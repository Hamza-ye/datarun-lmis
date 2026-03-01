import enum
import uuid

from sqlalchemy import JSON, Column, DateTime, Enum, String, func
from sqlalchemy.types import Uuid

from core.database import Base


class StagedCommandStatus(str, enum.Enum):
    AWAITING = "AWAITING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class ApprovalActionType(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"

class StagedCommand(Base):
    """
    Table Name: ledger_staged_commands
    Purpose: A durable 'Waiting Room' for high-impact Ledger transactions.
    """
    __tablename__ = "ledger_staged_commands"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_event_id = Column(String, index=True, nullable=False) # FK to Idempotency Registry
    command_type = Column(String, nullable=False) # e.g., ADJUSTMENT, STOCK_COUNT
    payload = Column(JSON, nullable=False) # The normalized LedgerCommand
    stage_reason = Column(String, nullable=False) # e.g., "Manual Entry", "Threshold Exceeded"
    status = Column(Enum(StagedCommandStatus, name="staged_command_status"), nullable=False, default=StagedCommandStatus.AWAITING)
    node_id = Column(String, index=True, nullable=False) # Facility/MU for RBAC filtering
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ApprovalAudit(Base):
    """
    Table Name: ledger_approval_audit
    Purpose: The immutable legal record of who approved/rejected what.
    """
    __tablename__ = "ledger_approval_audit"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    staged_command_id = Column(Uuid(as_uuid=True), index=True, nullable=False)
    actor_id = Column(String, nullable=False) # ID of supervisor
    action = Column(Enum(ApprovalActionType, name="approval_action_type"), nullable=False)
    comment = Column(String, nullable=True) # Justification
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())
