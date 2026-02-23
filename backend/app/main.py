from fastapi import FastAPI
from contextlib import asynccontextmanager
from core.database import engine, Base

from app.adapter.api.router import router as adapter_router
from app.ledger.api.router import ledger_router, gatekeeper_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Database initialization is now handled strictly by Alembic migrations.
    # We no longer auto-create tables on boot.
    yield
    # Clean up connections
    await engine.dispose()

app = FastAPI(
    title="National LMIS Ledger System",
    description="Decoupled Modular Monolith for Supply Chain Accounting",
    version="1.0.0",
    lifespan=lifespan
)

# Mount the Modular Routers
app.include_router(adapter_router)
app.include_router(ledger_router)
app.include_router(gatekeeper_router)

@app.get("/health")
async def health_check():
    return {"status": "ok", "architecture": "modular_monolith"}
