import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ActorContext, get_current_actor
from core.database import get_db
from app.ledger.schemas.command import LedgerCommand
from app.ledger.domain.gatekeeper.service import GatekeeperService
from app.ledger.domain.event_store.service import EventStoreService
from app.ledger.domain.in_transit.service import InTransitService
from app.ledger.schemas.command import TransactionType

ledger_router = APIRouter(prefix="/api/ledger", tags=["Ledger Core"])
gatekeeper_router = APIRouter(prefix="/api/ledger/gatekeeper", tags=["Ledger Gatekeeper"])

@ledger_router.post("/commands", status_code=status.HTTP_201_CREATED)
async def submit_ledger_command(
    command: LedgerCommand,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    Internal API Gateway for Ledger operations.
    The Adapter (acting as 'ledger_system') submits normalized commands here.
    This routes to Area B (Idempotency), Area E (Approval), or Area C/D directly.
    """
    actor.require_role("ledger_system")
    
    # Idempotency check happens implicitly inside the services if we abstract it, 
    # but for manual composition we can use the Gatekeeper to "Stage" high risk items.
    
    # Dummy Threshold Policy (Normally resolving via Area F PolicyResolver)
    requires_approval = command.quantity >= 1000 or command.transaction_type == TransactionType.ADJUSTMENT
    
    if requires_approval:
        # Route to Area E (Gatekeeper)
        await GatekeeperService.stage_command(db, command, "System Policy Threshold Exceeded")
        await db.commit()
        return {"status": "STAGED", "message": "Transaction requires manual approval"}
        
    else:
        # Route to Area C (Event Store) or Area D (In-Transit)
        if command.transaction_type == TransactionType.TRANSFER:
            result = await InTransitService.process_dispatch(db, command, dest_node_id=command.metadata.get("dest_node_id", "UNKNOWN"))
        elif command.transaction_type == TransactionType.RECEIPT and command.transfer_id:
            result = await InTransitService.process_receipt(db, command, command.transfer_id)
        else:
            result = await EventStoreService.commit_command(db, command)
            
        await db.commit()
        return {"status": "COMMITTED", "event_id": command.source_event_id}

@gatekeeper_router.post("/{staged_id}/resolve")
async def resolve_staged_command(
    staged_id: UUID,
    # In a real app we'd take a Pydantic model for the payload
    # using a dict shortcut for the MVP example
    action_data: dict, 
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    UI Endpoint for Supervisors to Approve or Reject transactions.
    """
    actor.require_role("ledger_supervisor")
    
    from app.ledger.schemas.gatekeeper import SupervisorActionPayload, ApprovalActionType
    
    action_type = ApprovalActionType.APPROVE if action_data.get("action") == "APPROVE" else ApprovalActionType.REJECT
    payload = SupervisorActionPayload(
         actor_id=actor.actor_id,
         action=action_type,
         comment=action_data.get("comment", "")
    )
    
    # (In a real system we'd fetch the staged command first here to check `actor.require_node_access(cmd.node_id)`)
    
    approved_command = await GatekeeperService.resolve_command(db, staged_id, payload)
    
    if approved_command:
        # If approved, flush it to the real engine
        await EventStoreService.commit_command(db, approved_command)
        
    await db.commit()
    return {"status": "RESOLVED", "action": action_type.value}
