import enum
import uuid
from sqlalchemy import Column, String, Enum, BigInteger, DateTime, func, JSON
from sqlalchemy.types import Uuid

from core.database import Base

class IdempotencyStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    STAGED = "STAGED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class IdempotencyRegistry(Base):
    """
    Table Name: ledger_idempotency_registry
    Purpose: Ensure every field submission results in exactly one ledger operation.
    """
    __tablename__ = "ledger_idempotency_registry"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_event_id = Column(String, unique=True, index=True, nullable=False)
    status = Column(Enum(IdempotencyStatus, name="idempotency_status"), nullable=False, default=IdempotencyStatus.PROCESSING)
    version_timestamp = Column(BigInteger, nullable=False)
    result_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
