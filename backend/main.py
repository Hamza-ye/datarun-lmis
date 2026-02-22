from fastapi import FastAPI

# Initialize the main FastAPI application
app = FastAPI(
    title="Datarun LMIS",
    description="Datarun LMIS - Unified API",
    version="1.0.0",
)

# API Routers will be mounted here
# app.include_router(adapter_api.router, prefix="/api/adapter")
# app.include_router(ledger_api.router, prefix="/api/ledger")

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Datarun LMIS API is running"}
