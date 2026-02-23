import datetime
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import ActorContext, get_current_actor
from core.database import get_db
from app.kernel.models.registry import CommodityRegistry, NodeRegistry
from app.kernel.models.policy import SystemPolicy

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

# --- Commodities ---
@router.get("/commodities", response_model=List[Dict[str, Any]])
async def list_commodities(
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    actor.require_role("system_admin")
    stmt = select(CommodityRegistry)
    result = await db.execute(stmt)
    return [{"item_id": c.item_id, "code": c.code, "name": c.name, "base_unit": c.base_unit} for c in result.scalars().all()]

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
