import pytest
import pytest_asyncio
import datetime
import asyncio
from sqlalchemy.future import select
from sqlalchemy.orm.exc import StaleDataError

from app.ledger.schemas.command import LedgerCommand, TransactionType
from app.ledger.models.event_store import InventoryEvent, StockBalance
from app.ledger.domain.event_store.service import EventStoreService, InsufficientStockError

def base_command(transaction_type, quantity, event_id="C1"):
    return LedgerCommand(
        source_event_id=event_id,
        version_timestamp=1,
        transaction_type=transaction_type,
        node_id="NODE_A",
        item_id="ITEM_X",
        quantity=quantity,
        occurred_at=datetime.datetime.now(datetime.timezone.utc)
    )

@pytest.mark.asyncio
async def test_cqrs_math_logic(db_session):
    """Verifies that RECEIPT, ISSUE, STOCK_COUNT all calculate running balance correctly."""
    
    # 1. RECEIPT
    cmd1 = base_command(TransactionType.RECEIPT, 50, "C1")
    await EventStoreService.commit_command(db_session, cmd1)
    
    bal1 = (await db_session.execute(select(StockBalance))).scalars().first()
    assert bal1.quantity == 50
    assert bal1.version == 1
    
    # 2. ISSUE
    cmd2 = base_command(TransactionType.ISSUE, 20, "C2")
    await EventStoreService.commit_command(db_session, cmd2)
    
    bal2 = (await db_session.execute(select(StockBalance))).scalars().first()
    assert bal2.quantity == 30
    assert bal2.version == 2
    
    # 3. STOCK COUNT (Overwrites absolute value)
    cmd3 = base_command(TransactionType.STOCK_COUNT, 200, "C3")
    await EventStoreService.commit_command(db_session, cmd3)
    
    bal3 = (await db_session.execute(select(StockBalance))).scalars().first()
    assert bal3.quantity == 200
    assert bal3.version == 3

    # Check Events history
    events = (await db_session.execute(select(InventoryEvent).order_by(InventoryEvent.created_at))).scalars().all()
    assert len(events) == 3
    assert events[0].quantity == 50     # RECEIPT +50
    assert events[1].quantity == -20    # ISSUE -20
    assert events[2].quantity == 170    # STOCK_COUNT to 200 implies +170 from 30

@pytest.mark.asyncio
async def test_insufficient_stock(db_session):
    cmd1 = base_command(TransactionType.RECEIPT, 10, "C1")
    await EventStoreService.commit_command(db_session, cmd1)
    
    cmd2 = base_command(TransactionType.ISSUE, 50, "C2")
    with pytest.raises(InsufficientStockError):
        await EventStoreService.commit_command(db_session, cmd2)

@pytest.mark.asyncio
async def test_occ_concurrent_collision_recovery(db_session, monkeypatch):
    """
    Simulates a race condition using a mock.
    Worker A tries to commit, but we simulate a StaleDataError on the first flush (representing a collision).
    Worker A should catch it, rollback, and retry its calculation payload.
    It should succeed on the second attempt.
    """
    
    # Pre-seed record
    cmd = base_command(TransactionType.RECEIPT, 0, "SEED")
    await EventStoreService.commit_command(db_session, cmd)
    await db_session.commit()

    cmd1 = base_command(TransactionType.RECEIPT, 50, "C1")
    
    original_flush = db_session.flush
    flush_count = 0
    
    async def side_effect_flush(*args, **kwargs):
        nonlocal flush_count
        flush_count += 1
        
        if flush_count == 1:
            # Throw the OCC Concurrency Exception!
            raise StaleDataError("Mocked Concurrency Exception")
            
        return await original_flush(*args, **kwargs)
        
    monkeypatch.setattr(db_session, "flush", side_effect_flush)

    # Execute service which should hit the StaleDataError on first flush, catch it, rollback, and retry.
    event = await EventStoreService.commit_command(db_session, cmd1)
    await db_session.commit()
    
    # Verify it retried
    assert flush_count == 2
    
    final_balance = (await db_session.execute(select(StockBalance))).scalars().first()
    
    assert final_balance.quantity == 50
    assert final_balance.version == 2
    assert event.running_balance == 50
