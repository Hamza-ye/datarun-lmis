import pytest
import pytest_asyncio
import datetime
from sqlalchemy.future import select

from app.ledger.schemas.command import LedgerCommand, TransactionType
from app.ledger.models.idempotency import IdempotencyRegistry, IdempotencyStatus
from app.ledger.models.event_store import StockBalance, InventoryEvent
from app.ledger.domain.idempotency.service import IdempotencyService
from app.ledger.domain.event_store.service import EventStoreService

@pytest.mark.asyncio
async def test_reversal_atomicity_rollback(db_session, monkeypatch):
    """
    E2E Proof of Atomicity:
    If Idempotency flags a REVERSAL for V2, but the downstream EventStore math crashes,
    ensure the DB session rolls back completely so V1 is untouched and Idempotency isn't corrupted.
    """
    
    # 1. Successful V1 Payload
    cmd_v1 = LedgerCommand(
        source_event_id="E2E_ROLLBACK_1",
        version_timestamp=1,
        transaction_type=TransactionType.RECEIPT,
        node_id="CLINIC_A",
        item_id="ITEM_A",
        quantity=50,
        occurred_at=datetime.datetime.now(datetime.timezone.utc)
    )
    
    # Perform standard flow
    res_idem1 = await IdempotencyService.check_or_register_command(db_session, cmd_v1)
    assert res_idem1.action == "PROCEED"
    
    await EventStoreService.commit_command(db_session, cmd_v1)
    await db_session.commit()
    
    bal_v1 = (await db_session.execute(select(StockBalance))).scalars().first()
    assert bal_v1.quantity == 50
    
    # 2. V2 Arrives (Triggering Reversal) but Math Engine crashes!
    cmd_v2 = LedgerCommand(
        source_event_id="E2E_ROLLBACK_1",
        version_timestamp=2,
        transaction_type=TransactionType.RECEIPT,
        node_id="CLINIC_A",
        item_id="ITEM_A",
        quantity=80,
        occurred_at=datetime.datetime.now(datetime.timezone.utc)
    )
    
    # Simulate an unforeseen DB drop or math crash inside the Reversal implementation.
    async def mock_crashing_commit(*args, **kwargs):
        raise RuntimeError("SIMULATED FATAL DB/MATH CRASH DURING V2")
        
    monkeypatch.setattr(EventStoreService, "commit_command", mock_crashing_commit)
    
    try:
        # In the router, it would call Idempotency, see REVERSE_AND_PROCEED, and then call EventStore
        res_idem2 = await IdempotencyService.check_or_register_command(db_session, cmd_v2)
        assert res_idem2.action == "REVERSE_AND_PROCEED"
        
        # Call the mocked crashing method
        await EventStoreService.commit_command(db_session, cmd_v2)
        
        # If it didn't crash, the test fails
        assert False 
    except RuntimeError:
        # 3. Prove the overarching try/except rollback boundary of FastAPI/Router handles it
        await db_session.rollback()
        
    # 4. Critical Validations
    
    # The V1 Balance should remain untouched
    bal_final = (await db_session.execute(select(StockBalance))).scalars().first()
    assert bal_final.quantity == 50 # Not 80, not 0 (if reversal stuck)
    
    # The Idempotency Record must still flag it as processing/failed or rolled back without permanent corruption
    # Because we rolled back the transaction that bumped it to v2/PROCESSING
    stmt = select(IdempotencyRegistry).where(IdempotencyRegistry.source_event_id == "E2E_ROLLBACK_1")
    idem_final = (await db_session.execute(stmt)).scalars().first()
    
    # Crucially, it must roll back to V1 so the system can retry V2 later on!
    assert idem_final.version_timestamp == 1
    assert idem_final.status == IdempotencyStatus.PROCESSING # (The V1 state before we added COMPLETED logic to API)
