from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.ledger.models.in_transit import InTransitStatus


class InTransitTransferResponse(BaseModel):
    """Data Transfer Object representing an active or completed In-Transit shipment."""
    transfer_id: UUID
    source_node_id: str
    dest_node_id: str
    item_id: str
    qty_shipped: int
    qty_received: int
    status: InTransitStatus
    dispatched_at: datetime
    auto_close_after: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

class ReceiveTransferRequest(BaseModel):
    """Payload for completing an In-Transit receipt from the UI."""
    qty_received: int
    node_id: str
    occurred_at: datetime
    source_event_id: str
