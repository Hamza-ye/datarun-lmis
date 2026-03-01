import asyncio
import logging
import os
import sys

from sqlalchemy import delete, select

# Add the 'backend' directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.ledger.models.event_store import InventoryEvent, StockBalance
from core.database import async_session_maker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

async def replay_ledger_events():
    logger.info("Starting Ledger Read-Model Replay...")
    
    async with async_session_maker() as db:
        try:
            # 1. Truncate Read Model
            await db.execute(delete(StockBalance))
            logger.info("Truncated existing StockBalance read models.")
            
            # 2. Fetch all events ordered by occurred_at ASC
            result = await db.execute(
                select(InventoryEvent).order_by(InventoryEvent.occurred_at.asc(), InventoryEvent.created_at.asc())
            )
            events = result.scalars().all()
            
            # 3. Rebuild balances in memory
            balances = {}
            for event in events:
                key = (event.node_id, event.item_id)
                if key not in balances:
                    balances[key] = 0
                
                # STOCK_COUNT overrides, others are relative deltas
                if event.transaction_type == "STOCK_COUNT":
                    balances[key] = event.quantity
                else:
                    balances[key] += event.quantity
                    
            # 4. Insert new balances
            inserted_count = 0
            for (node_id, item_id), qty in balances.items():
                db.add(StockBalance(node_id=node_id, item_id=item_id, quantity=qty))
                inserted_count += 1
                
            await db.commit()
            logger.info(f"Replay Complete. Processed {len(events)} events -> Rebuilt {inserted_count} balance projections.")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Replay failed: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(replay_ledger_events())
