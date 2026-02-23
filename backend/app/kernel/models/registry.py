import enum
import uuid
from sqlalchemy import Column, String, Date, JSON, Enum, func, DateTime
from sqlalchemy.types import Uuid

from core.database import Base

class CommodityStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"

class NodeRegistry(Base):
    """
    Table Name: kernel_node_registry
    Purpose: Tracks logical and physical supply chain locations.
    Pattern: Slowly Changing Dimensions (SCD) Type 2.
    Why: If a clinic changes its parent district, historical events MUST associate with the old district.
    We query the parent hierarchy using 'date BETWEEN valid_from AND valid_to'.
    """
    __tablename__ = "kernel_node_registry"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4) # Surrogate PK for the row
    uid = Column(String, index=True, nullable=False) # The stable string ID representing the entity through time
    code = Column(String, nullable=False) # Human readable code, e.g., 'WH-01'
    name = Column(String, nullable=False)
    node_type = Column(String, nullable=False) # e.g., 'WAREHOUSE', 'DISTRICT_STORE', 'CLINIC'
    parent_id = Column(String, index=True, nullable=True) # References another Node 'uid'
    
    # SCD Type 2 Time Boundaries
    valid_from = Column(DateTime(timezone=True), nullable=False, default=func.now())
    valid_to = Column(DateTime(timezone=True), nullable=True) # Null means this is the currently active version
    
    meta_data = Column(JSON, nullable=True) # Contact info, geo-coordinates, etc.

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class CommodityRegistry(Base):
    """
    Table Name: kernel_commodity_registry
    Purpose: Golden source of truth for physical items.
    Rule: The Ledger ONLY cares about the 'base_unit'. Package multipliers exist entirely in the Adapter Layer.
    """
    __tablename__ = "kernel_commodity_registry"

    # UUID surrogate key vs String natural key. 
    # Usually item_id strings from external ERPs are stable so we can use them as PKs here.
    item_id = Column(String, primary_key=True) 
    code = Column(String, index=True, nullable=False) # Human readable short code (e.g. PARAM-01)
    name = Column(String, nullable=False)
    base_unit = Column(String, nullable=False) # e.g., 'TABLET', 'PIECE', 'VIAL'
    status = Column(Enum(CommodityStatus, name="commodity_status"), nullable=False, default=CommodityStatus.ACTIVE)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
