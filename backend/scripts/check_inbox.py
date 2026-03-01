import asyncio

from sqlalchemy.future import select

from app.adapter.models.engine import AdapterInbox, AdapterLogs, DeadLetterQueue
from core.database import async_session_maker


async def run():
    async with async_session_maker() as session:
        inboxes = (await session.execute(select(AdapterInbox))).scalars().all()
        print('INBOXES:', [(i.id, i.source_event_id, i.status) for i in inboxes])
        logs = (await session.execute(select(AdapterLogs))).scalars().all()
        print('LOGS:', [(l.inbox_id, l.response_status, l.response_body) for l in logs])
        dlqs = (await session.execute(select(DeadLetterQueue))).scalars().all()
        print('DLQs:', [(d.inbox_id, d.error_reason) for d in dlqs])

if __name__ == "__main__":
    asyncio.run(run())
