import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.composition.service import CompositionService
from app.core.security import ActorContext
from app.kernel.models.registry import NodeRegistry
from app.ledger.models.event_store import StockBalance
from app.adapter.models.engine import AdapterInbox, InboxStatus

@pytest.mark.asyncio
async def test_bff_node_overview_success(db_session: AsyncSession):
    # 1. Setup Data across 3 domains
    node_id = "facility_001"
    
    # Kernel
    db_session.add(NodeRegistry(
        uid=node_id, 
        name="Test Clinic", 
        node_type="HF", 
        code="TC01"
    ))
    
    # Ledger
    db_session.add(StockBalance(
        node_id=node_id, 
        item_id="ITEM1", 
        quantity=100
    ))
    
    # Adapter
    db_session.add(AdapterInbox(
        source_system="S1", 
        mapping_id="M1", 
        mapping_version="v1", 
        status=InboxStatus.RECEIVED, 
        payload={"dummy": "data"}
    ))
    
    await db_session.commit()

    # 2. Mock Actor (Global Access)
    actor = ActorContext(
        actor_id="test_user", 
        roles=["system_admin"], 
        allowed_nodes=["GLOBAL"]
    )

    # 3. Call Service
    result = await CompositionService.get_node_overview(db_session, actor, node_id)

    # 4. Assert Structure and Data
    assert result["node"]["status"] == "ok"
    assert result["node"]["data"]["name"] == "Test Clinic"
    
    assert result["stock"]["status"] == "ok"
    assert len(result["stock"]["data"]) == 1
    assert result["stock"]["data"][0].quantity == 100
    
    assert result["pending_sync"]["status"] == "ok"
    assert result["pending_sync"]["count"] == 1
    assert len(result["pending_sync"]["latest"]) == 1
