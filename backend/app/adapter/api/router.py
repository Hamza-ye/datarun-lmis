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
    correlation_id: str | None = None
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
    import uuid
    
    inbox_record = AdapterInbox(
        correlation_id=uuid.UUID(payload.correlation_id) if payload.correlation_id else uuid.uuid4(),
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
    
    return {"message": "Payload accepted for processing", "inbox_id": str(inbox_record.id), "correlation_id": str(inbox_record.correlation_id)}

@router.post("/admin/dlq/{inbox_id}/replay", status_code=status.HTTP_201_CREATED)
async def replay_dlq_item(
    inbox_id: str,
    payload_edit: Dict[str, Any],
    actor: ActorContext = Depends(get_current_actor),
    db_session=Depends(get_db)
):
    """
    Step 5 of the architecture: Reprocess a failed DLQ item with a corrected payload.
    Creates a new RECEIVED inbox record linked to the previous failed one.
    """
    from fastapi import HTTPException
    import uuid
    from sqlalchemy.future import select
    from app.adapter.models.engine import AdapterInbox, InboxStatus
    
    if "system_admin" not in actor.roles:
        raise HTTPException(status_code=403, detail="Only system admins can replay DLQ items")
        
    try:
        inbox_uuid = uuid.UUID(inbox_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid inbox_id format. Must be UUID.")
        
    stmt = select(AdapterInbox).where(AdapterInbox.id == inbox_uuid, AdapterInbox.status == InboxStatus.DLQ)
    old_record = (await db_session.execute(stmt)).scalars().first()
    
    if not old_record:
        raise HTTPException(status_code=404, detail="DLQ item not found or not in DLQ state")
        
    # Mark old as reprocessed
    old_record.status = InboxStatus.REPROCESSED
    
    # Create new record
    new_record = AdapterInbox(
        correlation_id=old_record.correlation_id,
        parent_inbox_id=old_record.id,
        source_system=old_record.source_system,
        mapping_id=old_record.mapping_id,
        mapping_version=old_record.mapping_version,
        source_event_id=old_record.source_event_id,
        payload=payload_edit,
        status=InboxStatus.RECEIVED
    )
    db_session.add(new_record)
    await db_session.commit()
    await db_session.refresh(new_record)
    
    return {
        "message": "Replay scheduled successfully",
        "new_inbox_id": str(new_record.id),
        "correlation_id": str(new_record.correlation_id)
    }

@router.get("/admin/dlq")
async def get_dlq_items(
    actor: ActorContext = Depends(get_current_actor),
    db_session=Depends(get_db)
):
    from fastapi import HTTPException
    from sqlalchemy.future import select
    from app.adapter.models.engine import AdapterInbox, InboxStatus
    
    if "system_admin" not in actor.roles:
        raise HTTPException(status_code=403, detail="Only system admins can view the DLQ")
        
    stmt = select(AdapterInbox).where(AdapterInbox.status == InboxStatus.DLQ).order_by(AdapterInbox.created_at.desc())
    records = (await db_session.execute(stmt)).scalars().all()
    
    return [
        {
            "id": str(r.id),
            "correlation_id": str(r.correlation_id) if r.correlation_id else None,
            "source_system": r.source_system,
            "error_message": r.error_message,
            "payload": r.payload,
            "created_at": r.created_at.isoformat() if r.created_at else None
        } for r in records
    ]
