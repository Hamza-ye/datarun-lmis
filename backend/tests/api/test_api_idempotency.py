import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from core.database import get_db


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
async def test_ledger_command_idempotency(async_client: AsyncClient, db_session):
    """Submits the EXACT same command twice. The second should be softly ignored."""
    from app.core.security import ActorContext, get_current_actor
    
    worker_ctx = ActorContext(
        actor_id="ledger_system_worker",
        roles=["ledger_system"],
        allowed_nodes=[]
    )
    app.dependency_overrides[get_current_actor] = lambda: worker_ctx
    payload = {
        "source_event_id": "DOUBLE_CLICK_001",
        "version_timestamp": 1,
        "transaction_type": "RECEIPT",
        "node_id": "TEST_NODE",
        "item_id": "TEST_ITEM",
        "quantity": 100,
        "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    
    # Fire First Request
    res1 = await async_client.post(
        "/api/ledger/commands", 
        json=payload, 
        headers=auth_header("mock_ledger_worker_token")
    )
    assert res1.status_code == 201
    assert res1.json()["status"] == "COMMITTED"
    
    # Fire it AGAIN simulating a network retry / UI double click
    res2 = await async_client.post(
        "/api/ledger/commands", 
        json=payload, 
        headers=auth_header("mock_ledger_worker_token")
    )
    
    # It should succeed without blowing up, but tell the client it was ignored
    assert res2.status_code == 201 # HTTP 201 is fine, the business logic handled it.
    body = res2.json()
    assert body["status"] == "IGNORED"
    assert "Duplicate" in body["message"]

@pytest.mark.asyncio
async def test_topology_correction_idempotency(async_client: AsyncClient, db_session):
    """Submits the same topology correction twice."""
    from app.core.security import ActorContext, get_current_actor
    from app.kernel.models.registry import NodeRegistry
    
    admin_ctx = ActorContext(
        actor_id="admin_1",
        roles=["system_admin"],
        allowed_nodes=["GLOBAL"]
    )
    app.dependency_overrides[get_current_actor] = lambda: admin_ctx
    
    # 1. Setup row
    n = NodeRegistry(
        uid="CLINIC_IDEM_1",
        code="C_I_1",
        name="Clinic Idempotency",
        node_type="HF",
        parent_id="DISTRICT_1",
        valid_from=datetime.date(2026, 1, 1)
    )
    db_session.add(n)
    await db_session.commit()
    
    payload = {
        "new_parent_id": "DISTRICT_2",
        "effective_date": "2026-02-01"
    }
    
    # Fire first
    res1 = await async_client.post(
        "/api/kernel/nodes/CLINIC_IDEM_1/topology-correction", 
        json=payload, 
        headers=auth_header("mock_system_admin_token")
    )
    assert res1.status_code == 200
    assert res1.json()["message"] == "Historical topology corrected"
    
    # DEBUG: Check what is in the DB now
    from sqlalchemy.future import select
    all_nodes = (await db_session.execute(select(NodeRegistry).where(NodeRegistry.uid == "CLINIC_IDEM_1"))).scalars().all()
    for node in all_nodes:
        print(f"DEBUG DB ROW: {node.uid}, parent={node.parent_id}, from={node.valid_from}, to={node.valid_to}")
    
    # Fire second
    res2 = await async_client.post(
        "/api/kernel/nodes/CLINIC_IDEM_1/topology-correction", 
        json=payload, 
        headers=auth_header("mock_system_admin_token")
    )
    
    print("DEBUG IDEMPOTENCY RES2:", res2.json())
    assert res2.status_code == 200
    assert res2.json()["message"] == "Historical topology already corrected for this date."
