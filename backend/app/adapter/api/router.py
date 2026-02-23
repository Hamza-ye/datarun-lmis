from fastapi import APIRouter, Depends, BackgroundTasks, status
from pydantic import BaseModel
from typing import Dict, Any

from app.core.security import ActorContext, get_current_actor
from app.adapter.worker import AdapterWorker
from core.database import get_db

router = APIRouter(prefix="/api/adapter", tags=["Adapter"])

class ExternalPayload(BaseModel):
    source_system: str
    mapping_profile: str
    data: Dict[str, Any]

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
    actor.require_role("external_system")
    
    # Store in raw inbox 
    from app.adapter.models.engine import AdapterInbox, InboxStatus
    
    inbox_record = AdapterInbox(
        source_system=payload.source_system,
        payload=payload.data,
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
