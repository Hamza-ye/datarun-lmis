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

@pytest.mark.asyncio
async def test_dlq_replay(async_client: AsyncClient, db_session):
    from app.core.security import ActorContext, get_current_actor
    from app.adapter.models.engine import AdapterInbox, InboxStatus
    import uuid
    
    admin_ctx = ActorContext(
        actor_id="admin_1",
        roles=["system_admin"],
        allowed_nodes=["GLOBAL"]
    )
    app.dependency_overrides[get_current_actor] = lambda: admin_ctx
    
    # 1. Seed a DLQ item
    bad_inbox = AdapterInbox(
        correlation_id=uuid.uuid4(),
        source_system="dhis2",
        mapping_id="test_mapping",
        mapping_version="1.0",
        payload={"bad": "data"},
        status=InboxStatus.DLQ,
        error_message="Missing required field"
    )
    db_session.add(bad_inbox)
    await db_session.commit()
    
    # 2. Replay the DLQ item with a fixed payload
    fixed_payload = {"good": "data", "fixed": True}
    res = await async_client.post(f"/api/adapter/admin/dlq/{str(bad_inbox.id)}/replay", json=fixed_payload)
    
    assert res.status_code == 201
    res_data = res.json()
    assert "new_inbox_id" in res_data
    assert res_data["correlation_id"] == str(bad_inbox.correlation_id)
    
    # 3. Verify the old record is REPROCESSED
    from sqlalchemy.future import select
    stmt_old = select(AdapterInbox).where(AdapterInbox.id == bad_inbox.id)
    old_record = (await db_session.execute(stmt_old)).scalars().first()
    assert old_record.status == InboxStatus.REPROCESSED
    
    # 4. Verify the new record is RECEIVED and linked to the parent
    stmt_new = select(AdapterInbox).where(AdapterInbox.id == uuid.UUID(res_data["new_inbox_id"]))
    new_record = (await db_session.execute(stmt_new)).scalars().first()
    assert new_record.status == InboxStatus.RECEIVED
    assert new_record.parent_inbox_id == bad_inbox.id
    assert new_record.payload == fixed_payload
    
    app.dependency_overrides.clear()
