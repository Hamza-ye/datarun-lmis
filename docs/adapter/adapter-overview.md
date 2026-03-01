# Adapter (ACL) — Overview

## Role in the Architecture

The Adapter functions as an **Anti-Corruption Layer (ACL)** between flexible Data-Collection inputs and strict domain services. Its responsibilities are structural translation, normalization, and reliable delivery. The Adapter and the Ledger share **zero database tables** — they are completely blind to each other's internal states.

## Constitution

**MAY:**
- Map fields/shapes deterministically (JSONPath + deterministic ops)
- Resolve crosswalks/lookups from read-only reference stores
- Normalize units and types
- Add provenance metadata (`source_event_id`, `contract_version`)
- Retry transient transport failures
- Push to DLQ on permanent mapping failure or destination business rejection
- Store `raw_payload` (Ingress) and `mapped_payload` (Post-Transform) for traceability

**MUST NOT:**
- Execute downstream business logic (e.g., stock calculations, permissions)
- Fetch data dynamically from downstream domains during mapping

## The 3-Layer Pipeline ([ADR-006](../adrs/006-three-layer-adapter-pipeline.md))

The Adapter is a 3-Layer Event Gateway (Ingestion → Transformation → Egress):

### Layer 1: Ingestion
- Receives payload, validates structure, stores `raw_payload`
- Returns `202 Accepted` immediately
- Target state: `RECEIVED`

### Layer 2: Transformation
- Applies `ACTIVE` mapping contract, executes DSL logic
- Stores `mapped_payload`
- Target states: `MAPPED` (success) or `DLQ` (mapping error)

### Layer 3: Egress
- Dispatches `mapped_payload` to domain endpoint
- **Invariant:** Never re-runs transformation; only uses stored `mapped_payload`
- Target states: `FORWARDED` (2xx), `RETRY_EGRESS` (5xx/timeout), `DESTINATION_REJECTED` (4xx)

## Decoupling Philosophy

- The Adapter has its own configuration database. It does not query the Ledger.
- Crosswalk mappings are configured in the Adapter's own `adapter_crosswalks` table.
- We can swap out the Ledger entirely; the Adapter just points its URL somewhere else.
- We can have 10 different Adapters (ODK, DHIS2, custom Web App) — the Ledger doesn't care.

## Related Docs

| Topic | Document |
| --- | --- |
| Mapping DSL schema | [Mapping DSL Reference](mapping-dsl-reference.md) |
| Database tables | [Database Schema](database-schema.md) |
| DLQ & Replay | [DLQ and Replay](dlq-and-replay.md) |
| Contract lifecycle | [Mapping Contract Lifecycle](mapping-contract-lifecycle.md) |
| Edge cases | [Adapter Edge Cases](edge-cases.md) |
| Test fixtures | [Test Fixtures](test-fixtures/) |
