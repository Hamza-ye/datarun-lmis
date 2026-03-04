import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.domain.policy.resolver import PolicyResolver
from app.kernel.models.policy import SystemPolicy
from app.kernel.models.registry import CommodityPackage, CommodityRegistry, NodeRegistry

# --- Fixtures ---


@pytest_asyncio.fixture
async def seed_kernel_data(db_session: AsyncSession):
    """
    Seeds a hierarchy:
      National WH (WH-01, type=WH)
        ├── District A (DIST-A, type=HF)
        │     └── Clinic 1 (CL-01, type=HF)
        └── MU Alpha (MU-01, type=MU)
    """
    # Nodes
    wh = NodeRegistry(uid="WH-01", code="WH", name="National Warehouse", node_type="WH")
    dist = NodeRegistry(
        uid="DIST-A", code="DA", name="District A", node_type="HF", parent_id="WH-01"
    )
    clinic = NodeRegistry(
        uid="CL-01", code="C1", name="Clinic 1", node_type="HF", parent_id="DIST-A"
    )
    mu = NodeRegistry(
        uid="MU-01", code="MU1", name="MU Alpha", node_type="MU", parent_id="DIST-A"
    )

    db_session.add_all([wh, dist, clinic, mu])

    # Commodities
    param = CommodityRegistry(
        item_id="ITEM-01", code="PARAM", name="Paracetamol", base_unit="TABLET"
    )
    amox = CommodityRegistry(
        item_id="ITEM-02", code="AMOX", name="Amoxicillin", base_unit="CAPSULE"
    )

    db_session.add_all([param, amox])
    await db_session.flush()


@pytest_asyncio.fixture
async def seed_full_policy_data(db_session: AsyncSession, seed_kernel_data):
    """
    Seeds policies across all 6 resolution levels for 'auto_receive_days':
      Level 6: Global (NULL + NULL)                → 14 days
      Level 5: Category (NULL + category:DRUGS)     → 10 days
      Level 4: Node type (type:MU + NULL)           → 21 days
      Level 3: Node type + item (type:MU + ITEM-01) → 18 days
      Level 2: Specific node (DIST-A + NULL)        → 7 days
      Level 1: Specific node + item (CL-01 + ITEM-01) → 3 days
    """
    policies = [
        # Level 6: Global default
        SystemPolicy(
            policy_key="auto_receive_days",
            applies_to_node=None,
            applies_to_item=None,
            config={"days": 14},
        ),
        # Level 5: Category-scoped
        SystemPolicy(
            policy_key="auto_receive_days",
            applies_to_node=None,
            applies_to_item="category:DRUGS",
            config={"days": 10},
        ),
        # Level 4: Node-type global
        SystemPolicy(
            policy_key="auto_receive_days",
            applies_to_node="type:MU",
            applies_to_item=None,
            config={"days": 21},
        ),
        # Level 3: Node-type + specific item
        SystemPolicy(
            policy_key="auto_receive_days",
            applies_to_node="type:MU",
            applies_to_item="ITEM-01",
            config={"days": 18},
        ),
        # Level 2: Specific node, any item
        SystemPolicy(
            policy_key="auto_receive_days",
            applies_to_node="DIST-A",
            applies_to_item=None,
            config={"days": 7},
        ),
        # Level 1: Exact match
        SystemPolicy(
            policy_key="auto_receive_days",
            applies_to_node="CL-01",
            applies_to_item="ITEM-01",
            config={"days": 3},
        ),
    ]

    db_session.add_all(policies)
    await db_session.flush()


# --- Policy Resolver Tests ---


@pytest.mark.asyncio
async def test_level_1_exact_match(db_session: AsyncSession, seed_full_policy_data):
    """Level 1: Specific node + specific item → highest precedence."""
    result = await PolicyResolver.get_policy(
        db_session, "auto_receive_days", "CL-01", "ITEM-01"
    )
    assert result["days"] == 3


@pytest.mark.asyncio
async def test_level_2_node_any_item(db_session: AsyncSession, seed_full_policy_data):
    """Level 2: Specific node + NULL.
    CL-01 does NOT have a rule for ITEM-02. It should NOT fallback to its own node with NULL item
    (there is no CL-01 + NULL policy). Instead it should check parent (DIST-A + ITEM-02 → miss),
    then DIST-A + NULL → hit: 7 days.
    """
    result = await PolicyResolver.get_policy(
        db_session, "auto_receive_days", "CL-01", "ITEM-02"
    )
    assert result["days"] == 7


@pytest.mark.asyncio
async def test_level_2_direct_node_null(
    db_session: AsyncSession, seed_full_policy_data
):
    """Level 2: Querying DIST-A directly with an unknown item falls to DIST-A + NULL → 7 days."""
    result = await PolicyResolver.get_policy(
        db_session, "auto_receive_days", "DIST-A", "ITEM-99"
    )
    assert result["days"] == 7


@pytest.mark.asyncio
async def test_level_3_node_type_with_item(
    db_session: AsyncSession, seed_full_policy_data
):
    """Level 3: Node type + specific item.
    MU-01 has no specific node policy. Falls to type:MU + ITEM-01 → 18 days.
    """
    result = await PolicyResolver.get_policy(
        db_session, "auto_receive_days", "MU-01", "ITEM-01"
    )
    assert result["days"] == 18


@pytest.mark.asyncio
async def test_level_4_node_type_any_item(
    db_session: AsyncSession, seed_full_policy_data
):
    """Level 4: Node type + NULL.
    MU-01 with ITEM-02: no specific node policy, no type:MU+ITEM-02. Falls to type:MU + NULL → 21 days.
    """
    result = await PolicyResolver.get_policy(
        db_session, "auto_receive_days", "MU-01", "ITEM-02"
    )
    assert result["days"] == 21


@pytest.mark.asyncio
async def test_level_6_global_fallback(db_session: AsyncSession, seed_full_policy_data):
    """Level 6: Global (NULL + NULL).
    A completely unknown node should hit global fallback → 14 days.
    """
    result = await PolicyResolver.get_policy(
        db_session, "auto_receive_days", "UNKNOWN_NODE", "ITEM-99"
    )
    assert result["days"] == 14


@pytest.mark.asyncio
async def test_global_query_no_node_no_item(
    db_session: AsyncSession, seed_full_policy_data
):
    """Querying with no node and no item should return global → 14 days."""
    result = await PolicyResolver.get_policy(
        db_session, "auto_receive_days", None, None
    )
    assert result["days"] == 14


@pytest.mark.asyncio
async def test_category_scoped_policy(db_session: AsyncSession, seed_full_policy_data):
    """Level 5: NULL + category:DRUGS.
    When explicitly queried with the category prefix, should resolve.
    """
    result = await PolicyResolver.get_policy(
        db_session, "auto_receive_days", None, "category:DRUGS"
    )
    assert result["days"] == 10


@pytest.mark.asyncio
async def test_missing_policy_returns_none(db_session: AsyncSession):
    """A policy key that doesn't exist at all should safely return None."""
    result = await PolicyResolver.get_policy(
        db_session, "non_existent_policy", "CL-01", "ITEM-01"
    )
    assert result is None


@pytest.mark.asyncio
async def test_parent_fallback_chain(db_session: AsyncSession, seed_kernel_data):
    """Test that resolution walks up the parent tree.
    Seed: Only WH-01 has a policy. CL-01 → DIST-A → WH-01.
    """
    policy = SystemPolicy(
        policy_key="negative_stock_behavior",
        applies_to_node="WH-01",
        applies_to_item=None,
        config={"behavior": "BLOCK"},
    )
    db_session.add(policy)
    await db_session.flush()

    # CL-01 should walk up: CL-01 → miss, DIST-A → miss, WH-01 → hit
    result = await PolicyResolver.get_policy(
        db_session, "negative_stock_behavior", "CL-01", "ITEM-01"
    )
    assert result["behavior"] == "BLOCK"


# --- CommodityPackage Tests ---


@pytest.mark.asyncio
async def test_commodity_package_creation(db_session: AsyncSession, seed_kernel_data):
    """CommodityPackage should link to CommodityRegistry via item_id."""
    pkg = CommodityPackage(
        package_id="PKG-100",
        item_id="ITEM-01",
        uom_name="BOX_100",
        base_unit_multiplier=100,
    )
    db_session.add(pkg)
    await db_session.flush()

    assert pkg.package_id == "PKG-100"
    assert pkg.base_unit_multiplier == 100
    assert pkg.is_active is True  # default


@pytest.mark.asyncio
async def test_commodity_package_inactive(db_session: AsyncSession, seed_kernel_data):
    """Inactive packages should be soft-deprecated, not deleted."""
    pkg = CommodityPackage(
        package_id="PKG-OLD",
        item_id="ITEM-01",
        uom_name="BOX_50",
        base_unit_multiplier=50,
        is_active=False,
    )
    db_session.add(pkg)
    await db_session.flush()

    assert pkg.is_active is False
