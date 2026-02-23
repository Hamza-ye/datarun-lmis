# Architecture Decision Records (ADRs)

This document captures the critical, high-level structural decisions made for the National Malaria Commodity Ledger (NMCL). When making implementation choices, developers must adhere to the constraints defined here.

---

## ADR-001: Separation of Adapter and Ledger via Modular Monolith

**Context:** 
External systems (like CommCare or DHIS2) send messy, unpredictable data. The Ledger requires strict, mathematically pure commands. We need to isolate the mapping/translation logic from the accounting logic without creating an operational nightmare of deploying 15 microservices for a 5-person IT team.

**Decision:**
We will use a **Modular Monolith** architecture.
* The system runs as a single process (e.g., one FastAPI server) sharing a single Database instance.
* The translation logic lives in `backend/app/adapter`. The accounting logic lives in `backend/app/ledger`.
* **Constraint:** The Adapter and Ledger are banned from importing each other's Python classes.
* **Constraint:** The Adapter communicates with the Ledger strictly by making an HTTP POST loopback request to the Ledger's API endpoint.

**Consequence:**
We achieve perfect domain isolation (allowing us to easily split them into true microservices later if scaling demands it), but retain the simplicity of a single `git pull` and single `docker-compose up` for local development.

---

## ADR-002: Event Sourcing for the Accounting Core (Area C)

**Context:**
A Ledger is only useful if it is trusted. If the `stock_balances` table simply updates `quantity = 50`, auditors have no way to prove *why* the stock is 50.

**Decision:**
Area C will use **Event Sourcing**.
* The ultimate source of truth is the `inventory_events` table (The Event Store), which is **append-only**.
* `UPDATE` and `DELETE` SQL commands are strictly forbidden on the Event Store.
* To fix a mistake, a `REVERSAL` event must be appended.

**Consequence:**
Absolute auditability. We can rebuild the entire state of the system from Day 1 by replaying the events. However, querying the Event Store for current balances is too slow, necessitating ADR-003.

---

## ADR-003: Command Query Responsibility Segregation (CQRS) for Balances

**Context:**
Event Sourcing (ADR-002) makes writing "Facts" incredibly safe, but makes reading "Current Stock" incredibly slow.

**Decision:**
We will separate the Write Model from the Read Model (CQRS).
* **Write Model:** The `inventory_events` table.
* **Read Model (Projections):** The `stock_balances` table. Whenever an event is written, the system synchronously updates the read model. 
* To prevent race conditions during the Projection update, we mandate **Optimistic Concurrency Control** (OCC) using a `version` integer on the projection row.

**Consequence:**
Fetching stock for a dashboard is an instant `O(1)` index lookup. Writing a transaction requires slightly more database coordination (updating the event and the projection in a single atomic DB transaction).

---

## ADR-004: Synchronous Ledger Execution vs. Event Broker (Kafka)

**Context:**
Modern architectures often use Kafka or RabbitMQ to stream events between domains.

**Decision:**
Inside the Ledger module itself, execution will be **Synchronous**, relying on PostgreSQL ACID transactions.
* We will *not* introduce Kafka/RabbitMQ into the core infrastructure.
* Staging commands (Area E) and Idempotency (Area B) will use PostgreSQL tables as their "queues."

**Conclusion:**
Massively simplified infrastructure. A Postgres DB is sufficient to handle hundreds of transactions per second, which far exceeds the current requirements for the LMIS. By avoiding distributed message queues, we eliminate the complexity of distributed transactions, two-phase commits, and message broker maintenance.

---

## ADR-005: Async Background Tasks via FastAPI Application Lifespan

**Context:**
The Adapter component uses a "Store, Cleanse & Forward" pattern (ADR-001). When an external payload is received via the API, the system responds immediately with a `202 Accepted` while postponing the heavy mapping and forwarding logic. A background worker loop is required to continuously poll the `adapter_inbox`.

**Decision:**
We will implement background workers utilizing Python's native `asyncio.create_task()` directly bound to the FastAPI application's `@asynccontextmanager lifespan`.
*   We explicitly discard introducing heavy task queues like **Celery**, **RQ**, or **Redis**.
*   The worker tasks must continuously trap and log their own internal `Exception` events to avoid crashing the server loop.
*   The application explicitly traps the `asyncio.CancelledError` on server shutdown to gracefully wrap up any active database transactions.

**Consequence:**
By staying native, we maintain the strict definition of our "zero-dependency" Modular Monolith (ADR-001). We guarantee that deployment consists purely of the Python API and a PostgreSQL database. The tradeoff is that background tasks exist completely in-memory tied to the API instances processes, scaling horizontally exactly linearly alongside the API instances.
