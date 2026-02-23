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
