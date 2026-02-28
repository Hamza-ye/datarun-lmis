# ADR: 3-Layer Adapter Pipeline (Ingestion, Transformation, Egress)

## Status
Proposed

## Context
The current Datarun Adapter architecture processes incoming payloads in a single, monolithic background worker flow: it receives the payload, executes the mapping DSL, and forwards the HTTP request to the destination within the same logical execution boundary.

While this works, it lacks strict observability and traceability when failures occur. Specifically:
- A failure during the mapping phase (e.g., missing dictionary crosswalk) results in a `DLQ` state, but it is conflated with the original ingestion record.
- A failure during the delivery phase (e.g., Destination HTTP timeout or Destination Business Rejection) is difficult to distinguish from an internal mapping crash without parsing text logs.
- There is no durable record of the *exact mapped JSON payload* that was generated prior to the HTTP forward attempt.

To align with Domain-Driven Design (DDD) and Enterprise Integration Patterns (EIP), the Adapter must act as a structured Message Translator and Content-Based Router with clear boundaries.

## Decision
We will refactor the Adapter pipeline into three logically distinct, asynchronous layers driven by a single state machine. 
**Crucial Distinction:** This means separate worker loops and strict state transitions within the same service, **NOT** separate microservices, queues, or deploy units. We avoid over-physicalization by using a single primary inbox table.

### Layer 1: Ingestion (The "I Saw It" Layer)
**Responsibility:** Receive the payload from the external source, assign a correlation ID, persist it durability, and immediately return a `202 Accepted` to the caller.
- **Boundaries:** No mapping rules or destination knowledge. Standard HTTP/JSON validation only.
- **Data Model:** `adapter_inbox`
- **Metadata Stored:** `source_system`, `raw_payload`, `received_at`, `ingress_headers`, `source_event_id`.
- **Target State:** `RECEIVED` (Ready for transformation).

### Layer 2: Transformation (The "I Translated It" Layer)
**Responsibility:** Pick up `RECEIVED` payloads, resolve the `ACTIVE` mapping contract, execute the DSL engine (including crosswalk dictionary lookups), and generate the target domain Command (e.g., Ledger Command).
- **Boundaries:** **Zero network calls** to the destination. Purely structural transformation.
- **Data Model:** `adapter_inbox` (advancing the state of the existing record)
- **Metadata Stored:** `contract_id`, `contract_version`, **`mapped_payload`** (the exact JSON output), `transformation_time_ms`.
- **Target State Transitions:**
  - Success -> `MAPPED` (Ready for egress).
  - Mapping Error (missing dictionary, invalid cast) -> `DLQ` (Requires Admin to fix contract and Replay).

### Layer 3: Egress / Delivery (The "I Delivered It" Layer)
**Responsibility:** Pick up `MAPPED` payloads and reliably dispatch them via HTTP `POST` to the target domain (e.g., Ledger). Handle transport failures (timeouts) and domain-level business rejections (HTTP 4xx).
- **Invariant:** Layer 3 MUST never re-run transformation. It can only use the stored `mapped_payload`.
- **Boundaries:** No mapping execution. Purely acts as a reliable courier.
- **Data Model:** `adapter_inbox` (advancing state) + `adapter_egress_logs` (replaces conflated `AdapterLogs` for HTTP trace history)
- **Metadata Stored:** `destination_url`, `http_status_code`, `response_payload`, `retry_count`, `delivery_time_ms`.
- **Target State Transitions:**
  - Success (HTTP 2xx) -> `FORWARDED`.
  - Transport Failure (HTTP 5xx, Network Timeout) -> `RETRY_EGRESS`.
  - Destination Rejection (HTTP 4xx - Business Rule Violation) -> `DESTINATION_REJECTED` (Indicates the Adapter succeeded, but reality/domain refused the action).

## Consequences
### Positive
1. **Air-Tight Finger Pointing:** Instantly know if an error belongs to the Data Collection (bad payload), the Adapter (bad mapping contract), or the Ledger (failed business invariant).
2. **Auditability:** We can mathematically prove exactly what the Adapter produced (`mapped_payload`) before it was sent over the network.
3. **Resilience:** If the Ledger goes offline for 12 hours, Layer 1 and 2 continue to run at full speed, buffering perfectly mapped commands in the `MAPPED` state until Layer 3 can recover.

### Negative
- Increases database storage slightly because we now store both the `raw_payload` (Layer 1) and the `mapped_payload` (Layer 2).
- Requires updating the `engine.py` models and splitting the background worker logic.
