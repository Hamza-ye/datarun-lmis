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

## Related Docs

- **Inbox schema:** See [Database Schema](database-schema.md) for `adapter_inbox` columns
- **Contract lifecycle:** See [Mapping Contract Lifecycle](mapping-contract-lifecycle.md)
