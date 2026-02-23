import json
from uuid import UUID
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import ActorContext, get_current_actor
from core.database import get_db
from app.adapter.models.engine import MappingContract, AdapterCrosswalk, DeadLetterQueue, InboxStatus
from pydantic import BaseModel

router = APIRouter(prefix="/api/adapter/admin", tags=["Adapter Admin"])

# --- Schemas ---
class ContractCreate(BaseModel):
    id: str
    version: str
    dsl_config: Dict[str, Any]

class CrosswalkCreate(BaseModel):
    namespace: str
    source_value: str
    internal_id: str
    metadata_json: Optional[Dict[str, Any]] = None

class DLQReplayRequest(BaseModel):
    is_dry_run: bool = True

# --- Mapping Contracts ---
@router.get("/contracts", response_model=List[Dict[str, Any]])
async def list_contracts(
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    actor.require_role("system_admin")
    stmt = select(MappingContract)
    result = await db.execute(stmt)
    contracts = result.scalars().all()
    return [{"id": c.id, "version": c.version, "status": c.status, "created_at": c.created_at} for c in contracts]

@router.post("/contracts", status_code=status.HTTP_201_CREATED)
async def create_contract(
    payload: ContractCreate,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    actor.require_role("system_admin")
    
    # Check if a contract with this ID and Version already exists
    stmt = select(MappingContract).where(
        MappingContract.id == payload.id,
        MappingContract.version == payload.version
    )
    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Contract version already exists.")

    new_contract = MappingContract(
        id=payload.id,
        version=payload.version,
        dsl_config=payload.dsl_config,
        status="DRAFT" # Always start as DRAFT
    )
    db.add(new_contract)
    await db.commit()
    return {"message": "Draft Contract Created", "id": payload.id, "version": payload.version}

@router.post("/contracts/{contract_id}/versions/{version}/activate")
async def activate_contract(
    contract_id: str,
    version: str,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    Implements the 'Atomic Flip' rule.
    """
    actor.require_role("system_admin")
    
    # 1. Find the target contract
    stmt = select(MappingContract).where(
        MappingContract.id == contract_id,
        MappingContract.version == version
    )
    target = (await db.execute(stmt)).scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Contract version not found")
        
    # 2. Find any currently ACTIVE version and DEPRECATE it
    stmt_active = select(MappingContract).where(
        MappingContract.id == contract_id,
        MappingContract.status == "ACTIVE"
    )
    current_active = (await db.execute(stmt_active)).scalars().first()
    if current_active:
        current_active.status = "DEPRECATED"
        
    # 3. ACTIVATE the new one
    target.status = "ACTIVE"
    await db.commit()
    
    return {"message": "Contract Activated", "deprecated_version": current_active.version if current_active else None}


# --- Crosswalks ---
@router.get("/crosswalks", response_model=List[Dict[str, Any]])
async def list_crosswalks(
    namespace: Optional[str] = None,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    actor.require_role("system_admin")
    stmt = select(AdapterCrosswalk)
    if namespace:
        stmt = stmt.where(AdapterCrosswalk.namespace == namespace)
    result = await db.execute(stmt)
    return [{"id": str(c.id), "namespace": c.namespace, "source_value": c.source_value, "internal_id": c.internal_id} for c in result.scalars().all()]

@router.post("/crosswalks", status_code=status.HTTP_201_CREATED)
async def create_crosswalk(
    payload: CrosswalkCreate,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    actor.require_role("system_admin")
    cw = AdapterCrosswalk(
        namespace=payload.namespace,
        source_value=payload.source_value,
        internal_id=payload.internal_id,
        metadata_json=payload.metadata_json
    )
    db.add(cw)
    await db.commit()
    return {"message": "Crosswalk created", "id": str(cw.id)}


# --- Dead Letter Queue ---
@router.get("/dlq", response_model=List[Dict[str, Any]])
async def get_dlq(
    status_filter: Optional[str] = "UNRESOLVED",
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    actor.require_role("system_admin")
    stmt = select(DeadLetterQueue)
    if status_filter:
        stmt = stmt.where(DeadLetterQueue.status == status_filter)
    result = await db.execute(stmt)
    dlqs = result.scalars().all()
    # Simplified return for MVP
    return [{"id": str(d.id), "inbox_id": str(d.inbox_id), "error_reason": d.error_reason, "status": d.status} for d in dlqs]
