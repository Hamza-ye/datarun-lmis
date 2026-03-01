# ADR-005: Async Background Tasks via FastAPI Application Lifespan

## Status
Accepted

## Context
The Adapter component uses a "Store, Cleanse & Forward" pattern ([ADR-001](001-modular-monolith.md)). When an external payload is received via the API, the system responds immediately with a `202 Accepted` while postponing the heavy mapping and forwarding logic. A background worker loop is required to continuously poll the `adapter_inbox`.

## Decision
We will implement background workers utilizing Python's native `asyncio.create_task()` directly bound to the FastAPI application's `@asynccontextmanager lifespan`.

- We explicitly discard introducing heavy task queues like **Celery**, **RQ**, or **Redis**.
- The worker tasks must continuously trap and log their own internal `Exception` events to avoid crashing the server loop.
- The application explicitly traps the `asyncio.CancelledError` on server shutdown to gracefully wrap up any active database transactions.

## Consequences

### Positive
- Maintains the strict definition of the "zero-dependency" Modular Monolith ([ADR-001](001-modular-monolith.md)). Deployment consists purely of the Python API and a PostgreSQL database.

### Negative
- Background tasks exist completely in-memory tied to the API instance process, scaling horizontally exactly linearly alongside the API instances.
