import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

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
async def test_admin_requires_role(async_client: AsyncClient):
    """Ensure external systems or ledger workers cannot configure the adapter."""
    # 403 Forbidden with Wrong Role
    res1 = await async_client.get("/api/adapter/admin/contracts", headers=auth_header("mock_external_system_token"))
    assert res1.status_code == 403

    res2 = await async_client.get("/api/adapter/admin/contracts", headers=auth_header("mock_ledger_worker_token"))
    assert res2.status_code == 403

@pytest.mark.asyncio
async def test_contract_atomic_flip(async_client: AsyncClient):
    """Test creating a contract and activating it deprecates the previous one."""
    
    # We need a system_admin token. In MVP security.py, there isn't one defined yet.
    # Let's mock `get_current_actor` for this test block specifically.
    from app.core.security import ActorContext, get_current_actor
    
    admin_ctx = ActorContext(
        actor_id="admin_1",
        roles=["system_admin"],
        allowed_nodes=["GLOBAL"]
    )
    app.dependency_overrides[get_current_actor] = lambda: admin_ctx

    # 1. Create v1.0
    v1_payload = {"id": "test_contract", "version": "1.0", "dsl_config": {}}
    res_create = await async_client.post("/api/adapter/admin/contracts", json=v1_payload)
    assert res_create.status_code == 201

    # 2. Activate v1.0
    res_act = await async_client.post("/api/adapter/admin/contracts/test_contract/versions/1.0/activate")
    assert res_act.status_code == 200

    # 3. Create v1.1
    v2_payload = {"id": "test_contract", "version": "1.1", "dsl_config": {}}
    await async_client.post("/api/adapter/admin/contracts", json=v2_payload)

    # 4. Activate v1.1 - this should atomic flip v1.0 to DEPRECATED
    res_act_2 = await async_client.post("/api/adapter/admin/contracts/test_contract/versions/1.1/activate")
    assert res_act_2.status_code == 200
    assert res_act_2.json()["deprecated_version"] == "1.0"
    
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_crosswalk_crud(async_client: AsyncClient):
    from app.core.security import ActorContext, get_current_actor
    
    admin_ctx = ActorContext(
        actor_id="admin_1",
        roles=["system_admin"],
        allowed_nodes=["GLOBAL"]
    )
    app.dependency_overrides[get_current_actor] = lambda: admin_ctx

    payload = {
        "namespace": "dhis2_nodes",
        "source_value": "clx_123",
        "internal_id": "DIST-A"
    }
    
    res = await async_client.post("/api/adapter/admin/crosswalks", json=payload)
    assert res.status_code == 201
    
    res_get = await async_client.get("/api/adapter/admin/crosswalks?namespace=dhis2_nodes")
    assert res_get.status_code == 200
    assert len(res_get.json()) > 0
    assert res_get.json()[0]["source_value"] == "clx_123"

    app.dependency_overrides.clear()
