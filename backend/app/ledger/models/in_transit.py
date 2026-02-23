import enum
import uuid
from sqlalchemy import Column, String, Integer, DateTime, Enum, func
from sqlalchemy.types import Uuid

from core.database import Base

class InTransitStatus(str, enum.Enum):
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    STALE_AUTO_CLOSED = "STALE_AUTO_CLOSED"
    FAILED_AUTO_CLOSE = "FAILED_AUTO_CLOSE"

class InTransitRegistry(Base):
    """
    Table Name: ledger_in_transit_registry
    Purpose: Tracks stock that is actively moving between nodes.
    """
    __tablename__ = "ledger_in_transit_registry"

    transfer_id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_node_id = Column(String, index=True, nullable=False)
    dest_node_id = Column(String, index=True, nullable=False)
    item_id = Column(String, index=True, nullable=False)
    qty_shipped = Column(Integer, nullable=False)
    qty_received = Column(Integer, nullable=False, default=0)
    status = Column(Enum(InTransitStatus, name="in_transit_status"), nullable=False, default=InTransitStatus.OPEN)
    dispatched_at = Column(DateTime(timezone=True), nullable=False)
    auto_close_after = Column(DateTime(timezone=True), nullable=True) # Future cron mechanism
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class InternalDLQ(Base):
    """
    Table Name: ledger_internal_dlq
    Purpose: Catches failures in internal orchestration mechanisms (e.g., auto-receipt failing due to Area C rejection).
    """
    __tablename__ = "ledger_internal_dlq"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_process = Column(String, nullable=False) # e.g., 'AREA_D_AUTO_RECEIPT'
    reference_id = Column(String, index=True, nullable=False) # e.g., transfer_id
    error_message = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
