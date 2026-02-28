from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.composition.service import CompositionService

router = APIRouter(prefix="/api/bff", tags=["BFF / API Composition"])

@router.get("/node-overview/{node_id}")
async def get_node_overview(
    node_id: str,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db)
):
    """
    Composed endpoint for the Dashboard.
    Aggregates Kernel (Metadata), Ledger (Stock), and Adapter (Sync Status).
    """
    # Enforce basic node access at the BFF level
    if "GLOBAL" not in actor.allowed_nodes and node_id not in actor.allowed_nodes:
        raise HTTPException(status_code=403, detail="No access to this node.")
        
    return await CompositionService.get_node_overview(db, actor, node_id)
