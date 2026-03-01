import uuid

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.types import Uuid

from core.database import Base


class InventoryEvent(Base):
    """
    Table Name: ledger_inventory_events
    Purpose: The Write Model. An immutable, append-only log of every absolute delta.
    """
    __tablename__ = "ledger_inventory_events"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_event_id = Column(String, index=True, nullable=False) # Maps to the originating Adapter payload
    transaction_type = Column(String, nullable=False) # e.g., RECEIPT, DISPATCH, STOCK_COUNT
    node_id = Column(String, index=True, nullable=False)
    item_id = Column(String, index=True, nullable=False)
    quantity = Column(Integer, nullable=False) # Absolute delta (e.g., +50 or -50), or absolute value for STOCK_COUNT
    running_balance = Column(Integer, nullable=False) # Snapshot of the balance at the moment this inserted
    occurred_at = Column(DateTime(timezone=True), nullable=False) # Business Time
    created_at = Column(DateTime(timezone=True), server_default=func.now()) # DB Time

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
    quantity = Column(Integer, nullable=False, default=0) # Must not go below zero without specific config
    
    # OCC Column. SQLAlchemy will automatically increment this on UPDATE and raise StaleDataError if it mismatches.
    version = Column(Integer, nullable=False, default=1)
    
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('node_id', 'item_id', name='uq_stock_balance_node_item'),
    )

    __mapper_args__ = {
        "version_id_col": version
    }
