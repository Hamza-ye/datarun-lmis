import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import datetime

from app.main import app
from core.database import get_db
from app.ledger.schemas.command import TransactionType

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
async def test_validation_error_envelope(async_client: AsyncClient):
    """Submits a structurally invalid payload to trigger 422 RequestValidationError."""
    payload = {
        "source_system": "DHIS2", # missing mapping_profile and data
    }
    
    res = await async_client.post(
        "/api/adapter/inbox", 
        json=payload, 
        headers=auth_header("mock_external_system_token")
    )
    
    assert res.status_code == 422
    body = res.json()
    assert "error_code" in body
    assert body["error_code"] == "VALIDATION_ERROR"
    assert "correlation_id" in body
    assert "detail" in body
    assert res.headers.get("X-Correlation-ID") == body["correlation_id"]

@pytest.mark.asyncio
async def test_insufficient_stock_error_envelope(async_client: AsyncClient, db_session):
    """Submits an orchestrator command that pushes stock negative to trigger 400 InsufficientStockError."""
    cmd_payload = {
        "source_event_id": "API_ISSUE_NEG",
        "version_timestamp": 12345,
        "transaction_type": "ISSUE", # Issue decreases stock
        "node_id": "TEST_NODE",
        "item_id": "TEST_ITEM",
        "quantity": 50, # Node has 0, so this drops it to -50
        "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    
    res = await async_client.post(
        "/api/ledger/commands", 
        json=cmd_payload, 
        headers=auth_header("mock_ledger_worker_token")
    )
    
    assert res.status_code == 400
    body = res.json()
    assert body["error_code"] == "INSUFFICIENT_STOCK"
    assert "Cannot issue" in body["detail"] or "resulting in negative" in body["detail"]
    assert "correlation_id" in body
