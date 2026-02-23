from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from core.database import engine, Base
import contextvars
import uuid

from app.adapter.api.router import router as adapter_router
from app.adapter.api.admin import router as adapter_admin_router
from app.ledger.api.router import ledger_router, gatekeeper_router
from app.kernel.api.router import router as kernel_router
from app.core.api import router as auth_router

import asyncio
from app.adapter.worker import AdapterWorker

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Start Background Worker
    worker_task = asyncio.create_task(AdapterWorker.run_loop(interval_seconds=5))
    
    yield
    
    # 2. Graceful Shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        print("Adapter Worker shutdown cleanly.")
        
    await engine.dispose()

app = FastAPI(
    title="National LMIS Ledger System",
    description="Decoupled Modular Monolith for Supply Chain Accounting",
    version="1.0.0",
    lifespan=lifespan
)

# --- Observability (Correlation IDs) ---
correlation_id_ctx = contextvars.ContextVar("correlation_id", default=None)

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    # Retrieve from header or generate a new one
    corr_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    correlation_id_ctx.set(corr_id)
    
    response = await call_next(request)
    # Echo back to the client
    response.headers["X-Correlation-ID"] = corr_id
    return response

# --- Global Standardized Error Envelopes ---
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": "HTTP_ERROR",
            "detail": exc.detail,
            "correlation_id": correlation_id_ctx.get()
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "VALIDATION_ERROR",
            "detail": exc.errors(),
            "correlation_id": correlation_id_ctx.get()
        },
    )

from app.ledger.domain.event_store.service import InsufficientStockError

@app.exception_handler(InsufficientStockError)
async def insufficient_stock_exception_handler(request: Request, exc: InsufficientStockError):
    return JSONResponse(
        status_code=400,
        content={
            "error_code": "INSUFFICIENT_STOCK",
            "detail": str(exc),
            "correlation_id": correlation_id_ctx.get()
        },
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_SERVER_ERROR",
            "detail": "An unexpected system error occurred.",
            "correlation_id": correlation_id_ctx.get()
        },
    )

# Mount the Modular Routers
app.include_router(auth_router)
app.include_router(adapter_router)
app.include_router(adapter_admin_router)
app.include_router(ledger_router)
app.include_router(gatekeeper_router)
app.include_router(kernel_router)

@app.get("/health")
async def health_check():
    return {"status": "ok", "architecture": "modular_monolith"}
