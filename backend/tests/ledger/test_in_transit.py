import pytest
import pytest_asyncio
import datetime
from sqlalchemy.future import select

from app.ledger.schemas.command import LedgerCommand, TransactionType
from app.ledger.models.in_transit import InTransitRegistry, InTransitStatus, InternalDLQ
from app.ledger.models.event_store import StockBalance, InventoryEvent
from app.ledger.domain.event_store.service import EventStoreService
from app.ledger.domain.in_transit.service import InTransitService

def base_command(transaction_type, quantity, event_id="C1", transfer_id=None):
    return LedgerCommand(
        source_event_id=event_id,
        version_timestamp=1,
        transaction_type=transaction_type,
        node_id="NODE_A", # Defaulting, will override in tests
        item_id="ITEM_X",
        quantity=quantity,
        transfer_id=transfer_id,
        occurred_at=datetime.datetime.now(datetime.timezone.utc)
    )

@pytest_asyncio.fixture
async def seeded_warehouse(db_session):
    """Seed the warehouse with 100 units so it can dispatch."""
    cmd = base_command(TransactionType.RECEIPT, 100, "W_SEED")
    cmd.node_id = "WAREHOUSE"
    await EventStoreService.commit_command(db_session, cmd)
    await db_session.flush()

@pytest.mark.asyncio
async def test_happy_path_transfer(db_session, seeded_warehouse):
    """Warehouse DEDUCTS 50 (Dispatch). Clinic ADDS 50 (Receipt)."""
    
    # 1. Dispatch
    dispatch_cmd = base_command(TransactionType.TRANSFER, 50, "DISP_1")
    dispatch_cmd.node_id = "WAREHOUSE"
    
    registry = await InTransitService.process_dispatch(db_session, dispatch_cmd, dest_node_id="CLINIC_1")
    await db_session.commit()
    
    assert registry.status == InTransitStatus.OPEN
    
    warehouse_bal = (await db_session.execute(select(StockBalance).where(StockBalance.node_id == "WAREHOUSE"))).scalars().first()
    assert warehouse_bal.quantity == 50 # Deducted
    
    clinic_bal = (await db_session.execute(select(StockBalance).where(StockBalance.node_id == "CLINIC_1"))).scalars().first()
    assert clinic_bal is None # Nothing arrived yet!
    
    # 2. Receipt
    receipt_cmd = base_command(TransactionType.RECEIPT, 50, "RECV_1", str(registry.transfer_id))
    receipt_cmd.node_id = "CLINIC_1"
    
    registry_updated = await InTransitService.process_receipt(db_session, receipt_cmd, str(registry.transfer_id))
    await db_session.commit()
    
    assert registry_updated.status == InTransitStatus.COMPLETED
    assert registry_updated.qty_received == 50
    
    clinic_bal = (await db_session.execute(select(StockBalance).where(StockBalance.node_id == "CLINIC_1"))).scalars().first()
    assert clinic_bal.quantity == 50 # Arrived!

@pytest.mark.asyncio
async def test_partial_receipt_discrepancy(db_session, seeded_warehouse):
    """Warehouse sends 50. Clinic only receives 40."""
    
    dispatch_cmd = base_command(TransactionType.TRANSFER, 50, "DISP_2")
    dispatch_cmd.node_id = "WAREHOUSE"
    registry = await InTransitService.process_dispatch(db_session, dispatch_cmd, "CLINIC_1")
    await db_session.commit()
    
    receipt_cmd = base_command(TransactionType.RECEIPT, 40, "RECV_2", str(registry.transfer_id))
    receipt_cmd.node_id = "CLINIC_1"
    
    registry_updated = await InTransitService.process_receipt(db_session, receipt_cmd, str(registry.transfer_id))
    await db_session.commit()
    
    assert registry_updated.status == InTransitStatus.PARTIAL
    assert registry_updated.qty_received == 40
    assert registry_updated.qty_shipped == 50

@pytest.mark.asyncio
async def test_auto_close_stale_transfers(db_session, seeded_warehouse):
    """Simulates Cron Job closing a stalled transfer."""
    
    dispatch_cmd = base_command(TransactionType.TRANSFER, 50, "DISP_3")
    dispatch_cmd.node_id = "WAREHOUSE"
    registry = await InTransitService.process_dispatch(db_session, dispatch_cmd, "CLINIC_1")
    
    # Sneakily backdate the deadline so it's stale
    registry.auto_close_after = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    await db_session.commit()
    
    # Run the cron job
    closed_count = await InTransitService.auto_close_stale_transfers(db_session)
    await db_session.commit()
    
    assert closed_count == 1
    
    # Check registry updated
    stmt = select(InTransitRegistry).where(InTransitRegistry.transfer_id == registry.transfer_id)
    reg_final = (await db_session.execute(stmt)).scalars().first()
    assert reg_final.status == InTransitStatus.STALE_AUTO_CLOSED
    assert reg_final.qty_received == 50
    
    # Check Area C was credited
    clinic_bal = (await db_session.execute(select(StockBalance).where(StockBalance.node_id == "CLINIC_1"))).scalars().first()
    assert clinic_bal.quantity == 50

@pytest.mark.asyncio
async def test_internal_dlq_on_auto_close_error(db_session, seeded_warehouse, monkeypatch):
    """Simulates Area C rejecting an auto-receipt, ensuring the Cron doesn't crash but logs to DLQ."""
    
    dispatch_cmd = base_command(TransactionType.TRANSFER, 50, "DISP_4")
    dispatch_cmd.node_id = "WAREHOUSE"
    registry = await InTransitService.process_dispatch(db_session, dispatch_cmd, "CLINIC_1")
    registry.auto_close_after = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    await db_session.commit()
    
    # Patch EventStoreService to throw a validation error (e.g. Node Deactivated)
    async def mock_commit(*args, **kwargs):
        raise ValueError("Simulated Area C Rejection: Node Deactivated")
        
    monkeypatch.setattr(EventStoreService, "commit_command", mock_commit)
    
    # Run the cron job
    closed_count = await InTransitService.auto_close_stale_transfers(db_session)
    await db_session.commit()
    
    # The cron job itself returned 0 successful closures, but DID NOT CRASH
    assert closed_count == 0
    
    # Registry marked as failed
    stmt = select(InTransitRegistry).where(InTransitRegistry.transfer_id == registry.transfer_id)
    reg_final = (await db_session.execute(stmt)).scalars().first()
    assert reg_final.status == InTransitStatus.FAILED_AUTO_CLOSE
    
    # DLQ entry written
    dlq_entry = (await db_session.execute(select(InternalDLQ))).scalars().first()
    assert dlq_entry is not None
    assert dlq_entry.reference_id == str(registry.transfer_id)
    assert "Simulated Area C Rejection" in dlq_entry.error_message

@pytest.mark.asyncio
async def test_loss_in_transit(db_session, seeded_warehouse):
    """Simulates a shipment being lost in transit and written off by a supervisor."""
    
    # 1. Dispatch 50
    dispatch_cmd = base_command(TransactionType.TRANSFER, 50, "DISP_LOSS_1")
    dispatch_cmd.node_id = "WAREHOUSE"
    registry = await InTransitService.process_dispatch(db_session, dispatch_cmd, "CLINIC_1")
    await db_session.commit()
    
    warehouse_bal_before = (await db_session.execute(select(StockBalance).where(StockBalance.node_id == "WAREHOUSE"))).scalars().first()
    assert warehouse_bal_before.quantity == 50 # 100 - 50 = 50
    
    # 2. Loss Event 
    loss_cmd = base_command(TransactionType.LOSS_IN_TRANSIT, 50, "LOSS_EVENT_1")
    loss_cmd.node_id = "WAREHOUSE" # Accountability is tied to the source
    
    registry_updated = await InTransitService.process_loss(db_session, loss_cmd, str(registry.transfer_id))
    await db_session.commit()
    
    # 3. Verify Registry is LOST
    assert registry_updated.status == InTransitStatus.LOST
    
    # 4. Verify Balance did NOT double-deduct
    warehouse_bal_after = (await db_session.execute(select(StockBalance).where(StockBalance.node_id == "WAREHOUSE"))).scalars().first()
    assert warehouse_bal_after.quantity == 50 # Still 50!
    
    # 5. Verify the Audit Event was created with 0 quantity
    stmt = select(InventoryEvent).where(InventoryEvent.source_event_id == "LOSS_EVENT_1")
    loss_audit_event = (await db_session.execute(stmt)).scalars().first()
    
    assert loss_audit_event is not None
    assert loss_audit_event.quantity == 0
    assert loss_audit_event.transaction_type == TransactionType.LOSS_IN_TRANSIT
