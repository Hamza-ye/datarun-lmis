import asyncio

from sqlalchemy.future import select

from app.ledger.models.event_store import InventoryEvent, StockBalance
from core.database import async_session_maker


async def run():
    async with async_session_maker() as session:
        events = (await session.execute(select(InventoryEvent))).scalars().all()
        print('EVENTS:', [(e.source_event_id, e.node_id, e.item_id, e.quantity) for e in events])
        balances = (await session.execute(select(StockBalance))).scalars().all()
        print('BALANCES:', [(b.node_id, b.item_id, b.quantity) for b in balances])

if __name__ == "__main__":
    asyncio.run(run())
