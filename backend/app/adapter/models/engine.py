import enum
import uuid

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Index,
    String,
    func,
)
from sqlalchemy.types import Uuid

from core.database import Base


class InboxStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    MAPPED = "MAPPED"
    FORWARDED = "FORWARDED"
    RETRY_EGRESS = "RETRY_EGRESS"
    DLQ = "DLQ"
    DESTINATION_REJECTED = "DESTINATION_REJECTED"
    REPROCESSED = "REPROCESSED"

class ContractStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"
    REJECTED = "REJECTED"

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
    mapped_payload = Column(JSON, nullable=True)
    status = Column(Enum(InboxStatus, name="inbox_status"), nullable=False, default=InboxStatus.RECEIVED)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index(
            "idx_inbox_pending",
            "status",
            postgresql_where=status.in_([InboxStatus.RECEIVED, InboxStatus.MAPPED, InboxStatus.RETRY_EGRESS])
        ),
        CheckConstraint(
            "(status NOT IN ('MAPPED', 'FORWARDED', 'RETRY_EGRESS', 'DESTINATION_REJECTED')) OR "
            "(mapping_id IS NOT NULL AND mapping_version IS NOT NULL AND mapped_payload IS NOT NULL)",
            name="chk_mapped_state_requirements"
        ),
    )
    
class MappingContract(Base):
    __tablename__ = "mapping_contracts"
    
    id = Column(String, primary_key=True)  # e.g., 'hf_receipt_902'
    version = Column(String, primary_key=True)
    status = Column(Enum(ContractStatus, name="contract_status"), nullable=False) # ACTIVE, DEPRECATED
    dsl_config = Column(JSON, nullable=False)
    sample_in = Column(JSON, nullable=True)
    expected_out = Column(JSON, nullable=True)
    test_result_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AdapterCrosswalk(Base):
    __tablename__ = "adapter_crosswalks"
    
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    namespace = Column(String, nullable=False, index=True) # e.g., 'wh_category_to_item'
    source_value = Column(String, nullable=False, index=True) # e.g., 'MRDT25'
    internal_id = Column(String, nullable=False) # e.g., 'RDT-01'
    metadata_json = Column(JSON, nullable=True) # e.g., {"transform_factor": 25}
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AdapterEgressLogs(Base):
    __tablename__ = "adapter_egress_logs"
    
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inbox_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    destination_url = Column(String, nullable=False)
    request_payload = Column(JSON, nullable=False)
    response_status = Column(String, nullable=True)
    response_body = Column(String, nullable=True)
    retry_count = Column(BigInteger, default=0)
    delivery_time_ms = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
