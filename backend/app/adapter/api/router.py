from fastapi import APIRouter, Depends, BackgroundTasks, status
from pydantic import BaseModel
from typing import Dict, Any

from app.core.security import ActorContext, get_current_actor
from app.adapter.worker import AdapterWorker
from core.database import get_db

router = APIRouter(prefix="/api/adapter", tags=["Adapter"])

class ExternalPayload(BaseModel):
    source_system: str | None = None
    mapping_profile: str
    source_event_id: str | None = None
    dry_run: bool = False
    payload: Dict[str, Any]

@router.post("/inbox", status_code=status.HTTP_202_ACCEPTED)
async def receive_external_payload(
    payload: ExternalPayload,
    background_tasks: BackgroundTasks,
    actor: ActorContext = Depends(get_current_actor),
    db_session=Depends(get_db)
):
    """
    Step 1 of the architecture: External systems submit their dirty DHIS2/eLMIS payloads here.
    Because this is an asynchronous messaging pattern, we return 202 Accepted immediately 
    and let the Adapter Worker chew through the payload in the background.
    """
    from fastapi import HTTPException
    
    if "external_system" not in actor.roles and "system_admin" not in actor.roles:
        raise HTTPException(status_code=403, detail="Actor lacks required role: external_system or system_admin")
    
    from sqlalchemy.future import select
    from fastapi import HTTPException
    from app.adapter.models.engine import AdapterInbox, InboxStatus, MappingContract
    from app.adapter.schemas.dsl import MappingContractDSL
    from app.adapter.engine.mapper import MapperEngine
    
    # Route matching: resolve active contract
    stmt = select(MappingContract).where(
        MappingContract.id == payload.mapping_profile,
        MappingContract.status == "ACTIVE"
    )
    contract = (await db_session.execute(stmt)).scalars().first()
    
    if not contract:
        raise HTTPException(status_code=400, detail=f"No active mapping contract found for profile '{payload.mapping_profile}'")
    
    if payload.dry_run:
        # Instantly resolve and map payload for preview without saving to DB
        dsl = MappingContractDSL(**contract.dsl_config)
        try:
            commands = await MapperEngine.run(db_session, payload.payload, contract=dsl)
        except Exception as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=str(e))
            
        return {
            "message": "Dry-run successful", 
            "dry_run": True, 
            "mapped_payloads": commands
        }
    
    # Live Mutation: Store in raw inbox 
    inbox_record = AdapterInbox(
        source_system=payload.source_system or "unknown",
        mapping_id=contract.id,
        mapping_version=contract.version,
        source_event_id=payload.source_event_id,
        payload=payload.payload,
        status=InboxStatus.RECEIVED
    )
    db_session.add(inbox_record)
    await db_session.commit()
    await db_session.refresh(inbox_record)
    
    # Trigger background worker
    # We pass the ID, not the SQLAlchemy object, because SQLAlchemy sessions aren't thread safe across async boundaries
    # background_tasks.add_task(AdapterWorker.process_single, session, inbox_record)
    # NOTE: Background task execution requires actual Session scope management which is tricky in pure FastAPI dependency injection. 
    # Usually this is handled by Celery or APScheduler. 
    # For now, we will just return the 202. The worker can be triggered via a separate test endpoint or cron.
    
    return {"message": "Payload accepted for processing", "inbox_id": str(inbox_record.id)}
