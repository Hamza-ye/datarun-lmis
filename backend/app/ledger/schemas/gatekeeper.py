from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

from app.ledger.models.gatekeeper import ApprovalActionType, StagedCommandStatus

class SupervisorActionPayload(BaseModel):
    """Payload received from the UI when a supervisor clicks Approve or Reject"""
    actor_id: str = Field(..., description="The ID of the supervisor taking action.")
    action: ApprovalActionType
    comment: Optional[str] = Field(None, description="Reason for rejection or approval notes.")

class StagedCommandResponse(BaseModel):
    """Response returned to the UI to build the 'Tasks Awaiting Review' dashboard"""
    id: UUID
    source_event_id: str
    command_type: str
    stage_reason: str
    status: StagedCommandStatus
    node_id: str
    payload: Dict[str, Any]
    created_at: datetime
