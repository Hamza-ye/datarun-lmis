import enum
import uuid
from sqlalchemy import Column, String, Enum, BigInteger, DateTime, func, JSON, text
from sqlalchemy.types import Uuid

from core.database import Base

class InboxStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    MAPPED = "MAPPED"
    FORWARDED = "FORWARDED"
    DLQ = "DLQ"
    ERROR = "ERROR"

class AdapterInbox(Base):
    __tablename__ = "adapter_inbox"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_system = Column(String, nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(Enum(InboxStatus, name="inbox_status"), nullable=False, default=InboxStatus.RECEIVED)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
class MappingContract(Base):
    __tablename__ = "mapping_contracts"
    
    id = Column(String, primary_key=True)  # e.g., 'hf_receipt_902'
    version = Column(String, nullable=False)
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

class DeadLetterQueue(Base):
    __tablename__ = "dead_letter_queue"
    
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inbox_id = Column(Uuid(as_uuid=True), nullable=False)
    source_system = Column(String, nullable=False)
    error_reason = Column(String, nullable=False)
    context_data = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="UNRESOLVED") # UNRESOLVED, REPROCESSED, DISCARDED
    created_at = Column(DateTime(timezone=True), server_default=func.now())
