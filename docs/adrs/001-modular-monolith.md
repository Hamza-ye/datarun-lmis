# ADR-001: Separation of Adapter and Ledger via Modular Monolith

## Status
Accepted

## Context
The upstream data-collection system (DatarunAPI) sends generic, template-driven submissions. The Ledger requires strict, mathematically pure commands. We need to isolate the mapping/translation logic from the accounting logic without creating an operational nightmare of deploying 15 microservices for a 5-person IT team.

## Decision
We will use a **Modular Monolith** architecture.

- The system runs as a single process (one FastAPI server) sharing a single Database instance.
- The translation logic lives in `backend/app/adapter`. The accounting logic lives in `backend/app/ledger`.
- **Constraint:** The Adapter and Ledger are banned from importing each other's Python classes.
- **Constraint:** The Adapter communicates with the Ledger strictly by making an HTTP POST loopback request to the Ledger's API endpoint.

## Consequences

### Positive
- Perfect domain isolation, allowing us to easily split them into true microservices later if scaling demands it.
- Simplicity of a single `git pull` and single `docker-compose up` for local development.

### Negative
- HTTP loopback adds minor latency compared to in-process calls.
