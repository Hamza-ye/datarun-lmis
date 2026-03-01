import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger.models.event_store import InventoryEvent, StockBalance
from app.ledger.schemas.command import TransactionType
from app.main import app
from core.database import get_db


@pytest_asyncio.fixture
async def seed_reporting_data(db_session: AsyncSession):
    # Seed Balances for two different clinics
    b1 = StockBalance(node_id="CLINIC_A", item_id="PARAM-01", quantity=500)
    b2 = StockBalance(node_id="CLINIC_B", item_id="PARAM-01", quantity=200)
    
    # Seed History for Clinic A
    e1 = InventoryEvent(
        source_event_id="EVT-01", 
        transaction_type=TransactionType.RECEIPT.value,
        node_id="CLINIC_A",
        item_id="PARAM-01",
        quantity=500,
        running_balance=500,
        occurred_at=datetime.datetime.now(datetime.timezone.utc)
    )
    
    db_session.add_all([b1, b2, e1])
    await db_session.flush()

@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession):
    """Test Client with DB Override"""
    app.dependency_overrides[get_db] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()

def auth_header(token: str):
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_get_balances_rbac_filtering(async_client: AsyncClient, seed_reporting_data):
    """
    Simulates a JWT token belonging to a user from District A.
    They should only see Clinic A's stock, not Clinic B's.
    Note: testing infrastructure uses 'mock_supervisor_token' from security.py 
    which has allowed_nodes=["DIST-A", "CLINIC_A", "CLINIC_1"] in this scenario.
    """
    
    # We need to temporarily hack the mock token to return CLINIC_A
    # The actual implementation in security.py returns CLINIC_1.
    # Let's override it cleanly for this test by mocking security.get_current_actor
    from app.core.security import ActorContext, get_current_actor
    
    def override_actor_clinic_a():
        return ActorContext(actor_id="test", roles=["ledger_viewer"], allowed_nodes=["CLINIC_A"])
        
    app.dependency_overrides[get_current_actor] = override_actor_clinic_a
    
    response = await async_client.get("/api/ledger/balances")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 1
    assert data[0]["node_id"] == "CLINIC_A"
    assert data[0]["quantity"] == 500
    
    app.dependency_overrides.pop(get_current_actor, None)

@pytest.mark.asyncio
async def test_get_balances_global_admin(async_client: AsyncClient, seed_reporting_data):
    """A global admin should see everything."""
    from app.core.security import ActorContext, get_current_actor
    
    def override_actor_admin():
        return ActorContext(actor_id="admin", roles=["GLOBAL_ADMIN"], allowed_nodes=[])
        
    app.dependency_overrides[get_current_actor] = override_actor_admin
    
    response = await async_client.get("/api/ledger/balances")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 2 # Should see both Clinic A and Clinic B
    
    app.dependency_overrides.pop(get_current_actor, None)

@pytest.mark.asyncio
async def test_get_history_forbidden(async_client: AsyncClient, seed_reporting_data):
    """If a generic user asks for history of a clinic they don't own, 403."""
    from app.core.security import ActorContext, get_current_actor
    
    def override_actor_clinic_c():
        return ActorContext(actor_id="test", roles=["ledger_viewer"], allowed_nodes=["CLINIC_C"])
        
    app.dependency_overrides[get_current_actor] = override_actor_clinic_c
    
    response = await async_client.get("/api/ledger/history/CLINIC_A/PARAM-01")
    assert response.status_code == 403
    
    app.dependency_overrides.pop(get_current_actor, None)
