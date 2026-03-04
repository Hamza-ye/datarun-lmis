import asyncio
import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.adapter.engine.mapper import MapperEngine
from app.adapter.models.engine import (
    AdapterEgressLogs,
    AdapterInbox,
    InboxStatus,
    MappingContract,
)
from app.adapter.schemas.dsl import MappingContractDSL
from core.database import async_session_maker

logger = logging.getLogger(__name__)


class AdapterWorker:
    """
    Background asynchronous loops that execute the 3-Layer DDD architecture.
    Layer 2 (Transform): Fetches RECEIVED payloads, maps them, saves MAPPED state.
    Layer 3 (Egress): Fetches MAPPED payloads, dispatches via HTTP, logs to Egress.
    """

    @staticmethod
    async def reclaim_zombies(session: AsyncSession, stale_minutes: int = 15):
        """Reclaims inbox rows that were stuck in PROCESSING state due to worker crashes."""
        import datetime

        from sqlalchemy import update

        now = datetime.datetime.now(datetime.timezone.utc)
        threshold = now - datetime.timedelta(minutes=stale_minutes)

        stmt = (
            update(AdapterInbox)
            .where(
                AdapterInbox.status == InboxStatus.PROCESSING,
                AdapterInbox.updated_at < threshold,
            )
            .values(status=InboxStatus.RECEIVED)
        )

        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount

    @staticmethod
    async def insert_egress_log_async(log_data: dict, session: AsyncSession = None):
        """Fire-and-forget log insertion for Layer 3 (Egress) tracing."""
        try:
            if session:
                session.add(AdapterEgressLogs(**log_data))
                await session.commit()
            else:
                async with async_session_maker() as log_session:
                    log_session.add(AdapterEgressLogs(**log_data))
                    await log_session.commit()
        except Exception as e:
            logger.error(f"Failed to insert adapter egress log asynchronously: {e}")

    # ==========================================
    # LAYER 2: TRANSFORM ENGINE
    # ==========================================
    @staticmethod
    async def process_mapping_batch(batch_size: int = 50, session: AsyncSession = None):
        if session:
            return await AdapterWorker._do_process_mapping_batch(session, batch_size)

        async with async_session_maker() as new_session:
            return await AdapterWorker._do_process_mapping_batch(
                new_session, batch_size
            )

    @staticmethod
    async def _do_process_mapping_batch(session: AsyncSession, batch_size: int):
        stmt = (
            select(AdapterInbox)
            .where(AdapterInbox.status == InboxStatus.RECEIVED)
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
        result = await session.execute(stmt)
        inbox_items = result.scalars().all()

        if not inbox_items:
            return 0

        for item in inbox_items:
            item.status = InboxStatus.PROCESSING
        await session.commit()

        for item in inbox_items:
            await session.refresh(item)
            await AdapterWorker.process_single_mapping(session, item)

        return len(inbox_items)

    @staticmethod
    async def process_single_mapping(session: AsyncSession, item: AdapterInbox):
        try:
            # Resolve Contract
            stmt = select(MappingContract).where(
                MappingContract.id == item.mapping_id,
                MappingContract.version == item.mapping_version,
            )
            result = await session.execute(stmt)
            contract_record = result.scalars().first()

            if not contract_record:
                raise Exception(
                    f"Mapping Contract {item.mapping_id} v{item.mapping_version} not found."
                )

            dsl = MappingContractDSL(**contract_record.dsl_config)

            # Execute Transform
            commands = await MapperEngine.run(session, item.payload, contract=dsl)

            # Save exact mapped output & Update State
            item.mapped_payload = commands
            item.status = InboxStatus.MAPPED
            await session.commit()

        except ValueError as e:
            if str(e).startswith("DLQ_TRIGGER"):
                item.status = InboxStatus.DLQ
                item.error_message = str(e)
            else:
                item.status = InboxStatus.DLQ
                item.error_message = f"Mapping Error: {str(e)}"
            await session.commit()
        except Exception as e:
            logger.error(f"LAYER 2 MAPPING ERROR: {e}")
            item.status = InboxStatus.DLQ
            item.error_message = f"System Mapping Exception: {str(e)}"
            await session.commit()

    # ==========================================
    # LAYER 3: EGRESS ENGINE
    # ==========================================
    @staticmethod
    async def process_egress_batch(batch_size: int = 50, session: AsyncSession = None):
        if session:
            return await AdapterWorker._do_process_egress_batch(session, batch_size)

        async with async_session_maker() as new_session:
            return await AdapterWorker._do_process_egress_batch(new_session, batch_size)

    @staticmethod
    async def _do_process_egress_batch(session: AsyncSession, batch_size: int):
        stmt = (
            select(AdapterInbox)
            .where(
                AdapterInbox.status.in_([InboxStatus.MAPPED, InboxStatus.RETRY_EGRESS])
            )
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )

        result = await session.execute(stmt)
        inbox_items = result.scalars().all()

        if not inbox_items:
            return 0

        # We don't transition to PROCESSING here because if the HTTP call fails mid-flight,
        # we want it to stay MAPPED or RETRY_EGRESS so another worker picks it up.
        # But we do hold the row lock until we commit.

        for item in inbox_items:
            # Strict Layer 3 Invariant
            assert item.mapped_payload is not None, (
                "LAYER 3 INVARIANT FAILURE: mapped_payload is NULL."
            )
            assert item.mapping_version is not None, (
                "LAYER 3 INVARIANT FAILURE: mapping_version is NULL."
            )

            await AdapterWorker.process_single_egress(session, item)

        return len(inbox_items)

    @staticmethod
    async def process_single_egress(session: AsyncSession, item: AdapterInbox):
        try:
            # We ONLY need the contract for the URL, not the transformation rules
            stmt = select(MappingContract).where(
                MappingContract.id == item.mapping_id,
                MappingContract.version == item.mapping_version,
            )
            result = await session.execute(stmt)
            contract_record = result.scalars().first()
            if not contract_record:
                raise Exception("Contract URL lookup failed during Egress.")

            dsl = MappingContractDSL(**contract_record.dsl_config)
            url = dsl.destination.url
            headers = dsl.destination.headers or {}

            # Use the already transformed payload
            commands = item.mapped_payload

            import time

            start_time = time.time()

            async with httpx.AsyncClient() as client:
                for cmd in commands:
                    try:
                        response = await client.request(
                            method=dsl.destination.method,
                            url=url,
                            headers=headers,
                            json=cmd,
                            timeout=10.0,
                        )

                        execution_time_ms = int((time.time() - start_time) * 1000)

                        log_data = {
                            "inbox_id": item.id,
                            "destination_url": url,
                            "request_payload": cmd,
                            "destination_http_code": response.status_code,
                            "destination_response": response.text,
                            "execution_time_ms": execution_time_ms,
                        }

                        if session:
                            await AdapterWorker.insert_egress_log_async(
                                log_data, session=session
                            )
                        else:
                            asyncio.create_task(
                                AdapterWorker.insert_egress_log_async(log_data)
                            )

                        if response.status_code >= 500:
                            item.status = InboxStatus.RETRY_EGRESS
                            await session.commit()
                            return
                        elif response.status_code >= 400:
                            item.status = InboxStatus.DESTINATION_REJECTED
                            item.error_message = f"Destination Rejected: {response.status_code} - {response.text}"
                            await session.commit()
                            return

                    except (httpx.ConnectError, httpx.TimeoutException) as net_err:
                        log_data = {
                            "inbox_id": item.id,
                            "destination_url": url,
                            "request_payload": cmd,
                            "destination_http_code": None,
                            "destination_response": str(net_err),
                            "status": "NETWORK_ERROR",
                            "execution_time_ms": int((time.time() - start_time) * 1000),
                        }
                        if session:
                            await AdapterWorker.insert_egress_log_async(
                                log_data, session=session
                            )
                        else:
                            asyncio.create_task(
                                AdapterWorker.insert_egress_log_async(log_data)
                            )

                        item.status = InboxStatus.RETRY_EGRESS
                        await session.commit()
                        return

            item.status = InboxStatus.FORWARDED
            await session.commit()

        except Exception as e:
            logger.error(f"LAYER 3 EGRESS ERROR: {e}")
            item.status = InboxStatus.DLQ
            item.error_message = str(e)
            await session.commit()

    @staticmethod
    async def run_mapping_loop(interval_seconds: int = 5):
        """Infinite loop for Layer 2: Transformation"""
        import time

        last_reclaim = 0
        try:
            while True:
                try:
                    if time.time() - last_reclaim > 300:  # Every 5 mins
                        async with async_session_maker() as session:
                            zombies = await AdapterWorker.reclaim_zombies(session)
                            if zombies > 0:
                                logger.warning(f"Reclaimed {zombies} zombie payloads")
                        last_reclaim = time.time()

                    processed = await AdapterWorker.process_mapping_batch()
                    if processed == 0:
                        await asyncio.sleep(interval_seconds)
                except Exception as e:
                    logger.error(f"Adapter Mapping Loop Error: {e}")
                    await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise

    @staticmethod
    async def run_egress_loop(interval_seconds: int = 5):
        """Infinite loop for Layer 3: Delivery"""
        try:
            while True:
                try:
                    processed = await AdapterWorker.process_egress_batch()
                    if processed == 0:
                        await asyncio.sleep(interval_seconds)
                except Exception as e:
                    logger.error(f"Adapter Egress Loop Error: {e}")
                    await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise
