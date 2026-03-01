import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import ActorContext, get_current_actor
from app.kernel.models.policy import SystemPolicy
from app.kernel.models.registry import CommodityRegistry, NodeRegistry
from core.database import get_db

router = APIRouter(prefix="/api/kernel", tags=["Shared Kernel"])

# --- Schemas ---
class CommodityCreate(BaseModel):
    item_id: str
    code: str
    name: str
    base_unit: str

class PolicyCreate(BaseModel):
    policy_key: str
    applies_to_node: str = "GLOBAL"
    applies_to_item: str = "ALL"
    config: Dict[str, Any]

class NodeCreate(BaseModel):
    node_id: str
    code: str
    name: str
    node_type: str
    parent_id: Optional[str] = None
    meta_data: Optional[Dict[str, Any]] = None

class NodeUpdate(BaseModel):
    name: Optional[str] = None
    node_type: Optional[str] = None
    parent_id: Optional[str] = None
    meta_data: Optional[Dict[str, Any]] = None

class NodeTopologyCorrection(BaseModel):
    new_parent_id: str
    effective_date: datetime.date

class NodeResolveRequest(BaseModel):
    node_ids: List[str]

# --- Commodities ---
@router.get("/commodities", response_model=List[Dict[str, Any]])
async def list_commodities(
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    actor.require_role("system_admin")
    stmt = select(CommodityRegistry)
    result = await db.execute(stmt)
    return [{"item_id": c.item_id, "code": c.code, "name": c.name, "base_unit": c.base_unit, "status": c.status} for c in result.scalars().all()]

@router.post("/commodities", status_code=status.HTTP_201_CREATED)
async def create_commodity(
    payload: CommodityCreate,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    actor.require_role("system_admin")
    # Base units are strictly immutable - you can only create new records
    c = CommodityRegistry(
        item_id=payload.item_id,
        code=payload.code,
        name=payload.name,
        base_unit=payload.base_unit,
        status="ACTIVE"
    )
    db.add(c)
    await db.commit()
    return {"message": "Commodity created"}

# --- Policies ---
@router.post("/policies", status_code=status.HTTP_201_CREATED)
async def create_or_update_policy(
    payload: PolicyCreate,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    actor.require_role("system_admin")
    # Upsert logic based on coordinates
    stmt = select(SystemPolicy).where(
        SystemPolicy.policy_key == payload.policy_key,
        SystemPolicy.applies_to_node == payload.applies_to_node,
        SystemPolicy.applies_to_item == payload.applies_to_item
    )
    existing = (await db.execute(stmt)).scalars().first()
    
    if existing:
        existing.config = payload.config
    else:
        p = SystemPolicy(
            policy_key=payload.policy_key,
            applies_to_node=payload.applies_to_node,
            applies_to_item=payload.applies_to_item,
            config=payload.config
        )
        db.add(p)
    await db.commit()
    return {"message": "Policy mapped"}

# --- Nodes (SCD Type 2) ---
@router.get("/nodes", response_model=List[Dict[str, Any]])
async def list_nodes(
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    actor.require_role("system_admin")
    stmt = select(NodeRegistry).where(NodeRegistry.valid_to == None)
    result = await db.execute(stmt)
    nodes = result.scalars().all()
    return [{
        "node_id": n.uid,
        "code": n.code,
        "name": n.name,
        "node_type": n.node_type,
        "parent_id": n.parent_id,
        "meta_data": n.meta_data,
        "valid_from": n.valid_from,
        "valid_to": n.valid_to
    } for n in nodes]

@router.post("/nodes/resolve", response_model=Dict[str, str])
async def resolve_nodes(
    payload: NodeResolveRequest,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    Efficiently resolves a list of Node UUIDs to their human-readable names.
    Ignores historical topology splits, just gets the name of the active record
    (or the latest record if deactivated).
    """
    if "system_admin" not in actor.roles and "ledger_supervisor" not in actor.roles:
        # A read-only basic check context (or allow all authenticated)
        pass 
        
    if not payload.node_ids:
        return {}
        
    unique_ids = list(set(payload.node_ids))
    
    stmt = select(NodeRegistry.uid, NodeRegistry.name).where(
        NodeRegistry.uid.in_(unique_ids),
        NodeRegistry.valid_to == None
    )
    result = await db.execute(stmt)
    resolved = {row.uid: row.name for row in result.all()}
    
    missing = set(unique_ids) - set(resolved.keys())
    if missing:
        stmt2 = select(NodeRegistry.uid, NodeRegistry.name).where(
            NodeRegistry.uid.in_(list(missing))
        )
        result2 = await db.execute(stmt2)
        for row in result2.all():
            if row.uid not in resolved:
                resolved[row.uid] = row.name
                
    return resolved

@router.get("/nodes/all", response_model=List[Dict[str, Any]])
async def list_all_nodes_historical(
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    actor.require_role("system_admin")
    stmt = select(NodeRegistry)
    result = await db.execute(stmt)
    nodes = result.scalars().all()
    return [{
        "node_id": n.uid,
        "code": n.code,
        "name": n.name,
        "node_type": n.node_type,
        "parent_id": n.parent_id,
        "meta_data": n.meta_data,
        "valid_from": n.valid_from,
        "valid_to": n.valid_to
    } for n in nodes]

@router.post("/nodes", status_code=status.HTTP_201_CREATED)
async def create_node(
    payload: NodeCreate,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    actor.require_role("system_admin")
    today_date = datetime.date.today()
    
    # Check current active existence
    stmt = select(NodeRegistry).where(
        NodeRegistry.uid == payload.node_id,
        NodeRegistry.valid_to == None
    )
    if (await db.execute(stmt)).scalars().first():
        raise HTTPException(status_code=400, detail="Active node with this UID already exists")
        
    n = NodeRegistry(
        uid=payload.node_id,
        code=payload.code,
        name=payload.name,
        node_type=payload.node_type,
        parent_id=payload.parent_id,
        meta_data=payload.meta_data,
        valid_from=today_date
    )
    db.add(n)
    await db.commit()
    return {"message": "Node created", "uid": n.uid}

@router.put("/nodes/{node_id}")
async def update_node(
    node_id: str,
    payload: NodeUpdate,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    SCD Type 2: Modifying a node (e.g., Parent ID changes) caps the 'valid_to' of the current record
    and inserts a new clone with the updated values. Never UPDATE an existing parent_id.
    """
    actor.require_role("system_admin")
    today_date = datetime.date.today()
    
    stmt = select(NodeRegistry).where(
        NodeRegistry.uid == node_id,
        NodeRegistry.valid_to == None
    )
    active_node = (await db.execute(stmt)).scalars().first()
    
    if not active_node:
        raise HTTPException(status_code=404, detail="Active Node not found")
        
    requires_history_split = False
    new_parent_id = active_node.parent_id
    
    if payload.parent_id is not None and payload.parent_id != active_node.parent_id:
        requires_history_split = True
        new_parent_id = payload.parent_id
        
    # If standard fields updated, we can just update in place for simple meta.
    # But if hierarchy changes, we must split to preserve math history.
    if requires_history_split:
        active_node.valid_to = today_date
        
        new_node = NodeRegistry(
            uid=active_node.uid,
            code=active_node.code,
            name=payload.name if payload.name else active_node.name,
            node_type=payload.node_type if payload.node_type else active_node.node_type,
            parent_id=new_parent_id,
            meta_data=payload.meta_data if payload.meta_data else active_node.meta_data,
            valid_from=today_date
        )
        db.add(new_node)
    else:
        if payload.name: active_node.name = payload.name
        if payload.node_type: active_node.node_type = payload.node_type
        if payload.meta_data: active_node.meta_data = payload.meta_data
        
    await db.commit()
    return {"message": "Node updated. Split created: " + str(requires_history_split)}

@router.post("/nodes/{node_id}/topology-correction")
async def historical_topology_correction(
    node_id: str,
    payload: NodeTopologyCorrection,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    SCD Type 2 Historical Rewrite: 
    Finds the active record at the `effective_date`, caps its `valid_to`, 
    and inserts a new record with the new `parent_id` spanning `effective_date` 
    to the original `valid_to` (which could be NULL or a bounded date if another split exists).
    """
    actor.require_role("system_admin")
    
    from sqlalchemy import or_
    
    # 1. Idempotency / Double-Click Guard: Check if the exact split requested ALREADY exists
    stmt_check = select(NodeRegistry).where(
        NodeRegistry.uid == node_id,
        NodeRegistry.parent_id == payload.new_parent_id
    )
    for existing_split in (await db.execute(stmt_check)).scalars().all():
        if str(existing_split.valid_from)[:10] == str(payload.effective_date)[:10]:
            return {"message": "Historical topology already corrected for this date."}
        
    # 2. Find the specific row that was "active" on the effective date
    stmt = select(NodeRegistry).where(
        NodeRegistry.uid == node_id,
        NodeRegistry.valid_from <= payload.effective_date,
        or_(
            NodeRegistry.valid_to == None,
            NodeRegistry.valid_to > payload.effective_date
        )
    ).with_for_update() # ROW LEVEL LOCK FOR IDEMPOTENCY
    historical_node = (await db.execute(stmt)).scalars().first()
    
    if not historical_node:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot apply correction: No registry record active on {payload.effective_date}"
        )
        
    if historical_node.parent_id == payload.new_parent_id:
        return {"message": "No correction needed. Parent matches."}
        
    original_valid_to = historical_node.valid_to
    
    # Cap the historical record
    historical_node.valid_to = payload.effective_date
    
    # Insert the new "middle" or "current" record
    corrected_node = NodeRegistry(
        uid=historical_node.uid,
        code=historical_node.code,
        name=historical_node.name,
        node_type=historical_node.node_type,
        parent_id=payload.new_parent_id,
        meta_data=historical_node.meta_data,
        valid_from=payload.effective_date,
        valid_to=original_valid_to # If it was active, this is None. If it was already split, this preserves the cap.
    )
    
    db.add(corrected_node)
    await db.commit()
    
    return {"message": "Historical topology corrected"}
