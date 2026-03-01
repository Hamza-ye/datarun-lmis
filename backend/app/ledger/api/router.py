from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ActorContext, get_current_actor
from app.ledger.domain.event_store.service import EventStoreService
from app.ledger.domain.gatekeeper.service import GatekeeperService
from app.ledger.domain.in_transit.service import InTransitService
from app.ledger.domain.reporting.service import ReportingService
from app.ledger.schemas.command import LedgerCommand, TransactionType
from app.ledger.schemas.gatekeeper import ApprovalActionRequest
from app.ledger.schemas.in_transit import (
    InTransitTransferResponse,
    ReceiveTransferRequest,
)
from app.ledger.schemas.reporting import LedgerHistoryResponse, StockBalanceResponse
from core.database import get_db

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
        # Create a Reversal Command (Symmetry of Governance)
        reversal_command = command.model_copy(deep=True)
        reversal_command.quantity = -command.quantity # Invert the quantity
        reversal_command.source_event_id = f"REV-{command.source_event_id}"
        
        # Immediately stage the Reversal for Supervisor Approval because it alters history
        await GatekeeperService.stage_command(db, reversal_command, "Symmetry of Governance: Reversal of modified transaction")
        await db.commit()
        return {"status": "STAGED", "message": "Reversal of prior transaction requires manual approval before proceeding."}

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
        from sqlalchemy.future import select

        from app.ledger.models.idempotency import IdempotencyRegistry, IdempotencyStatus
        stmt = select(IdempotencyRegistry).where(IdempotencyRegistry.source_event_id == command.source_event_id)
        idem_record = (await db.execute(stmt)).scalars().first()
        if idem_record:
            idem_record.status = IdempotencyStatus.COMPLETED
            idem_record.result_summary = {"status": "COMMITTED", "event_id": command.source_event_id}
            
        await db.commit()
        return {"status": "COMMITTED", "event_id": command.source_event_id}

@gatekeeper_router.get("/staged")
async def list_staged_commands(
    node_id: Optional[str] = None,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    List transactions awaiting approval for the actor's allowed nodes.
    """
    actor.require_role("ledger_supervisor")
    from sqlalchemy.future import select

    from app.ledger.models.gatekeeper import StagedCommand
    
    stmt = select(StagedCommand).where(StagedCommand.status == "AWAITING")
    if node_id:
        actor.require_node_access(node_id)
        stmt = stmt.where(StagedCommand.node_id == node_id)
    elif "GLOBAL" not in actor.allowed_nodes:
        # Prevent supervisors from seeing other districts
        stmt = stmt.where(StagedCommand.node_id.in_(actor.allowed_nodes))
        
    result = await db.execute(stmt)
    staged = result.scalars().all()
    return [{
        "id": str(s.id),
        "source_event_id": s.source_event_id,
        "command_type": s.command_type,
        "payload": s.payload,
        "stage_reason": s.stage_reason,
        "node_id": s.node_id,
        "status": s.status,
        "created_at": s.created_at
    } for s in staged]

@gatekeeper_router.post("/{staged_id}/resolve")
async def resolve_staged_command(
    staged_id: UUID,
    action_data: ApprovalActionRequest, 
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    UI Endpoint for Supervisors to Approve or Reject transactions.
    """
    actor.require_role("ledger_supervisor")
    
    from app.ledger.schemas.gatekeeper import (
        ApprovalActionType,
        SupervisorActionPayload,
    )
    
    action_type = ApprovalActionType.APPROVE if action_data.action == "APPROVE" else ApprovalActionType.REJECT
    payload = SupervisorActionPayload(
         actor_id=actor.actor_id,
         action=action_type,
         comment=action_data.comment
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

@ledger_router.get("/transfers", response_model=List[InTransitTransferResponse])
async def list_transfers(
    node_id: Optional[str] = None,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    CQRS Read API: Fetches pending incoming/outgoing transfers.
    Automatically filters results based on the JWT `allowed_nodes` claims.
    """
    from sqlalchemy import or_
    from sqlalchemy.future import select

    from app.ledger.models.in_transit import InTransitRegistry

    stmt = select(InTransitRegistry)
    
    if node_id:
        if "GLOBAL" not in actor.allowed_nodes and node_id not in actor.allowed_nodes:
            raise HTTPException(status_code=403, detail="No access to this node.")
        stmt = stmt.where(or_(InTransitRegistry.source_node_id == node_id, InTransitRegistry.dest_node_id == node_id))
    elif "GLOBAL" not in actor.allowed_nodes:
        stmt = stmt.where(or_(
            InTransitRegistry.source_node_id.in_(actor.allowed_nodes),
            InTransitRegistry.dest_node_id.in_(actor.allowed_nodes)
        ))
        
    result = await db.execute(stmt)
    transfers = result.scalars().all()
    return transfers

@ledger_router.post("/transfers/{transfer_id}/receive", status_code=status.HTTP_201_CREATED)
async def receive_transfer(
    transfer_id: UUID,
    payload: ReceiveTransferRequest,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    UI Endpoint to mark a dispatched transfer as received.
    """
    if "GLOBAL" not in actor.allowed_nodes and payload.node_id not in actor.allowed_nodes:
        raise HTTPException(status_code=403, detail="No access to this node.")
        
    actor.require_role("ledger_system") 
    
    from sqlalchemy.future import select

    from app.ledger.models.in_transit import InTransitRegistry
    
    stmt = select(InTransitRegistry).where(InTransitRegistry.transfer_id == transfer_id)
    transfer = (await db.execute(stmt)).scalars().first()
    
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
        
    if transfer.dest_node_id != payload.node_id:
        raise HTTPException(status_code=400, detail="Destination node mismatch")

    from app.ledger.schemas.command import LedgerCommand, TransactionType
    
    receipt_command = LedgerCommand(
        source_event_id=payload.source_event_id,
        version_timestamp=int(payload.occurred_at.timestamp()),
        transaction_type=TransactionType.RECEIPT,
        node_id=payload.node_id,
        item_id=transfer.item_id,
        quantity=payload.qty_received,
        transfer_id=str(transfer_id)
    )
    
    from app.ledger.domain.idempotency.service import IdempotencyService
    idem_result = await IdempotencyService.check_or_register_command(db, receipt_command)
    if idem_result.action == "IGNORE":
        await db.commit()
        return {"status": "IGNORED", "message": idem_result.reason, "existing_summary": idem_result.existing_summary}
        
    result = await InTransitService.process_receipt(db, receipt_command, str(transfer_id))
    
    from app.ledger.models.idempotency import IdempotencyRegistry, IdempotencyStatus
    stmt_idem = select(IdempotencyRegistry).where(IdempotencyRegistry.source_event_id == receipt_command.source_event_id)
    idem_record = (await db.execute(stmt_idem)).scalars().first()
    if idem_record:
        idem_record.status = IdempotencyStatus.COMPLETED
        idem_record.result_summary = {"status": "COMMITTED", "event_id": receipt_command.source_event_id}
        
    await db.commit()
    return {"status": "COMMITTED", "event_id": receipt_command.source_event_id, "transfer_status": result.get("transfer_status")}
