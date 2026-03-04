import uuid

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.types import Uuid

from core.database import Base


class InventoryEvent(Base):
    """
    Table Name: ledger_inventory_events
    Purpose: The Write Model. An immutable, append-only log of every absolute delta.
    """

    __tablename__ = "ledger_inventory_events"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_event_id = Column(String, index=True, nullable=False)
    transaction_type = Column(String, nullable=False)  # One of 6 canonical types
    node_id = Column(String, index=True, nullable=False)
    item_id = Column(String, index=True, nullable=False)
    quantity = Column(BigInteger, nullable=False)  # Absolute delta (+50 or -50)
    running_balance = Column(BigInteger, nullable=False)  # Snapshot at moment of insert
    adjustment_reason = Column(
        String, nullable=True
    )  # Sub-type for ADJUSTMENT events (e.g., DAMAGE, EXPIRY, LOSS_IN_TRANSIT)
    occurred_at = Column(DateTime(timezone=True), nullable=False)  # Business Time
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # DB Time


class StockBalance(Base):
    """
    Table Name: ledger_stock_balances
    Purpose: The Read Model. A fast-access projection table holding the current cumulative value.
    Concurrency: Uses 'version' for Optimistic Concurrency Control (OCC).
    """

    __tablename__ = "ledger_stock_balances"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id = Column(String, index=True, nullable=False)
    item_id = Column(String, index=True, nullable=False)
    quantity = Column(BigInteger, nullable=False, default=0)

    # OCC Column
    version = Column(Integer, nullable=False, default=1)
    last_updated = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("node_id", "item_id", name="uq_stock_balance_node_item"),
    )

    __mapper_args__ = {"version_id_col": version}
