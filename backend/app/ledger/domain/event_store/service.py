import asyncio

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.exc import StaleDataError

from app.ledger.models.event_store import InventoryEvent, StockBalance
from app.ledger.schemas.command import LedgerCommand, TransactionType


class InsufficientStockError(Exception):
    pass


class EventStoreService:
    @staticmethod
    async def commit_command(
        session: AsyncSession, command: LedgerCommand, max_retries: int = 3
    ) -> InventoryEvent:
        """
        The core math engine.
        Calculates the delta, applies it to the StockBalance, and records the immutable Event.
        Uses OCC (Optimistic Concurrency Control). If `StaleDataError` is caught, it retries calculation.
        """
        retries = 0

        while retries <= max_retries:
            try:
                # 1. Fetch Read Model
                stmt = select(StockBalance).where(
                    StockBalance.node_id == command.node_id,
                    StockBalance.item_id == command.item_id,
                )
                result = await session.execute(stmt)
                balance_record = result.scalars().first()

                # 1b. Create the Read Model record if it doesn't exist
                if not balance_record:
                    if (
                        command.transaction_type
                        in [TransactionType.ISSUE, TransactionType.TRANSFER]
                        and command.quantity > 0
                    ):
                        raise InsufficientStockError(
                            f"Cannot issue {command.quantity} from missing balance record."
                        )

                    balance_record = StockBalance(
                        node_id=command.node_id, item_id=command.item_id, quantity=0
                    )
                    session.add(balance_record)

                # 2. CQRS Math & Delta Setup
                current_qty = balance_record.quantity
                delta = 0

                if command.transaction_type == TransactionType.STOCK_COUNT:
                    # Stock counts are Absolute values.
                    delta = command.quantity - current_qty
                elif command.transaction_type in [
                    TransactionType.ISSUE,
                    TransactionType.TRANSFER,
                ]:
                    # These reduce stock
                    delta = -abs(command.quantity)
                elif command.transaction_type == TransactionType.RECEIPT:
                    # These add stock
                    delta = abs(command.quantity)
                elif command.transaction_type in [
                    TransactionType.ADJUSTMENT,
                    TransactionType.REVERSAL,
                ]:
                    # The payload provides exactly what to add/subtract (can be positive or negative)
                    delta = command.quantity

                new_qty = current_qty + delta

                # 3. Validation
                if new_qty < 0:
                    raise InsufficientStockError(
                        f"Transaction results in negative stock: {current_qty} + {delta} = {new_qty}"
                    )

                # 4. Projection Update (Triggers OCC)
                balance_record.quantity = new_qty

                # 5. Write Immutable Event Record
                event_log = InventoryEvent(
                    source_event_id=command.source_event_id,
                    transaction_type=command.transaction_type.value,
                    node_id=command.node_id,
                    item_id=command.item_id,
                    quantity=delta,
                    running_balance=new_qty,
                    adjustment_reason=command.adjustment_reason,
                    occurred_at=command.occurred_at,
                )
                session.add(event_log)

                await session.flush()

                return event_log

            except StaleDataError:
                await session.rollback()
                retries += 1
                if retries > max_retries:
                    raise Exception(
                        f"Failed to commit inventory event {command.source_event_id} due to high concurrency. Max retries {max_retries} exceeded."
                    )
                await asyncio.sleep(0.05 * retries)

            except IntegrityError as e:
                await session.rollback()
                raise ValueError(f"Integrity Error: {e}")
