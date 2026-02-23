from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.ledger.models.idempotency import IdempotencyRegistry, IdempotencyStatus
from app.ledger.schemas.command import LedgerCommand

class IdempotencyResult:
    """
    Data structure defining the Ledger's execution path after the Idempotency Guard check.
    action: PROCEED | REVERSE_AND_PROCEED | IGNORE
    """
    def __init__(self, action: str, reason: str, existing_summary: dict = None):
        self.action = action
        self.reason = reason
        self.existing_summary = existing_summary

class IdempotencyService:
    
    @staticmethod
    async def check_or_register_command(session: AsyncSession, command: LedgerCommand) -> IdempotencyResult:
        """
        Guards against duplicate processing of the same source event.
        Uses raw SQL row-level locks (FOR UPDATE) to prevent race conditions during concurrent submissions.
        Returns an IdempotencyResult dictating the next action for the Ledger core.
        """
        # 1. Look for existing record, locking the row to stop race conditions
        stmt = select(IdempotencyRegistry).where(
            IdempotencyRegistry.source_event_id == command.source_event_id
        ).with_for_update()
        
        result = await session.execute(stmt)
        existing_record = result.scalars().first()

        # 2. Complete New Entry (First Time)
        if not existing_record:
            new_record = IdempotencyRegistry(
                source_event_id=command.source_event_id,
                version_timestamp=command.version_timestamp,
                status=IdempotencyStatus.PROCESSING
            )
            session.add(new_record)
            # Flush to immediately write the processing state within this DB transaction
            await session.flush()
            return IdempotencyResult(action="PROCEED", reason="New command detected")
        
        # 3. Edited Form Detection (The Reversal Invariant)
        if command.version_timestamp > existing_record.version_timestamp:
            existing_record.version_timestamp = command.version_timestamp
            existing_record.status = IdempotencyStatus.PROCESSING
            existing_record.result_summary = None 
            await session.flush()
            return IdempotencyResult(
                action="REVERSE_AND_PROCEED", 
                reason="Newer version of existing command detected. Reversal required."
            )
            
        # 4. Pure Duplicate Drop (Same version or older delayed packet)
        if existing_record.status == IdempotencyStatus.PROCESSING:
             summary = {"message": "Command is currently processing in another thread"}
        else:
             summary = existing_record.result_summary or {"status": existing_record.status.value}
             
        return IdempotencyResult(
            action="IGNORE",
            reason="Duplicate command already processed or older version.",
            existing_summary=summary
        )
