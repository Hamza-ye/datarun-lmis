# Adapter (ACL) Constitution — Datarun Health LMIS

The Adapter (ACL) is a 3-Layer Event Gateway (Ingestion → Transformation → Egress) that translates Data-Collection payloads into Domain Commands and guarantees reliable delivery. Its scope is strictly structural translation.

MAY:
- Map fields and shapes deterministically (JSONPath + deterministic ops).
- Resolve crosswalks/lookups from read-only reference stores.
- Normalize units and types.
- Add provenance metadata (source_event_id, contract_version).
- Retry transient transport failures.
- Push to DLQ on permanent mapping failure or destination business rejection.
- Store `raw_payload` (Ingress) and `mapped_payload` (Post-Transform) for absolute traceability.

MUST NOT:
- Execute downstream business logic (e.g., stock calculations, permissions).
- Fetch data dynamically from downstream domains during mapping.

## The 3-Layer Architecture
1. **Ingestion (Layer 1):** Receives payload, validates structure, stores `raw_payload`, returns `202 Accepted`. Target state: `RECEIVED`.
2. **Transformation (Layer 2):** Applies `ACTIVE` mapping contract, executes logic, stores `mapped_payload`. Target states: `MAPPED` (success) or `DLQ` (mapping error).
3. **Egress (Layer 3):** Dispatches to domain. Target states: `FORWARDED` (success), `RETRY_EGRESS` (network error), or `DESTINATION_REJECTED` (domain HTTP 4xx). MUST never re-run transformation; it can only use the stored `mapped_payload`.

VERSIONING:
- Every mapping contract must be versioned and include `sample_in.json` and `expected_out.json` tests.

---


## ROLES & LIFECYCLE (CONCISE)
## Mapping Contract Lifecycle (Minimal)

### Statuses

- DRAFT
- REVIEW
- APPROVED
- ACTIVE
- DEPRECATED
- ARCHIVED
- REJECTED

---

## Mapping Contract Lifecycle — Minimal 

Unique (id, and version)

### Statuses

- DRAFT
- REVIEW
- APPROVED
- ACTIVE
- DEPRECATED
- ARCHIVED
- REJECTED

---

## Transitions & Guards

### DRAFT → REVIEW
Guard:
- `sample_in.json` and `expected_out.json` exist.

---

### REVIEW → APPROVED
Guard:
- Mapping test (sample → expected) passes.
- Test result metadata stored for this version.

---

### REVIEW → REJECTED
Guard:
- Rejection reason recorded.

---

### APPROVED → ACTIVE
Guards:
- Only one `ACTIVE` version per contract's id.
- Activation must be atomic.
  - Either previous `ACTIVE` becomes `DEPRECATED` automatically,
  - Or activation is blocked until no other `ACTIVE` exists.

---

### ACTIVE → DEPRECATED
Guard:
- `Deprecated` versions are not used for new processing.
- `Deprecated` versions remain valid for replay.

---

### DEPRECATED → ARCHIVED
Guard:
- `Archived` versions are read-only and removed from active UI (kept for audit).

---

## Rollback

Rollback is performed by activating a previous `APPROVED` or `DEPRECATED` version.

Rules:
- Rollback is an atomic `ACTIVE` switch.
- No data mutation occurs.
- Previously processed events are NOT reprocessed automatically.

---

## Replay

Replay must explicitly specify:
- contract's id
- contract's version

Rules:
- Replay bypasses Layer 1 (Ingestion router).
- Replay explicitly targets Layer 2 (Transformation) using the exact stored DSL of that version.
- Replay must not silently use the current `ACTIVE` version unless explicitly requested as a new submission.
- Replay results must be traceable and logged with inherited `correlation_id`.

---

## Ingestion Binding Rule

For every processed inbound event, the system MUST store:

- contract's id
- contract's version
- `mapped_payload` (The exact JSON produced before egress)

Rules:
- Processing uses the `ACTIVE` version at ingestion time.
- The stored version is immutable.
- Historical events must always be traceable to both the exact mapping version used and the exact JSON payload produced.

