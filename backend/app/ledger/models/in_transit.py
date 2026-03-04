import enum
import uuid

from sqlalchemy import BigInteger, Column, DateTime, Enum, String, func
from sqlalchemy.types import Uuid

from core.database import Base


class InTransitStatus(str, enum.Enum):
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    STALE_AUTO_CLOSED = "STALE_AUTO_CLOSED"
    FAILED_AUTO_CLOSE = "FAILED_AUTO_CLOSE"
    LOST_IN_TRANSIT = "LOST_IN_TRANSIT"  # Was 'LOST' — renamed to match docs


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
    qty_shipped = Column(BigInteger, nullable=False)
    qty_received = Column(BigInteger, nullable=False, default=0)
    status = Column(
        Enum(InTransitStatus, name="in_transit_status"),
        nullable=False,
        default=InTransitStatus.OPEN,
    )
    dispatched_at = Column(DateTime(timezone=True), nullable=False)
    auto_close_after = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InternalDLQ(Base):
    """
    Table Name: ledger_internal_dlq
    Purpose: Catches failures in internal orchestration (e.g., auto-receipt failing due to Event Store rejection).
    """

    __tablename__ = "ledger_internal_dlq"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_process = Column(String, nullable=False)  # e.g., 'AREA_D_AUTO_RECEIPT'
    reference_id = Column(String, index=True, nullable=False)
    error_message = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
