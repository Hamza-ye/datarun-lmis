import datetime
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.ledger.schemas.command import LedgerCommand, TransactionType
from app.ledger.models.in_transit import InTransitRegistry, InTransitStatus, InternalDLQ
from app.ledger.domain.event_store.service import EventStoreService

class InTransitService:
    
    @staticmethod
    async def process_dispatch(session: AsyncSession, command: LedgerCommand, dest_node_id: str) -> InTransitRegistry:
        """
        Step 1: The Departure. 
        Deducts stock from source via Area C, and opens a tracking record in Area D.
        """
        if command.transaction_type != TransactionType.TRANSFER:
            raise ValueError(f"Dispatch requires TransactionType.TRANSFER, got {command.transaction_type}")
            
        # 1. Deduct from Source (Area C Math)
        # We pass the command directly; EventStoreService converts TRANSFER to negative delta
        await EventStoreService.commit_command(session, command)
        
        # 2. Open the Tracking Record
        registry = InTransitRegistry(
            source_node_id=command.node_id,
            dest_node_id=dest_node_id,
            item_id=command.item_id,
            qty_shipped=command.quantity,
            dispatched_at=command.occurred_at,
            # In a real app we'd fetch this from the Policy Resolver API. Hardcoding 14 days for MVP.
            auto_close_after=command.occurred_at + datetime.timedelta(days=14)
        )
        session.add(registry)
        await session.flush() # Flush to generate the transfer_id UUID
        
        return registry

    @staticmethod
    async def process_receipt(session: AsyncSession, command: LedgerCommand, transfer_id: str) -> InTransitRegistry:
        """
        Step 2: The Arrival.
        Credits stock to destination via Area C, and closes/updates the Area D tracking record.
        """
        if command.transaction_type != TransactionType.RECEIPT:
             raise ValueError(f"Receipt requires TransactionType.RECEIPT, got {command.transaction_type}")
             
        # 1. Fetch Tracking Record
        try:
            transfer_uuid = uuid.UUID(transfer_id)
        except ValueError:
            raise ValueError(f"Invalid transfer_id format: {transfer_id}")
            
        stmt = select(InTransitRegistry).where(InTransitRegistry.transfer_id == transfer_uuid).with_for_update()
        result = await session.execute(stmt)
        registry = result.scalars().first()
        
        if not registry:
            raise ValueError(f"No open transfer found with ID {transfer_id}")
            
        if registry.status not in [InTransitStatus.OPEN, InTransitStatus.PARTIAL]:
            raise ValueError(f"Transfer {transfer_id} is already in state {registry.status}")
            
        # 2. Credit Destination (Area C Math)
        await EventStoreService.commit_command(session, command)
        
        # 3. Update Tracking Record
        registry.qty_received += command.quantity
        
        if registry.qty_received >= registry.qty_shipped:
            registry.status = InTransitStatus.COMPLETED
        elif registry.qty_received > 0:
            registry.status = InTransitStatus.PARTIAL
            
        return registry

    @staticmethod
    async def auto_close_stale_transfers(session: AsyncSession):
        """
        Step 3: The Safety Net (Cron Job Target).
        Finds OPEN/PARTIAL transfers past their deadline and auto-receives them to prevent dirty data.
        If Area C rejects it (e.g. node deactivated), catches the exception in InternalDLQ.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        
        stmt = select(InTransitRegistry).where(
            InTransitRegistry.status.in_([InTransitStatus.OPEN, InTransitStatus.PARTIAL]),
            InTransitRegistry.auto_close_after < now
        ).with_for_update(skip_locked=True) # Don't block other active transactions
        
        result = await session.execute(stmt)
        stale_records = result.scalars().all()
        
        count = 0
        for record in stale_records:
            missing_qty = record.qty_shipped - record.qty_received
            
            if missing_qty <= 0:
                record.status = InTransitStatus.COMPLETED
                continue
                
            # Synthesize an Auto-Receipt Command
            auto_receipt_cmd = LedgerCommand(
                source_event_id=f"AUTO_RECV_{record.transfer_id}",
                version_timestamp=int(now.timestamp()),
                transaction_type=TransactionType.RECEIPT,
                node_id=record.dest_node_id,
                item_id=record.item_id,
                quantity=missing_qty,
                transfer_id=str(record.transfer_id),
                occurred_at=now,
                metadata={"reason": "SYSTEM_AUTO_CLOSE"}
            )
            
            # Using a nested savepoint (begin_nested) so if Area C fails, we don't blow up the entire cron batch
            nested = await session.begin_nested()
            try:
                await EventStoreService.commit_command(session, auto_receipt_cmd)
                record.qty_received += missing_qty
                record.status = InTransitStatus.STALE_AUTO_CLOSED
                await nested.commit()
                count += 1
            except Exception as e:
                # Catch Area C failures (or OCC race condition exhaustion)
                await nested.rollback()
                record.status = InTransitStatus.FAILED_AUTO_CLOSE
                
                # Log to DLQ
                dlq_entry = InternalDLQ(
                    source_process="AREA_D_AUTO_RECEIPT",
                    reference_id=str(record.transfer_id),
                    error_message=str(e)
                )
                session.add(dlq_entry)
                
        return count
