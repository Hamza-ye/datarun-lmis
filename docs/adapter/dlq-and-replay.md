# DLQ and Replay

## Overview

The Adapter uses a **Unified Inbox** strategy. Failed items stay in `adapter_inbox` with status `DLQ` — there is no separate DLQ table. This simplifies tracking and avoids cross-table joins.

## DLQ States

When a payload fails, its status in `adapter_inbox` changes according to the failure layer:

| Status | Cause | Layer |
| --- | --- | --- |
| `DLQ` | Missing crosswalk, invalid cast, DSL failure | Layer 2 (Transformation) |
| `DESTINATION_REJECTED` | Ledger rejected with HTTP 4xx | Layer 3 (Egress) |
| `RETRY_EGRESS` | Network timeout, HTTP 5xx | Layer 3 (Egress) |

The `error_message` column records exactly why it failed.

## The Error Correction Loop

1. **The Mistake:** A clinic sends a code the Adapter has never seen (e.g., `PARAM-BOX-200`).
2. **Adapter Fallback:** Based on config (`on_unmapped: DLQ`), the Adapter stops the pipeline. Marks the `adapter_inbox` row as `DLQ` with the error reason.
3. **Admin Fix:** The administrator checks the DLQ view, sees the missing crosswalk, and adds the new mapping rule.
4. **Replay:** The admin submits a Replay request via `POST /admin/dlq/{id}/replay`.

## Replay Logic

### The Spawning Process

1. The original DLQ record's status changes to `REPROCESSED`.
2. A **new** record is created in `adapter_inbox` with the corrected payload.
3. The new record inherits the same `correlation_id` from the original event.
4. The new record's `parent_inbox_id` points to the failed record's ID.
5. The new record's status is `RECEIVED`.

### Replay Rules

- Replay **bypasses Layer 1** (Ingestion router).
- Replay explicitly targets **Layer 2** (Transformation) using the exact stored DSL of the specified version.
- Replay must **not** silently use the current `ACTIVE` version unless explicitly requested as a new submission.
- Replay results must be traceable and logged with inherited `correlation_id`.
- The contract `id` and `version` must be explicitly specified.

### Processing

The asynchronous worker picks up the new `RECEIVED` row exactly as if it were a brand-new submission, guaranteeing that retries respect all idempotency and validation rules natively.

## Ingestion Binding Rule

For every processed inbound event, the system MUST store:
- `mapping_id` (contract ID used)
- `mapping_version` (contract version used)
- `mapped_payload` (exact JSON produced before egress)

The stored version is **immutable**. Historical events must always be traceable to both the exact mapping version used and the exact JSON payload produced.

## HTTP Failure Handling (Retry Policy)

Not all HTTP failures are equal. The worker distinguishes **client errors** (Adapter's fault — retrying won't help) from **server errors** (destination temporarily down — retrying should help):

| HTTP Status | Classification | Behaviour |
|---|---|---|
| 2xx | Success | Mark `FORWARDED` |
| 400, 422 | Client Error | Mark `DESTINATION_REJECTED` immediately. Retrying won't help — the Adapter's output is structurally wrong. |
| 5xx, timeout | Server Error | Mark `RETRY_EGRESS`. Retry with exponential backoff. After max attempts, mark `DLQ` with reason `destination_unreachable`. |

### Retry Parameters

| Parameter | Default | Description |
|---|---|---|
| `max_egress_retries` | 3 | Maximum delivery attempts before DLQ |
| `backoff_base_seconds` | 2 | Base for exponential backoff (2, 4, 8...) |

> **Invariant:** A payload must never be silently dropped due to a transient network failure. The retry mechanism is the safety net between the Adapter's "no silent drops" invariant and the reality of unreliable networks.

## Bulk Replay

When a mapping fix affects many records, an admin can replay all matching DLQ records in a single bulk operation:

1. Admin selects DLQ records by filter (e.g., matching `error_message`, `mapping_id`, or date range).
2. The system creates a job in `adapter_admin_jobs` tracking `job_type: REPLAY`, `triggered_by`, and `affected_records_count`.
3. Each record is replayed individually (same mechanics as single replay — new inbox row, inherited `correlation_id`, `parent_inbox_id` linkage).
4. The job record tracks `success_count` and `failure_count` for post-operation audit.

See [Database Schema → adapter_admin_jobs](database-schema.md) for the tracking table.

## Multi-Command Replay Safety

When a replayed payload produces multiple Ledger commands (see [Mapping DSL → Multi-Command Output](mapping-dsl-reference.md#multi-command-output-one-payload--multiple-commands)):

- Each command carries a deterministic `source_event_id` derived from the payload's source ID + template/iterator indices.
- On replay, the same `source_event_id` values are regenerated.
- Commands already successfully forwarded in the first attempt are **deduplicated by the Ledger's idempotency guard** — no double-counting.
- Only previously-failed commands (never forwarded, or destination-rejected) result in new Ledger entries.

> **Invariant:** Replay must be **idempotent at the Ledger level**. Replaying a partially-forwarded payload must not produce duplicate stock movements.

## Related Docs

- **Inbox schema:** See [Database Schema](database-schema.md) for `adapter_inbox` columns
- **Contract lifecycle:** See [Mapping Contract Lifecycle](mapping-contract-lifecycle.md)
- **Multi-command atomicity:** See [Mapping DSL Reference](mapping-dsl-reference.md#multi-command-output-one-payload--multiple-commands)
- **Correlation traceability:** See [Architecture → Correlation & Traceability](../architecture/correlation-traceability.md)
