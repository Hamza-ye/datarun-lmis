from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class StockBalanceResponse(BaseModel):
    """View model for the current pre-calculated stock projection"""
    model_config = ConfigDict(from_attributes=True)
    
    node_id: str
    item_id: str
    quantity: int
    last_updated: datetime

class LedgerHistoryResponse(BaseModel):
    """View model for the immutable audit log underlying the balances"""
    model_config = ConfigDict(from_attributes=True)
    
    source_event_id: str
    transaction_type: str
    node_id: str
    item_id: str
    quantity: int
    running_balance: int # The balance strictly at the time this happened
    occurred_at: datetime
