import asyncio
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.ledger.schemas.command import LedgerCommand, TransactionType
from app.ledger.models.event_store import InventoryEvent, StockBalance

class InsufficientStockError(Exception):
    pass

class EventStoreService:
    
    @staticmethod
    async def commit_command(session: AsyncSession, command: LedgerCommand, max_retries: int = 3) -> InventoryEvent:
        """
        The core math engine (Area C). 
        Calculates the delta, applies it to the StockBalance, and records the immutable Event.
        Uses OCC (Optimistic Concurrency Control). If `StaleDataError` is caught, it retries calculation.
        """
        retries = 0
        
        while retries <= max_retries:
            try:
                # 1. Fetch Read Model
                stmt = select(StockBalance).where(
                    StockBalance.node_id == command.node_id,
                    StockBalance.item_id == command.item_id
                )
                result = await session.execute(stmt)
                balance_record = result.scalars().first()
                
                # 1b. Create the Read Model record if it doesn't exist
                if not balance_record:
                    # If it's an issue but no record exists, they can't issue (stock is 0)
                    if command.transaction_type in [TransactionType.ISSUE, TransactionType.TRANSFER] and command.quantity > 0:
                         raise InsufficientStockError(f"Cannot issue {command.quantity} from missing balance record.")
                         
                    balance_record = StockBalance(
                        node_id=command.node_id,
                        item_id=command.item_id,
                        quantity=0
                    )
                    session.add(balance_record)
                
                # 2. CQRS Math & Delta Setup
                current_qty = balance_record.quantity
                delta = 0
                
                if command.transaction_type == TransactionType.STOCK_COUNT:
                    # Stock counts are Absolute values. 
                    # If DB has 10, and command says 12, Delta is +2.
                    delta = command.quantity - current_qty
                elif command.transaction_type in [TransactionType.ISSUE, TransactionType.TRANSFER]:
                    # These reduce stock
                    # Adapter guarantees passing absolute base units here, but just in case, ensure it's negative
                    delta = -abs(command.quantity)
                elif command.transaction_type in [TransactionType.RECEIPT]:
                    # These add stock
                    delta = abs(command.quantity)
                elif command.transaction_type in [TransactionType.ADJUSTMENT, TransactionType.REVERSAL, TransactionType.LOSS_IN_TRANSIT]:
                    # The payload provided exactly what to add/subtract (can be positive or negative)
                    delta = command.quantity
                
                new_qty = current_qty + delta
                
                # 3. Validation
                if new_qty < 0:
                    raise InsufficientStockError(f"Transaction results in negative stock: {current_qty} + {delta} = {new_qty}")
                
                # 4. Projection Update (Triggers OCC)
                # Ensure we bump the version manually if version_id_col doesn't perfectly propagate via session math
                balance_record.quantity = new_qty
                # balance_record.version is automatically incremented by SQLAlchemy on session.commit/flush
                
                # 5. Write Immutable Event Record
                event_log = InventoryEvent(
                    source_event_id=command.source_event_id,
                    transaction_type=command.transaction_type.value,
                    node_id=command.node_id,
                    item_id=command.item_id,
                    quantity=delta,  # We store the *change* that occurred
                    running_balance=new_qty, # We snapshot the new state for point-in-time calculation speed
                    occurred_at=command.occurred_at
                )
                session.add(event_log)
                
                # We attempt to flush. If another worker updated `StockBalance` while we did this math,
                # SQLAlchemy will throw a StaleDataError here because the WHERE id=? AND version=? will fail affecting 0 rows.
                await session.flush()
                
                return event_log
                
            except StaleDataError:
                # Concurrent Modification Detected! The math is now wrong.
                # E.g. Worker A saw 10, adds 5. Worker B saw 10, adds 2. 
                # B commits (version=2, qty=12). A tries to commit (EXPECTS version=1). Fails.
                # A must rollback this sub-transaction and recalculate the math with the new reality (qty=12).
                await session.rollback()
                retries += 1
                if retries > max_retries:
                    raise Exception(f"Failed to commit inventory event {command.source_event_id} due to high concurrency. Max retries {max_retries} exceeded.")
                # Brief sleep to allow the competing transaction to fully resolve
                await asyncio.sleep(0.05 * retries) 
                
            except IntegrityError as e:
                # E.g., duplicate source_event_id
                await session.rollback()
                raise ValueError(f"Integrity Error: {e}")
