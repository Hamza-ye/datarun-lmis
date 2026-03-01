# ADR-006: 3-Layer Adapter Pipeline (Ingestion, Transformation, Egress)

## Status
Accepted

## Context
The original Adapter architecture processed incoming payloads in a single, monolithic background worker flow: receive, map, and forward within the same logical execution boundary.

While this works, it lacks strict observability and traceability when failures occur:
- A failure during mapping is conflated with the ingestion record.
- Delivery failures are difficult to distinguish from mapping crashes without parsing text logs.
- There is no durable record of the *exact mapped JSON payload* generated prior to the HTTP forward attempt.

## Decision
We will refactor the Adapter pipeline into three logically distinct, asynchronous layers driven by a single state machine.

**Crucial Distinction:** This means separate worker loops and strict state transitions within the same service, **NOT** separate microservices, queues, or deploy units.

### Layer 1: Ingestion
**Responsibility:** Receive payload, assign correlation ID, persist durably, return `202 Accepted`.
- **Boundaries:** No mapping rules or destination knowledge.
- **Target State:** `RECEIVED`

### Layer 2: Transformation
**Responsibility:** Pick up `RECEIVED` payloads, resolve `ACTIVE` mapping contract, execute DSL engine, generate domain Command.
- **Boundaries:** Zero network calls to the destination. Purely structural transformation.
- **Stored:** `contract_id`, `contract_version`, `mapped_payload`, `transformation_time_ms`
- **Target States:** `MAPPED` (success) or `DLQ` (mapping error)

### Layer 3: Egress / Delivery
**Responsibility:** Pick up `MAPPED` payloads and dispatch via HTTP POST.
- **Invariant:** Layer 3 MUST never re-run transformation. It can only use the stored `mapped_payload`.
- **Target States:** `FORWARDED` (2xx), `RETRY_EGRESS` (5xx/timeout), `DESTINATION_REJECTED` (4xx)

## Consequences

### Positive
1. **Finger Pointing:** Instantly know if an error belongs to Data Collection (bad payload), Adapter (bad mapping), or Ledger (failed invariant).
2. **Auditability:** Can prove exactly what the Adapter produced (`mapped_payload`) before it was sent.
3. **Resilience:** If the Ledger goes offline, Layers 1 and 2 continue buffering `MAPPED` commands.

### Negative
- Increases database storage slightly (both `raw_payload` and `mapped_payload` stored).
- Requires splitting background worker logic into separate loops.
