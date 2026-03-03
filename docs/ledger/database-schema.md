# Ledger Database Schema

## Overview

All Ledger tables are owned exclusively by the Ledger Bounded Context. The Adapter has no access to these tables.

## Tables Summary

| Table | Sub-Domain | Purpose |
| --- | --- | --- |
| `ledger_idempotency_registry` | Idempotency Guard | Deduplication and version tracking |
| `ledger_staged_commands` | Approval Gatekeeper | "Waiting Room" for high-impact commands |
| `ledger_approval_audit` | Approval Gatekeeper | Legal record of approvals/rejections |
| `inventory_events` | Event Store | Append-only, immutable event log |
| `stock_balances` | Event Store | CQRS read-model for current stock |
| `ledger_in_transit_registry` | In-Transit Registry | Transfer state machine |
| `ledger_internal_dlq` | In-Transit Registry | Internal orchestration failures |

## Detailed Schemas

For column-level detail for each table, see the sub-domain documents:

- **Idempotency Guard tables:** [idempotency-guard.md](idempotency-guard.md)
- **Approval Gatekeeper tables:** [approval-gatekeeper.md](approval-gatekeeper.md)
- **Event Store tables:** [event-store.md](event-store.md)
- **In-Transit Registry tables:** [in-transit-registry.md](in-transit-registry.md)

## Key Constraints

- `inventory_events`: Append-only. No `UPDATE` or `DELETE` permitted.
- `stock_balances`: `UNIQUE(node_id, item_id)`. OCC via `version` column.
- `ledger_idempotency_registry`: `UNIQUE(source_event_id)`.
- `inventory_events` insert + `stock_balances` update always in a **single DB transaction**.

## Notable Columns Added by Audit

| Column | Table | Purpose |
|---|---|---|
| `adjustment_reason` | `inventory_events` | Sub-type for ADJUSTMENT / STOCK_COUNT events. See [Event Store → Adjustment Reasons](event-store.md#adjustment-reasons). |
| `occurred_at` | `inventory_events` | Business Time (when it happened in the field). Distinct from `created_at` (System Time). See [Event Store → Temporal Ordering](event-store.md#temporal-ordering). |
| `EXPIRED` status | `ledger_staged_commands` | Lifecycle Worker moves stale `AWAITING` commands to `EXPIRED` based on `policy.approval.expiry_days`. See [Approval Gatekeeper → Staged Command Expiry](approval-gatekeeper.md#staged-command-expiry). |
| `LOST_IN_TRANSIT` status | `ledger_in_transit_registry` | Supervisor-initiated write-off for lost goods. See [In-Transit Registry → Loss Write-Off](in-transit-registry.md#loss-write-off-lost_in_transit). |

## Status Enums (Complete Reference)

### `ledger_idempotency_registry.status`
`PROCESSING`, `COMPLETED`, `STAGED`, `FAILED`

### `ledger_staged_commands.status`
`AWAITING`, `APPROVED`, `REJECTED`, `EXPIRED`

### `ledger_in_transit_registry.status`
`OPEN`, `PARTIAL`, `COMPLETED`, `STALE_AUTO_CLOSED`, `FAILED_AUTO_CLOSE`, `LOST_IN_TRANSIT`

### `inventory_events.transaction_type`
`RECEIPT`, `ISSUE`, `TRANSFER`, `ADJUSTMENT`, `STOCK_COUNT`, `REVERSAL`

## Deferred (Post-MVP)

- `batch_id` and `expiry_date` tracking on `inventory_events` (for `policy.expiry.reject_expired_receipts`)
