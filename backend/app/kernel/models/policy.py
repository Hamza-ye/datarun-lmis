import uuid

from sqlalchemy import JSON, Column, DateTime, String, UniqueConstraint, func
from sqlalchemy.types import Uuid

from core.database import Base


class SystemPolicy(Base):
    """
    Table Name: kernel_system_policy
    Purpose: Configuration as Data. 
    Prevents hardcoding rules (like auto-receive days or approval thresholds) into Python logic.
    """
    __tablename__ = "kernel_system_policy"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_key = Column(String, index=True, nullable=False) # e.g. 'approval_required', 'auto_receive_days'
    
    # Target resolution coordinates. 
    # Use "GLOBAL" or "ALL" for wide nets. Specific IDs take precedence during resolution.
    applies_to_node = Column(String, index=True, nullable=False, default="GLOBAL")
    applies_to_item = Column(String, index=True, nullable=False, default="ALL")
    
    config = Column(JSON, nullable=False) # e.g. {"days": 14} or {"threshold": 500, "transaction_types": ["ADJUSTMENT"]}

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('policy_key', 'applies_to_node', 'applies_to_item', name='uq_system_policy_key_coords'),
    )
