import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from core.database import Base

# Ensure the models are registered 
from app.ledger.models.idempotency import IdempotencyRegistry

@pytest_asyncio.fixture(scope="function")
async def db_session():
    # SQLite in memory is perfect and blazingly fast for these domain logic tests
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with async_session() as session:
        yield session
        
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
