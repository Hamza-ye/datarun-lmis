# Correlation & Traceability

## Purpose

This document defines how every piece of data is **traceable end-to-end** — from a field worker tapping "Submit" on a mobile device, through the Adapter pipeline, into the Ledger's immutable Event Store, and back again for auditing or error correction. Every hand-off between Bounded Contexts carries explicit correlation identifiers so that no event is ever orphaned or unexplainable.

---

## The ID Chain

Three identifiers thread through the entire system. Together they provide full traceability at every layer.

| Identifier | Origin | Scope | Purpose |
|---|---|---|---|
| **`source_event_id`** | DatarunAPI (submission UID) | Cross-BC (Adapter → Ledger) | Uniquely identifies the real-world action (the field submission). Used for **idempotency** in the Ledger and **provenance** throughout. |
| **`correlation_id`** | Adapter (Layer 1 — Ingestion) | Adapter-internal | Groups a logical event and all its retries/replays into one lineage. Survives DLQ → Replay cycles. |
| **`X-Correlation-ID`** | FastAPI middleware | Per HTTP request | Request-scoped header for logs and observability. Injected by global middleware, consumed by all BCs identically. Not stored in domain tables. |

> [!IMPORTANT]
> `source_event_id` and `correlation_id` serve **different** purposes. `source_event_id` is the business identity of a submission (cross-BC, used for dedup). `correlation_id` is the Adapter's operational lineage tracker (Adapter-internal, groups retries).

---

## End-to-End Trace Path

```
  Mobile App
      │
      ▼
  DatarunAPI ──── submission.uid ──────────────────────────────────────────────┐
      │                                                                       │
      ▼                                                                       │
  ┌───────────────────────────────── Adapter BC ──────────────────────────┐    │
  │                                                                      │    │
  │  Layer 1 (Ingestion)                                                 │    │
  │    → Assigns: correlation_id (UUID)                                  │    │
  │    → Stores:  raw_payload, source_event_id, source_system            │    │
  │    → Status:  RECEIVED                                               │    │
  │                                                                      │    │
  │  Layer 2 (Transformation)                                            │    │
  │    → Stores:  mapped_payload, mapping_id, mapping_version            │    │
  │    → Status:  MAPPED  (or DLQ on failure)                            │    │
  │                                                                      │    │
  │  Layer 3 (Egress)                                                    │    │
  │    → Dispatches: mapped_payload to Ledger                            │    │
  │    → Logs:    adapter_egress_logs (HTTP code, response, timing)      │    │
  │    → Status:  FORWARDED / RETRY_EGRESS / DESTINATION_REJECTED        │    │
  │                                                                      │    │
  └──────────────────────────────────────────────────────────────────────┘    │
      │                                                                       │
      ▼ LedgerCommand contains source_event_id ◄──────────────────────────────┘
  ┌───────────────────────────────── Ledger BC ──────────────────────────┐
  │                                                                      │
  │  Idempotency Guard                                                   │
  │    → Key:   source_event_id (UNIQUE constraint)                      │
  │    → Dedup: rejects if already COMPLETED                             │
  │    → Edits: detects newer version_timestamp → Reversal + Re-apply    │
  │                                                                      │
  │  Approval Gatekeeper                                                 │
  │    → FK:    source_event_id links staged commands to the registry    │
  │                                                                      │
  │  Event Store                                                         │
  │    → Column: source_event_id on every inventory_events row           │
  │    → Audit:  any balance → event → source_event_id → original form  │
  │                                                                      │
  │  In-Transit Registry                                                 │
  │    → Column: transfer_id links Dispatch ↔ Receipt events             │
  │                                                                      │
  └──────────────────────────────────────────────────────────────────────┘
```

---

## Adapter Traceability Detail

### The `adapter_inbox` Record

Every inbound event produces a row in `adapter_inbox` that stores the full transformation context:

| Column | Traceability Role |
|---|---|
| `source_event_id` | Links back to the original DatarunAPI submission |
| `correlation_id` | Groups this event with all its retry/replay descendants |
| `parent_inbox_id` | Points to the previous failed attempt (replay lineage) |
| `payload` | Exact raw JSON from the external system (`raw_payload`) |
| `mapped_payload` | Exact JSON produced by Layer 2 (immutable once stored) |
| `mapping_id` | Contract ID used for this transformation |
| `mapping_version` | Contract version used for this transformation |

> See [Adapter Database Schema](../adapter/database-schema.md) for the complete column list.

### The Ingestion Binding Rule

For every processed inbound event, the system **MUST** store:
- `mapping_id` (contract ID used)
- `mapping_version` (contract version used)
- `mapped_payload` (exact JSON produced before egress)

The stored version is **immutable**. Historical events must always be traceable to both the exact mapping version used and the exact JSON payload produced.

### The Egress Audit Trail

`adapter_egress_logs` records every Layer 3 delivery attempt:

| Column | Traceability Role |
|---|---|
| `inbox_id` (FK) | Links back to the `adapter_inbox` row |
| `contract_version_id` | Mapping rules version used |
| `destination_http_code` | HTTP status from the Ledger |
| `destination_response` | Exact response body |
| `retry_count` | Number of delivery attempts |

---

## Replay Lineage (Adapter DLQ → Retry Chain)

When a DLQ item is replayed, correlation is preserved through a **spawning** mechanism:

1. Original DLQ record's status → `REPROCESSED`.
2. A **new** `adapter_inbox` row is created.
3. The new row inherits the **same** `correlation_id` from the original event.
4. The new row's `parent_inbox_id` points to the failed record's ID.
5. The new row starts at status `RECEIVED` and re-enters the pipeline at Layer 2.

```
  adapter_inbox (original)
    correlation_id: AAA
    status: REPROCESSED
        │
        └──► adapter_inbox (replay)
               correlation_id: AAA       ← inherited
               parent_inbox_id: (original.id)
               status: RECEIVED → MAPPED → FORWARDED
```

This creates an unbounded, traceable chain: any item can be traced backward through `parent_inbox_id` to the very first ingestion attempt, and forward/sideways through `correlation_id` to find all related attempts.

> See [DLQ and Replay](../adapter/dlq-and-replay.md) for full replay logic.

---

## Ledger Traceability Detail

### Cross-BC Join Key: `source_event_id`

The `source_event_id` is the **only** identifier that crosses the Adapter → Ledger boundary. It appears in:

| Table | Role |
|---|---|
| `adapter_inbox.source_event_id` | Adapter's record of the original submission |
| `ledger_idempotency_registry.source_event_id` | Ledger's deduplication key (PK, UNIQUE) |
| `ledger_staged_commands.source_event_id` | FK to idempotency registry (for gated approvals) |
| `inventory_events.source_event_id` | Permanent link from every Event Store row back to origin |

**Audit walk:** Any number in `stock_balances` → find the `inventory_events` rows that produced it → each carries a `source_event_id` → join to `adapter_inbox.source_event_id` → view the exact `raw_payload` and `mapped_payload` → trace to `adapter_egress_logs` for delivery details.

### Reversal Traceability

When a field worker edits a previously submitted form:

1. The Idempotency Guard detects the same `source_event_id` with a newer `version_timestamp`.
2. A `REVERSAL` event is appended to the Event Store, linked to the original event.
3. A new event replaces the old values, sharing the same `source_event_id`.
4. The full history is immutable: `Original → Reversal → Correction`.

### Transfer Traceability

The In-Transit Registry uses `transfer_id` to link **Dispatch** and **Receipt** events across nodes:

```
  Event Store: DEBIT (Dispatch)  ─── transfer_id ───►  In-Transit Registry
                                                              │
  Event Store: CREDIT (Receipt) ◄── transfer_id ────────────┘
```

---

## Request-Level Observability: `X-Correlation-ID`

The `X-Correlation-ID` header is a **cross-cutting concern** managed by FastAPI middleware. It:

- Is injected on every inbound HTTP request (generated if absent).
- Propagates through all internal service calls during that request.
- Appears in structured logs for distributed tracing.
- Is **not** stored in domain tables — it is ephemeral and request-scoped.

> [!NOTE]
> `X-Correlation-ID` is middleware, not domain logic. Auth validation, `ActorContext` enrichment, `X-Correlation-ID` injection, and error formatting are applied identically to all routes (BFF, Ledger, Adapter). See [Composition Overview](../composition/composition-overview.md).

---

## Traceability Invariants

1. **No orphan events.** Every `inventory_events` row has a non-null `source_event_id` that traces to a real-world submission.
2. **No orphan replays.** Every replayed `adapter_inbox` row has a `parent_inbox_id` and an inherited `correlation_id`.
3. **Immutable transformation evidence.** `mapped_payload`, `mapping_id`, and `mapping_version` are stored at transformation time and never overwritten.
4. **Immutable event log.** `inventory_events` is append-only. Corrections are `REVERSAL` events, not updates or deletes.
5. **Delivery audit trail.** Every egress attempt is logged in `adapter_egress_logs` with HTTP code, response, timing, and retry count.
6. **Cross-BC join is explicit.** The Adapter → Ledger boundary is joined exclusively on `source_event_id`. No hidden coupling.

---

## Related Docs

| Topic | Document |
|---|---|
| Adapter Pipeline | [Adapter Overview](../adapter/adapter-overview.md) |
| DLQ & Replay | [DLQ and Replay](../adapter/dlq-and-replay.md) |
| Adapter Schema | [Adapter Database Schema](../adapter/database-schema.md) |
| Ledger Event Store | [Event Store](../ledger/event-store.md) |
| Idempotency Guard | [Idempotency Guard](../ledger/idempotency-guard.md) |
| In-Transit Registry | [In-Transit Registry](../ledger/in-transit-registry.md) |
| Context Map | [Context Map](context-map.md) |
| Auth & Middleware | [Auth & Authorization](auth-and-authorization.md) |
| ADR-006 | [3-Layer Adapter Pipeline](../adrs/006-three-layer-adapter-pipeline.md) |
