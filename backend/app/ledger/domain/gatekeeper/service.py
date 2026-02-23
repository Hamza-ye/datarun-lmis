from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.ledger.schemas.command import LedgerCommand
from app.ledger.models.gatekeeper import StagedCommand, ApprovalAudit, StagedCommandStatus, ApprovalActionType
from app.ledger.schemas.gatekeeper import SupervisorActionPayload
from app.ledger.models.idempotency import IdempotencyRegistry, IdempotencyStatus

class GatekeeperService:
    
    @staticmethod
    async def stage_command(session: AsyncSession, command: LedgerCommand, reason: str) -> None:
        """
        Takes a new command and parks it in the Waiting Room.
        It updates the associated Idempotency record to STAGED to halt the downstream pipeline.
        This must happen in the same DB transaction as the incoming pipeline.
        """
        # 1. Park the Payload
        staged_record = StagedCommand(
            source_event_id=command.source_event_id,
            command_type=command.transaction_type.value,
            payload=command.model_dump(mode="json"),
            stage_reason=reason,
            status=StagedCommandStatus.AWAITING,
            node_id=command.node_id
        )
        session.add(staged_record)
        
        # 2. Update Idempotency Guard
        stmt = select(IdempotencyRegistry).where(
            IdempotencyRegistry.source_event_id == command.source_event_id
        ).with_for_update() # Ensure we don't have a race condition changing the state
        
        result = await session.execute(stmt)
        idem_record = result.scalars().first()
        
        if not idem_record:
            raise ValueError(f"Fatal Integrity Error: Missing Idempotency Registry for {command.source_event_id}")
            
        idem_record.status = IdempotencyStatus.STAGED
        
    @staticmethod
    async def resolve_command(session: AsyncSession, staged_id: UUID, action_payload: SupervisorActionPayload):
        """
        Called when a Supervisor clicks Approve or Reject.
        Writes the Audit Trail, flips the status, and returns the original Command Payload if APPROVED
        so the orchestrator can finally route it to Area C (Event Store).
        """
        # 1. Fetch the parked command
        stmt = select(StagedCommand).where(StagedCommand.id == staged_id).with_for_update()
        result = await session.execute(stmt)
        staged_record = result.scalars().first()
        
        if not staged_record:
            raise ValueError(f"Could not find staged record {staged_id}")
            
        if staged_record.status != StagedCommandStatus.AWAITING:
            raise ValueError(f"Staged record {staged_id} is already resolved: {staged_record.status}")
            
        # 2. Write Legal Audit Trail
        audit_record = ApprovalAudit(
            staged_command_id=staged_id,
            actor_id=action_payload.actor_id,
            action=action_payload.action,
            comment=action_payload.comment
        )
        session.add(audit_record)
        
        # 3. Handle Status Update
        staged_record.status = StagedCommandStatus.APPROVED if action_payload.action == ApprovalActionType.APPROVE else StagedCommandStatus.REJECTED
        
        # 4. Update Idempotency Status (Critical for Error Correction Loop)
        idem_stmt = select(IdempotencyRegistry).where(
            IdempotencyRegistry.source_event_id == staged_record.source_event_id
        ).with_for_update()
        idem_result = await session.execute(idem_stmt)
        idem_record = idem_result.scalars().first()
        
        if idem_record:
            if action_payload.action == ApprovalActionType.REJECT:
                 idem_record.status = IdempotencyStatus.FAILED
                 idem_record.result_summary = {"status": "REJECTED_BY_SUPERVISOR", "actor_id": action_payload.actor_id, "reason": action_payload.comment}
            elif action_payload.action == ApprovalActionType.APPROVE:
                 idem_record.status = IdempotencyStatus.COMPLETED
                 idem_record.result_summary = {"status": "APPROVED_BY_SUPERVISOR", "actor_id": action_payload.actor_id}
                 
        # 5. Return the payload to the Caller if Approved
        if action_payload.action == ApprovalActionType.APPROVE:
            return LedgerCommand(**staged_record.payload)
            
        return None
