import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app

@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

def auth_header(token: str):
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_get_current_user_context_supervisor(async_client: AsyncClient):
    res = await async_client.get(
        "/api/auth/me", 
        headers=auth_header("mock_supervisor_token")
    )
    
    assert res.status_code == 200
    body = res.json()
    assert body["actor_id"] == "user_supervisor_99"
    assert "ledger_supervisor" in body["roles"]
    assert "DIST-A" in body["allowed_nodes"]

@pytest.mark.asyncio
async def test_get_current_user_context_unauthorized(async_client: AsyncClient):
    res = await async_client.get("/api/auth/me")
    assert res.status_code == 401

@pytest.mark.asyncio
async def test_get_current_user_context_invalid_token(async_client: AsyncClient):
    res = await async_client.get(
        "/api/auth/me",
        headers=auth_header("totally_fake_token")
    )
    assert res.status_code == 401
