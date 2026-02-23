import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.database import async_session_maker
from app.adapter.models.engine import AdapterInbox, InboxStatus, MappingContract, DeadLetterQueue, AdapterLogs
from app.adapter.schemas.dsl import MappingContractDSL
from app.adapter.engine.mapper import MapperEngine

class AdapterWorker:
    """
    Background asynchronous loop that fetches RECEIVED payloads from the inbox, 
    routes them to the correct mapping contract, runs the engine, and forwards 
    the result to the configured Ledger endpoint.
    """
    
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
            async with httpx.AsyncClient() as client:
                for cmd in commands:
                    try:
                        response = await client.request(
                            method=dsl.destination.method,
                            url=url,
                            json=cmd,
                            timeout=10.0
                        )
                        
                        # Log Trace
                        log_entry = AdapterLogs(
                            inbox_id=item.id,
                            destination_url=url,
                            request_payload=cmd,
                            response_status=str(response.status_code),
                            response_body=response.text
                        )
                        session.add(log_entry)
                        
                        if response.status_code >= 500:
                            # Transient Destination Failure
                            item.status = InboxStatus.RETRY
                            await session.commit()
                            return
                        elif response.status_code >= 400:
                            # Permanent Validation Rejection by Destination
                            item.status = InboxStatus.ERROR
                            await session.commit()
                            return
                            
                    except (httpx.ConnectError, httpx.TimeoutException) as net_err:
                        # Network Failure (Transient)
                        log_entry = AdapterLogs(
                            inbox_id=item.id,
                            destination_url=url,
                            request_payload=cmd,
                            response_status="NETWORK_ERROR",
                            response_body=str(net_err)
                        )
                        session.add(log_entry)
                        item.status = InboxStatus.RETRY
                        await session.commit()
                        return
                    
            item.status = InboxStatus.FORWARDED
            await session.commit()
            
        except ValueError as e:
            if str(e).startswith("DLQ_TRIGGER"):
                item.status = InboxStatus.DLQ
                session.add(DeadLetterQueue(
                    inbox_id=item.id,
                    source_system=item.source_system,
                    error_reason=str(e),
                    context_data={
                        "payload_snapshot": item.payload,
                        "mapping_id": item.mapping_id,
                        "mapping_version": item.mapping_version
                    }
                ))
            else:
                item.status = InboxStatus.ERROR
            await session.commit()
        except Exception as e:
            print(f"WORKER ERROR: {e}")
            item.status = InboxStatus.ERROR
            await session.commit()
            
    @staticmethod
    async def run_loop(interval_seconds: int = 5):
        """Infinite loop designed to run alongside FastAPI"""
        try:
            while True:
                try:
                    processed = await AdapterWorker.process_batch()
                    if processed == 0:
                        await asyncio.sleep(interval_seconds)
                except Exception as e:
                    print(f"Adapter Worker Loop Error: {e}")
                    await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            # Re-raise to let the external caller (FastAPI lifespan) handle the clean exit
            raise
