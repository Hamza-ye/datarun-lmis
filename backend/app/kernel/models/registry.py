import enum
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
)
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

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uid = Column(
        String, index=True, nullable=False
    )  # Stable external identifier (e.g., CLX1234)
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    node_type = Column(String, nullable=False)  # WH, HF, MU, TEAM, MOBILE_WH
    parent_id = Column(
        String, index=True, nullable=True
    )  # References another Node 'uid'

    # SCD Type 2 Time Boundaries
    valid_from = Column(DateTime(timezone=True), nullable=False, default=func.now())
    valid_to = Column(
        DateTime(timezone=True), nullable=True
    )  # NULL = currently active version

    meta_data = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CommodityRegistry(Base):
    """
    Table Name: kernel_commodity_registry
    Purpose: Golden source of truth for physical items.
    Rule: The Ledger ONLY cares about the 'base_unit'. Package multipliers exist entirely in the Adapter Layer.
    """

    __tablename__ = "kernel_commodity_registry"

    item_id = Column(String, primary_key=True)
    code = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    base_unit = Column(String, nullable=False)  # e.g., 'TABLET', 'PIECE', 'VIAL'
    status = Column(
        Enum(CommodityStatus, name="commodity_status"),
        nullable=False,
        default=CommodityStatus.ACTIVE,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CommodityPackage(Base):
    """
    Table Name: commodity_packages
    Purpose: UOM conversion table for Adapters/Clients. Never used by the Event Store.
    Golden Rule: Base units and multipliers are STRICTLY IMMUTABLE. If packaging changes, create a new package_id.
    """

    __tablename__ = "commodity_packages"

    package_id = Column(String, primary_key=True)  # e.g., 'PKG-100'
    item_id = Column(
        String,
        ForeignKey("kernel_commodity_registry.item_id"),
        nullable=False,
        index=True,
    )
    uom_name = Column(String, nullable=False)  # e.g., 'BOX_100'
    base_unit_multiplier = Column(
        Integer, nullable=False
    )  # Conversion factor (e.g., 100)
    is_active = Column(Boolean, nullable=False, default=True)
