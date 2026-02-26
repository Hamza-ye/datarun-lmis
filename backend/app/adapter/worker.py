import asyncio
import httpx
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.database import async_session_maker
from app.adapter.models.engine import AdapterInbox, InboxStatus, MappingContract, AdapterLogs
from app.adapter.schemas.dsl import MappingContractDSL
from app.adapter.engine.mapper import MapperEngine

logger = logging.getLogger(__name__)

class AdapterWorker:
    """
    Background asynchronous loop that fetches RECEIVED payloads from the inbox, 
    routes them to the correct mapping contract, runs the engine, and forwards 
    the result to the configured Ledger endpoint.
    """
    
    @staticmethod
    async def reclaim_zombies(session: AsyncSession, stale_minutes: int = 15):
        """Reclaims inbox rows that were stuck in PROCESSING state due to worker crashes."""
        import datetime
        from sqlalchemy import update
        now = datetime.datetime.now(datetime.timezone.utc)
        threshold = now - datetime.timedelta(minutes=stale_minutes)
        
        stmt = update(AdapterInbox).where(
            AdapterInbox.status == InboxStatus.PROCESSING,
            AdapterInbox.updated_at < threshold
        ).values(status=InboxStatus.RECEIVED)
        
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount

    @staticmethod
    async def insert_log_async(log_data: dict):
        """Fire-and-forget log insertion in a dedicated lightweight session."""
        try:
            async with async_session_maker() as log_session:
                log_session.add(AdapterLogs(**log_data))
                await log_session.commit()
        except Exception as e:
            logger.error(f"Failed to insert adapter log asynchronously: {e}")

    @staticmethod
    async def process_batch(batch_size: int = 50, session: AsyncSession = None):
        if session:
            return await AdapterWorker._do_process_batch(session, batch_size)
            
        async with async_session_maker() as new_session:
            return await AdapterWorker._do_process_batch(new_session, batch_size)

    @staticmethod
    async def _do_process_batch(session: AsyncSession, batch_size: int):
        # 1. Fetch pending payloads with DB-level lock to prevent concurrent worker duplication
        stmt = select(AdapterInbox).where(AdapterInbox.status == InboxStatus.RECEIVED).with_for_update(skip_locked=True).limit(batch_size)
        result = await session.execute(stmt)
        inbox_items = result.scalars().all()
        
        if not inbox_items:
            return 0
            
        # Immediately set to processing to release row locks before slow HTTP calls
        for item in inbox_items:
            item.status = InboxStatus.PROCESSING
        await session.commit()
            
        for item in inbox_items:
            # We must refresh the object because we committed the session
            await session.refresh(item)
            await AdapterWorker.process_single(session, item)
            
        return len(inbox_items)

    @staticmethod
    async def process_single(session: AsyncSession, item: AdapterInbox):
        try:
            # 2. Strict Contract Resolving
            stmt = select(MappingContract).where(
                MappingContract.id == item.mapping_id,
                MappingContract.version == item.mapping_version
            )
            result = await session.execute(stmt)
            contract_record = result.scalars().first()
            
            if not contract_record:
                raise Exception(f"Mapping Contract {item.mapping_id} v{item.mapping_version} not found.")
                
            dsl = MappingContractDSL(**contract_record.dsl_config)
            
            # 3. Execution
            commands = await MapperEngine.run(session, item.payload, contract=dsl)
            
            # 4. Strict Forwarding & HTTP Failure Evaluation
            url = dsl.destination.url
            headers = dsl.destination.headers or {}
            async with httpx.AsyncClient() as client:
                for cmd in commands:
                    try:
                        response = await client.request(
                            method=dsl.destination.method,
                            url=url,
                            headers=headers,
                            json=cmd,
                            timeout=10.0
                        )
                        
                        # Log Trace
                        log_data = {
                            "inbox_id": item.id,
                            "destination_url": url,
                            "request_payload": cmd,
                            "response_status": str(response.status_code),
                            "response_body": response.text
                        }
                        asyncio.create_task(AdapterWorker.insert_log_async(log_data))
                        
                        if response.status_code >= 500:
                            # Transient Destination Failure
                            item.status = InboxStatus.RETRY
                            await session.commit()
                            return
                        elif response.status_code >= 400:
                            # Permanent Validation Rejection by Destination
                            item.status = InboxStatus.ERROR
                            item.error_message = f"Destination Rejected: {response.status_code} - {response.text}"
                            await session.commit()
                            return
                            
                    except (httpx.ConnectError, httpx.TimeoutException) as net_err:
                        # Network Failure (Transient)
                        log_data = {
                            "inbox_id": item.id,
                            "destination_url": url,
                            "request_payload": cmd,
                            "response_status": "NETWORK_ERROR",
                            "response_body": str(net_err)
                        }
                        asyncio.create_task(AdapterWorker.insert_log_async(log_data))
                        
                        item.status = InboxStatus.RETRY
                        await session.commit()
                        return
                    
            item.status = InboxStatus.FORWARDED
            await session.commit()
            
        except ValueError as e:
            if str(e).startswith("DLQ_TRIGGER"):
                item.status = InboxStatus.DLQ
                item.error_message = str(e)
            else:
                item.status = InboxStatus.ERROR
                item.error_message = str(e)
            await session.commit()
        except Exception as e:
            logger.error(f"WORKER ERROR: {e}")
            item.status = InboxStatus.ERROR
            item.error_message = str(e)
            await session.commit()
            
    @staticmethod
    async def run_loop(interval_seconds: int = 5):
        """Infinite loop designed to run alongside FastAPI"""
        import time
        last_reclaim = 0
        try:
            while True:
                try:
                    if time.time() - last_reclaim > 300: # Every 5 mins
                        async with async_session_maker() as session:
                            zombies = await AdapterWorker.reclaim_zombies(session)
                            if zombies > 0:
                                logger.warning(f"Reclaimed {zombies} zombie payloads")
                        last_reclaim = time.time()
                        
                    processed = await AdapterWorker.process_batch()
                    if processed == 0:
                        await asyncio.sleep(interval_seconds)
                except Exception as e:
                    logger.error(f"Adapter Worker Loop Error: {e}")
                    await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            # Re-raise to let the external caller (FastAPI lifespan) handle the clean exit
            raise
