import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.kernel.models.registry import NodeRegistry, CommodityRegistry
from app.kernel.models.policy import SystemPolicy
from app.kernel.domain.policy.resolver import PolicyResolver

@pytest_asyncio.fixture
async def seed_kernel_data(db_session: AsyncSession):
    """
    Seeds a hierarchy:
    GLOBAL
      |-- NATIONAL_WH (WH-01)
            |-- DISTRICT_A (DIST-A)
                  |-- CLINIC_1 (CL-01)
    """
    
    # Nodes
    wh = NodeRegistry(uid="WH-01", code="WH", name="National Warehouse", node_type="WAREHOUSE")
    dist = NodeRegistry(uid="DIST-A", code="DA", name="District A", node_type="DISTRICT", parent_id="WH-01")
    clinic = NodeRegistry(uid="CL-01", code="C1", name="Clinic 1", node_type="CLINIC", parent_id="DIST-A")
    
    db_session.add_all([wh, dist, clinic])
    
    # Commodities
    param = CommodityRegistry(item_id="ITEM-01", code="PARAM", name="Paracetamol", base_unit="TABLET")
    amox = CommodityRegistry(item_id="ITEM-02", code="AMOX", name="Amoxicillin", base_unit="CAPSULE")
    
    db_session.add_all([param, amox])
    
    # Policies
    # 1. Global Default
    p_global = SystemPolicy(policy_key="auto_receive_days", applies_to_node="GLOBAL", applies_to_item="ALL", config={"days": 14})
    
    # 2. National Override for ALL items
    p_national = SystemPolicy(policy_key="auto_receive_days", applies_to_node="WH-01", applies_to_item="ALL", config={"days": 30})
    
    # 3. District Override for ALL items
    p_dist = SystemPolicy(policy_key="auto_receive_days", applies_to_node="DIST-A", applies_to_item="ALL", config={"days": 7})
    
    # 4. Clinic Specific Override for ONE item
    p_clinic_item = SystemPolicy(policy_key="auto_receive_days", applies_to_node="CL-01", applies_to_item="ITEM-01", config={"days": 3})
    
    db_session.add_all([p_global, p_national, p_dist, p_clinic_item])
    await db_session.flush()

@pytest.mark.asyncio
async def test_policy_resolver_hierarchy(db_session: AsyncSession, seed_kernel_data):
    """
    Tests the fallback engine of configuration as data.
    """
    
    # Test 1: Exact Match (Node + Item)
    # Clinic 1 explicitly set Paracetamol (ITEM-01) to 3 days.
    res1 = await PolicyResolver.get_policy(db_session, "auto_receive_days", "CL-01", "ITEM-01")
    assert res1["days"] == 3
    
    # Test 2: Fallback to Parent Node (Node + ALL)
    # Clinic 1 does NOT have a specific rule for Amoxicillin (ITEM-02).
    # It should fallback to its parent, District A, which overrides ALL to 7 days.
    res2 = await PolicyResolver.get_policy(db_session, "auto_receive_days", "CL-01", "ITEM-02")
    assert res2["days"] == 7
    
    # Test 3: Fallback further up the tree
    # District doesn't have a rule for ITEM-03 (imaginary). Will use District's ALL rule.
    res3 = await PolicyResolver.get_policy(db_session, "auto_receive_days", "DIST-A", "ITEM-03")
    assert res3["days"] == 7
    
    # Test 4: Global Fallback
    # A completely disconnected node should hit the GLOBAL ALL fallback (14 days).
    res4 = await PolicyResolver.get_policy(db_session, "auto_receive_days", "UNKNOWN_NODE", "ITEM-01")
    assert res4["days"] == 14

@pytest.mark.asyncio
async def test_missing_policy(db_session: AsyncSession):
    # Should safely return None if the policy key just doesn't exist
    res = await PolicyResolver.get_policy(db_session, "non_existent_policy", "CL-01", "ITEM-01")
    assert res is None
