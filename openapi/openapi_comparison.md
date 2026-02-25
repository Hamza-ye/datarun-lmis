# API vs Architecture Comparison

This document compares the current `openapi.yaml` implementation against the strict requirements defined in the System Docs (Docs 1-7). 

| Endpoint / Area | Status | Confidence | Note |
| :--- | :--- | :--- | :--- |
| **Authentication (Doc 7)** | | | |
| `GET /api/auth/me` | MATCH | HIGH | Implemented correctly. JWT payload successfully extracts `actor_id`, `roles`, and `allowed_nodes`. |
| `Bearer Security Scheme` | MATCH | HIGH | Implemented in FastAPI Dependency Injection (`get_current_actor`). |
| **Adapter Area (Doc 1)** | | | |
| `POST /api/adapter/inbox` | MATCH | HIGH | Accurately accepts `ExternalPayload` array. Correctly rejects unauthenticated sources. |
| `GET /api/adapter/admin/contracts` | MATCH | HIGH | API exists. UI can list Mapping DSLs. |
| `POST /api/adapter/admin/contracts` | MATCH | HIGH | API exists for creating Mapping DSLs. |
| `POST /api/adapter(...)/activate` | MATCH | HIGH | Atomic flip for DSL rules exists. |
| `GET /api/adapter/admin/dlq` | MATCH | HIGH | API exists for Dead Letter Queue review. |
| `POST /api/adapter/admin/dlq/{id}/retry`| MISSING_IN_CODE | HIGH | The DLQ review API exists, but the UI needs a way to actually trigger the retry of a failed payload after fixing the mapping. |
| **Idempotency & Approval (Doc 3)** | | | |
| `POST /api/ledger/commands` | MATCH | HIGH | Internal API gateway for normalized commands. Correctly handles Idempotency Guard (Area B). |
| `GET /api/ledger/gatekeeper/staged` | MISSING_IN_CODE | HIGH | Supervisors need an inbox to view `AWAITING` commands. The resolution endpoint exists, but the list endpoint is missing. |
| `POST /api/ledger/gatekeeper/{id}/resolve`| MATCH | HIGH | Exists and expects `ACTION` (Approve/Reject) with optional `comment`. |
| **Event Store & Read Models (Doc 4)** | | | |
| `GET /api/ledger/balances` | MATCH | HIGH | Proper CQRS DTO (`StockBalanceResponse`) is returned, abstracted away from the raw Event DB rows. |
| `GET /api/ledger/history/{node}/{item}` | MATCH | HIGH | DTO (`LedgerHistoryResponse`) implemented. Correctly asserts the user has access to `node_id`. |
| **In-Transit Registry (Doc 5)** | | | |
| `GET /api/ledger/transfers` | MISSING_IN_CODE | HIGH | The UI will need to list pending incoming/outgoing transfers for a node. Backend domain exists, API does not. |
| `POST /api/ledger/transfers/{id}/receive` | MISSING_IN_CODE | HIGH | The UI needs an endpoint to mark a dispatched transfer as received. |
| **Shared Kernel (Doc 6)** | | | |
| `GET /api/kernel/nodes` | MATCH | HIGH | Exists for Topology tree rendering. |
| `GET /api/kernel/nodes/all` | MATCH | HIGH | Exists for resolution of IDs. |
| `POST /api/kernel/nodes/resolve` | MATCH | HIGH | Bulk resolution implemented. |
| `POST /api/kernel/nodes/{node_id}/topology-correction` | MATCH | HIGH | SCD Type 2 time-travel correction implemented. |
| `GET /api/kernel/commodities` | MATCH | HIGH | Exists for dropdowns. |
| `POST /api/kernel/policies` | MATCH | HIGH | Exists to configure hierarchical rules (approval thresholds, negative stock blocks). |

## Schema Discrepancies

1. **Gatekeeper Action Payload**: The `/api/ledger/gatekeeper/{staged_id}/resolve` endpoint request body shows as a generic `Object` in OpenAPI rather than a strongly typed Pydantic Schema. *Requires Confirmation* on building a strict `ApprovalAction` schema.
2. **Global Error Envelopes**: The `HTTPValidationError` and `500 Internal Server Error` responses lack explicit OpenAPI type schemas defining the `X-Correlation-ID` header required by the architecture. *Implementation exists in code* via `correlation_id_middleware` and `exception_handler`, but it is not formally serialized in the OpenAPI spec.
