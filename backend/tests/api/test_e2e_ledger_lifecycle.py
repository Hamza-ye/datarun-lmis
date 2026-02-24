import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import datetime
from sqlalchemy.future import select

from app.main import app
from core.database import get_db
from app.ledger.models.idempotency import IdempotencyRegistry, IdempotencyStatus
from app.ledger.models.gatekeeper import StagedCommand, StagedCommandStatus
from app.ledger.models.event_store import StockBalance, InventoryEvent

@pytest_asyncio.fixture
async def async_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()

def auth_header(token: str):
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_ledger_lifecycle_to_approval(async_client: AsyncClient, db_session):
    """
    E2E Test: 
    1. Adapter submits massive adjustment (Requires Approval) -> 201 STAGED
    2. Idempotency is STAGED, Command is AWAITING.
    3. Supervisor Approves it -> 200 RESOLVED
    4. Idempotency is COMPLETED, EventStore receives the event.
    """
    
    # --- STEP 1: Submit Command that requires approval (Quantity >= 1000 threshold in router) ---
    cmd_payload = {
        "source_event_id": "E2E_APPROVAL_TEST_1",
        "version_timestamp": 12345,
        "transaction_type": "ADJUSTMENT",
        "node_id": "HQ_WAREHOUSE",
        "item_id": "CRITICAL_ITEM",
        "quantity": 1500,  # Trips the router > 1000 threshold
        "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    
    # We must patch the security roles to let it through
    from app.core.security import ActorContext, get_current_actor
    worker_ctx = ActorContext(actor_id="ledger_worker", roles=["ledger_system"], allowed_nodes=[])
    app.dependency_overrides[get_current_actor] = lambda: worker_ctx
    
    res_submit = await async_client.post("/api/ledger/commands", json=cmd_payload)
    
    assert res_submit.status_code == 201
    assert res_submit.json()["status"] == "STAGED"
    
    # --- STEP 2: Verify Gatekeeper & Idempotency State ---
    
    # Verify Idempotency is bound
    stmt_idem = select(IdempotencyRegistry).where(IdempotencyRegistry.source_event_id == "E2E_APPROVAL_TEST_1")
    idem_rec = (await db_session.execute(stmt_idem)).scalars().first()
    assert idem_rec.status == IdempotencyStatus.STAGED
    
    # Verify waitlist
    stmt_staged = select(StagedCommand).where(StagedCommand.source_event_id == "E2E_APPROVAL_TEST_1")
    staged_rec = (await db_session.execute(stmt_staged)).scalars().first()
    assert staged_rec.status == StagedCommandStatus.AWAITING
    
    # Ensure nothing hit the EventStore yet
    bal_check = (await db_session.execute(select(StockBalance).where(StockBalance.item_id == "CRITICAL_ITEM"))).scalars().first()
    assert bal_check is None
    
    # --- STEP 3: Supervisor Resolves ---
    
    supervisor_ctx = ActorContext(actor_id="supervisor_bob", roles=["ledger_supervisor"], allowed_nodes=[])
    app.dependency_overrides[get_current_actor] = lambda: supervisor_ctx
    
    resolve_payload = {
        "action": "APPROVE",
        "comment": "Verified visually."
    }
    
    res_resolve = await async_client.post(
        f"/api/ledger/gatekeeper/{staged_rec.id}/resolve",
        json=resolve_payload
    )
    
    assert res_resolve.status_code == 200
    assert res_resolve.json()["status"] == "RESOLVED"
    
    # --- STEP 4: Final State Verification ---
    
    # DB refresh
    await db_session.refresh(idem_rec)
    await db_session.refresh(staged_rec)
    
    assert idem_rec.status == IdempotencyStatus.COMPLETED
    assert staged_rec.status == StagedCommandStatus.APPROVED
    
    # Prove the transaction crossed into the EventStore math engine
    bal_final = (await db_session.execute(select(StockBalance).where(StockBalance.item_id == "CRITICAL_ITEM"))).scalars().first()
    assert bal_final.quantity == 1500
    
    evt_final = (await db_session.execute(select(InventoryEvent).where(InventoryEvent.source_event_id == "E2E_APPROVAL_TEST_1"))).scalars().first()
    assert evt_final is not None
    assert evt_final.running_balance == 1500

    app.dependency_overrides.clear()
