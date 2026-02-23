import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import datetime

from app.main import app
from core.database import get_db

@pytest_asyncio.fixture
async def async_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_scd_type_2_node_update(async_client: AsyncClient):
    from app.core.security import ActorContext, get_current_actor
    
    admin_ctx = ActorContext(
        actor_id="admin_1",
        roles=["system_admin"],
        allowed_nodes=["GLOBAL"]
    )
    app.dependency_overrides[get_current_actor] = lambda: admin_ctx

    # 1. Create original Node
    node_payload = {
        "node_id": "CLINIC_A",
        "code": "C_A",
        "name": "Clinic A",
        "node_type": "HF",
        "parent_id": "DISTRICT_1"
    }
    
    res_create = await async_client.post("/api/kernel/nodes", json=node_payload)
    assert res_create.status_code == 201
    
    # 2. Update Node (Change Parent to force a split)
    update_payload = {
        "parent_id": "DISTRICT_2"
    }
    res_update = await async_client.put("/api/kernel/nodes/CLINIC_A", json=update_payload)
    assert res_update.status_code == 200
    assert "Split created: True" in res_update.json()["message"]
    
    # 3. Verify Database State
    from app.kernel.models.registry import NodeRegistry
    from sqlalchemy.future import select
    
    db_session = app.dependency_overrides[get_db]()
    stmt = select(NodeRegistry).where(NodeRegistry.uid == "CLINIC_A").order_by(NodeRegistry.valid_from)
    result = await db_session.execute(stmt)
    records = result.scalars().all()
    
    assert len(records) == 2
    
    old_record = records[0]
    new_record = records[1]
    
    assert old_record.parent_id == "DISTRICT_1"
    assert old_record.valid_to.date() == datetime.date.today()
    
    assert new_record.parent_id == "DISTRICT_2"
    assert new_record.valid_from.date() == datetime.date.today()
    assert new_record.valid_to is None
    
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_commodity_creation(async_client: AsyncClient):
    from app.core.security import ActorContext, get_current_actor
    
    admin_ctx = ActorContext(
        actor_id="admin_1",
        roles=["system_admin"],
        allowed_nodes=["GLOBAL"]
    )
    app.dependency_overrides[get_current_actor] = lambda: admin_ctx
    
    payload = {
        "item_id": "PARAM_500",
        "code": "P_500",
        "name": "Paracetamol 500",
        "base_unit": "TABLET"
    }
    
    res = await async_client.post("/api/kernel/commodities", json=payload)
    assert res.status_code == 201
    
    res_get = await async_client.get("/api/kernel/commodities")
    assert res_get.status_code == 200
    assert len(res_get.json()) > 0
    assert res_get.json()[0]["item_id"] == "PARAM_500"
    
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_historical_topology_correction(async_client: AsyncClient, db_session):
    from app.core.security import ActorContext, get_current_actor
    from app.kernel.models.registry import NodeRegistry
    from sqlalchemy.future import select
    
    admin_ctx = ActorContext(
        actor_id="admin_1",
        roles=["system_admin"],
        allowed_nodes=["GLOBAL"]
    )
    app.dependency_overrides[get_current_actor] = lambda: admin_ctx
    
    # 1. Manually insert a hypothetical historical node (Jan 1st to None)
    n = NodeRegistry(
        uid="CLINIC_HIST",
        code="C_H",
        name="Historic Clinic",
        node_type="HF",
        parent_id="DISTRICT_OLD",
        valid_from=datetime.date(2026, 1, 1)
    )
    db_session.add(n)
    await db_session.commit()
    
    # 2. Apply a correction effective Feb 1st
    correction_payload = {
        "new_parent_id": "DISTRICT_NEW",
        "effective_date": "2026-02-01"
    }
    
    res = await async_client.post("/api/kernel/nodes/CLINIC_HIST/topology-correction", json=correction_payload)
    assert res.status_code == 200
    
    # 3. Verify the historical split
    stmt = select(NodeRegistry).where(NodeRegistry.uid == "CLINIC_HIST").order_by(NodeRegistry.valid_from)
    result = await db_session.execute(stmt)
    records = result.scalars().all()
    
    assert len(records) == 2
    
    # OLD RECORD (Jan 1 to Feb 1)
    assert records[0].parent_id == "DISTRICT_OLD"
    assert str(records[0].valid_from)[:10] == "2026-01-01"
    assert str(records[0].valid_to)[:10] == "2026-02-01"
    
    # NEW RECORD (Feb 1 to None)
    assert records[1].parent_id == "DISTRICT_NEW"
    assert str(records[1].valid_from)[:10] == "2026-02-01"
    assert records[1].valid_to is None
    
    app.dependency_overrides.clear()
