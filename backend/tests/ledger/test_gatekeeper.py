import pytest
import pytest_asyncio
import datetime
from sqlalchemy.future import select

from app.ledger.models.gatekeeper import StagedCommand, ApprovalAudit, StagedCommandStatus, ApprovalActionType
from app.ledger.schemas.gatekeeper import SupervisorActionPayload
from app.ledger.domain.gatekeeper.service import GatekeeperService
from app.ledger.schemas.command import LedgerCommand, TransactionType
from app.ledger.models.idempotency import IdempotencyRegistry, IdempotencyStatus

# Mock base payload
VALID_COMMAND_PAYLOAD = {
    "source_event_id": "test_event_201",
    "version_timestamp": 1234567890,
    "transaction_type": "ADJUSTMENT",
    "node_id": "TEST_NODE_1",
    "item_id": "ITEM_1",
    "quantity": 500,
    "occurred_at": datetime.datetime.now(datetime.timezone.utc)
}

@pytest_asyncio.fixture
async def seeded_idempotency(db_session):
    """Area E relies on Area B having already registered the command"""
    registry = IdempotencyRegistry(
        source_event_id="test_event_201",
        status=IdempotencyStatus.PROCESSING,
        version_timestamp=1234567890
    )
    db_session.add(registry)
    await db_session.flush()
    return registry

@pytest.mark.asyncio
async def test_gatekeeper_stage_command(db_session, seeded_idempotency):
    """
    Simulates Area B handing off a 'Processing' payload to Area E.
    Area E should park it and set Area B to 'Staged'.
    """
    command = LedgerCommand(**VALID_COMMAND_PAYLOAD)
    
    # 1. Action: Stage the command
    await GatekeeperService.stage_command(
        session=db_session, 
        command=command, 
        reason="Adjustment exceeds +100 units"
    )
    await db_session.commit()
    
    # 2. Verify: Area B is now STAGED
    stmt_idem = select(IdempotencyRegistry).where(IdempotencyRegistry.source_event_id == "test_event_201")
    result_idem = await db_session.execute(stmt_idem)
    idem_record = result_idem.scalars().first()
    assert idem_record.status == IdempotencyStatus.STAGED
    
    # 3. Verify: Area E has the Waiting Room record
    stmt_staged = select(StagedCommand).where(StagedCommand.source_event_id == "test_event_201")
    result_staged = await db_session.execute(stmt_staged)
    staged_record = result_staged.scalars().first()
    
    assert staged_record is not None
    assert staged_record.status == StagedCommandStatus.AWAITING
    assert staged_record.stage_reason == "Adjustment exceeds +100 units"
    assert staged_record.payload["item_id"] == "ITEM_1"

@pytest.mark.asyncio
async def test_gatekeeper_approve_command(db_session, seeded_idempotency):
    """
    Simulates a Supervisor clicking 'Approve'.
    Should create audit log, mark as approved, and return the payload to go to Area C.
    """
    
    # Setup: Stage a command
    command = LedgerCommand(**VALID_COMMAND_PAYLOAD)
    await GatekeeperService.stage_command(db_session, command, "Manual Check")
    await db_session.flush()
    
    stmt = select(StagedCommand).where(StagedCommand.source_event_id == "test_event_201")
    result = await db_session.execute(stmt)
    staged_record = result.scalars().first()
    
    # Action: Supervisor Approves
    action_payload = SupervisorActionPayload(
        actor_id="SUPERVISOR_JONES",
        action=ApprovalActionType.APPROVE,
        comment="Looks accurate based on physical recount."
    )
    
    returned_command = await GatekeeperService.resolve_command(
        session=db_session,
        staged_id=staged_record.id,
        action_payload=action_payload
    )
    await db_session.commit()
    
    # Verify: Audit Row Created
    stmt_audit = select(ApprovalAudit).where(ApprovalAudit.staged_command_id == staged_record.id)
    result_audit = await db_session.execute(stmt_audit)
    audit = result_audit.scalars().first()
    
    assert audit.actor_id == "SUPERVISOR_JONES"
    assert audit.action == ApprovalActionType.APPROVE
    
    # Verify: Status Changed
    assert staged_record.status == StagedCommandStatus.APPROVED
    
    # Verify: Idempotency is Completed
    stmt_idem = select(IdempotencyRegistry).where(IdempotencyRegistry.source_event_id == "test_event_201")
    idem_record = (await db_session.execute(stmt_idem)).scalars().first()
    assert idem_record.status == IdempotencyStatus.COMPLETED
    assert idem_record.result_summary["status"] == "APPROVED_BY_SUPERVISOR"
    
    # Verify: Returned the payload
    assert isinstance(returned_command, LedgerCommand)
    assert returned_command.quantity == 500

@pytest.mark.asyncio
async def test_gatekeeper_reject_command(db_session, seeded_idempotency):
    """
    Simulates a Supervisor clicking 'Reject'.
    Should mark Staged as Rejected, Idempotency as Failed, and return None.
    """
    
    # Setup
    command = LedgerCommand(**VALID_COMMAND_PAYLOAD)
    await GatekeeperService.stage_command(db_session, command, "Suspiciously high value")
    await db_session.flush()
    
    staged_record = (await db_session.execute(select(StagedCommand))).scalars().first()
    
    # Action: Supervisor Rejects
    action_payload = SupervisorActionPayload(
        actor_id="SUPERVISOR_SMITH",
        action=ApprovalActionType.REJECT,
        comment="Fat finger error, they meant 50 units."
    )
    
    returned_command = await GatekeeperService.resolve_command(
        session=db_session,
        staged_id=staged_record.id,
        action_payload=action_payload
    )
    await db_session.commit()
    
    # Verify rejection states
    assert staged_record.status == StagedCommandStatus.REJECTED
    
    idem_record = (await db_session.execute(select(IdempotencyRegistry))).scalars().first()
    assert idem_record.status == IdempotencyStatus.FAILED
    assert idem_record.result_summary["status"] == "REJECTED_BY_SUPERVISOR"
    
    # Ensure nothing goes to Area C
    assert returned_command is None
