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
from typing import List, Optional
from app.ledger.schemas.reporting import StockBalanceResponse, LedgerHistoryResponse
from app.ledger.domain.reporting.service import ReportingService

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
    
    from app.ledger.domain.idempotency.service import IdempotencyService
    
    # 1. Idempotency Check (Area B Guard)
    idem_result = await IdempotencyService.check_or_register_command(db, command)
    if idem_result.action == "IGNORE":
        await db.commit() # Commit the lock release
        return {"status": "IGNORED", "message": idem_result.reason, "existing_summary": idem_result.existing_summary}
        
    elif idem_result.action == "REVERSE_AND_PROCEED":
        # In a full system, we would enqueue a reversal command here before proceeding.
        # For simplicity, we just log it and proceed with the new command as a forward-correction.
        pass

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
        elif command.transaction_type == TransactionType.LOSS_IN_TRANSIT and command.transfer_id:
            result = await InTransitService.process_loss(db, command, command.transfer_id)
        else:
            result = await EventStoreService.commit_command(db, command)
            
        # Update Idempotency Registry to COMPLETED
        from app.ledger.models.idempotency import IdempotencyRegistry, IdempotencyStatus
        from sqlalchemy.future import select
        stmt = select(IdempotencyRegistry).where(IdempotencyRegistry.source_event_id == command.source_event_id)
        idem_record = (await db.execute(stmt)).scalars().first()
        if idem_record:
            idem_record.status = IdempotencyStatus.COMPLETED
            idem_record.result_summary = {"status": "COMMITTED", "event_id": command.source_event_id}
            
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


@ledger_router.get("/balances", response_model=List[StockBalanceResponse])
async def get_stock_balances(
    node_id: Optional[str] = None,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    CQRS Read API: Fetches current pre-calculated stock balances.
    Automatically filters results based on the JWT `allowed_nodes` claims.
    Optionally filter to a specific valid node_id.
    """
    # Any authenticated user with a valid token can query the Ledger Read API, 
    # but the ReportingService strictly filters what they get back.
    balances = await ReportingService.get_balances(db, actor, node_id)
    return balances

@ledger_router.get("/history/{node_id}/{item_id}", response_model=List[LedgerHistoryResponse])
async def get_inventory_history(
    node_id: str,
    item_id: str,
    limit: int = 50,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    CQRS Read API: Fetches the immutable event log explaining how a balance arrived at its current state.
    Strictly asserts the actor has access to the requested `node_id`.
    """
    history = await ReportingService.get_history(db, actor, node_id, item_id, limit)
    return history

