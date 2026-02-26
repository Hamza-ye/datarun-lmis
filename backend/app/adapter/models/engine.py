import enum
import uuid
from sqlalchemy import Column, String, Enum, BigInteger, DateTime, func, JSON, text, Index
from sqlalchemy.types import Uuid

from core.database import Base

class InboxStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    MAPPED = "MAPPED"
    FORWARDED = "FORWARDED"
    RETRY = "RETRY"
    DLQ = "DLQ"
    ERROR = "ERROR"
    REPROCESSED = "REPROCESSED"

class AdapterInbox(Base):
    __tablename__ = "adapter_inbox"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    correlation_id = Column(Uuid(as_uuid=True), default=uuid.uuid4, index=True)
    parent_inbox_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    source_system = Column(String, nullable=False, index=True)
    mapping_id = Column(String, nullable=True)
    mapping_version = Column(String, nullable=True)
    source_event_id = Column(String, nullable=True, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(Enum(InboxStatus, name="inbox_status"), nullable=False, default=InboxStatus.RECEIVED)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index(
            "idx_inbox_pending",
            "status",
            postgresql_where=status.in_([InboxStatus.RECEIVED, InboxStatus.RETRY])
        ),
    )
    
class MappingContract(Base):
    __tablename__ = "mapping_contracts"
    
    id = Column(String, primary_key=True)  # e.g., 'hf_receipt_902'
    version = Column(String, primary_key=True)
    status = Column(String, nullable=False) # ACTIVE, DEPRECATED
    dsl_config = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AdapterCrosswalk(Base):
    __tablename__ = "adapter_crosswalks"
    
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    namespace = Column(String, nullable=False, index=True) # e.g., 'wh_category_to_item'
    source_value = Column(String, nullable=False, index=True) # e.g., 'MRDT25'
    internal_id = Column(String, nullable=False) # e.g., 'RDT-01'
    metadata_json = Column(JSON, nullable=True) # e.g., {"transform_factor": 25}
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AdapterLogs(Base):
    __tablename__ = "adapter_logs"
    
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inbox_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    destination_url = Column(String, nullable=False)
    request_payload = Column(JSON, nullable=False)
    response_status = Column(String, nullable=True)
    response_body = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
