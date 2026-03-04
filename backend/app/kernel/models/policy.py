import uuid

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.types import Uuid

from core.database import Base


class SystemPolicy(Base):
    """
    Table Name: kernel_system_policy
    Purpose: Configuration as Data.
    Prevents hardcoding rules (like auto-receive days or approval thresholds) into Python logic.

    Scope Resolution (most-specific → least-specific):
      1. Specific node + specific item
      2. Specific node + NULL (any item)
      3. Node type (e.g. 'type:MU') + specific item
      4. Node type + NULL
      5. NULL + commodity category (e.g. 'category:DRUGS')
      6. NULL + NULL (global)

    Scope conventions:
      - applies_to_node: NULL = global, 'type:<code>' = node type, specific node UID otherwise
      - applies_to_item: NULL = all items, 'category:<name>' = commodity category, specific item_id otherwise
    """

    __tablename__ = "kernel_system_policy"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_key = Column(String, index=True, nullable=False)

    # Scope coordinates. NULL means "unscoped" (applies to all entities on this axis).
    applies_to_node = Column(String, index=True, nullable=True, default=None)
    applies_to_item = Column(String, index=True, nullable=True, default=None)

    config = Column(JSON, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # PostgreSQL UNIQUE constraint with COALESCE to handle NULL-inequality.
        # In PostgreSQL, NULL != NULL, so a standard UNIQUE(policy_key, applies_to_node, applies_to_item)
        # would allow multiple rows with the same key where both scope columns are NULL.
        # We use a unique index with COALESCE to treat NULLs as a sentinel for uniqueness purposes only.
        Index(
            "uq_system_policy_key_coords",
            policy_key,
            text("COALESCE(applies_to_node, '__NULL__')"),
            text("COALESCE(applies_to_item, '__NULL__')"),
            unique=True,
        ),
    )
