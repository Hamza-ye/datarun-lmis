from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any, Dict

class TransactionType(str, Enum):
    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"
    TRANSFER = "TRANSFER"
    ADJUSTMENT = "ADJUSTMENT"
    STOCK_COUNT = "STOCK_COUNT"
    REVERSAL = "REVERSAL"
    LOSS_IN_TRANSIT = "LOSS_IN_TRANSIT"

class LedgerCommand(BaseModel):
    source_event_id: str = Field(..., description="The unique ID from the source (e.g., ODK InstanceID).")
    version_timestamp: int = Field(..., description="Timestamp acting as version for edits/reversals.")
    transaction_type: TransactionType
    node_id: str = Field(..., description="Internal ID of the facility or MU")
    item_id: str = Field(..., description="Internal ID of the commodity (Shared Kernel)")
    quantity: int = Field(..., description="The delta. Always in Base Units.")
    transfer_id: Optional[str] = Field(None, description="Links a receipt to a specific dispatch.")
    batch_id: Optional[str] = Field(None, description="For tracking specific lots/batches.")
    expiry_date: Optional[datetime] = Field(None, description="Essential for FEFO logic.")
    occurred_at: datetime = Field(..., description="The 'Business Time' (when it happened in the field).")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Contextual info (e.g., 'Reason: Damaged in transit').")
