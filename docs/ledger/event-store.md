# Event Store & Stock Projections (Area C)

## Purpose

The mathematical heart of the system. Area C enforces stock rules, appends immutable events, and maintains the stock balance projections.

## The Event Store (Write Model)

**Table:** `ledger_inventory_events` — Permanent, append-only ledger of all stock movements.

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Universal unique identifier |
| `source_event_id` | String | Reference to the original submission (links to Idempotency Guard) |
| `node_id` | String | Internal ID of the facility or MU |
| `item_id` | String | Internal ID of the commodity (from Shared Kernel) |
| `transaction_type` | Enum | `RECEIPT`, `ISSUE`, `TRANSFER`, `ADJUSTMENT`, `STOCK_COUNT`, `REVERSAL` |
| `quantity` | BigInt | Absolute delta. Always in **Base Units** |
| `adjustment_reason` | String (nullable) | Sub-type for ADJUSTMENT / STOCK_COUNT events (see [Adjustment Reasons](#adjustment-reasons)) |
| `running_balance` | BigInt | Snapshot of the balance at insertion time (system-time order) |
| `occurred_at` | Timestamp | Business Time (when it happened in the field) |
| `created_at` | Timestamp | System Time (when the DB wrote the row) |

> **Invariant:** Once a row is written, it is **never updated or deleted**. Corrections are `REVERSAL` events.

## Stock Projections (Read Model)

**Table:** `ledger_stock_balances` — Fast lookup for current "Stock on Hand."

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Surrogate key |
| `node_id` | String | Location (unique with `item_id`) |
| `item_id` | String | The commodity |
| `quantity` | BigInt | Running total |
| `version` | Integer | OCC guard — increments on every update |
| `last_updated` | Timestamp | Last balance change |

## Optimistic Concurrency Control (OCC)

Prevents race conditions when two commands affect the same `node_id` + `item_id` simultaneously.

1. **Read:** `quantity: 100, version: 5`
2. **Math:** RECEIPT of 10 → target `quantity: 110, version: 6`
3. **Atomic Update:** `UPDATE ledger_stock_balances SET quantity = 110, version = 6 WHERE node_id = 'A' AND item_id = 'X' AND version = 5`
4. **Guard:** If another thread updated to version 6 first, our `WHERE version = 5` affects 0 rows.
5. **Retry:** Throws `StaleObjectException`, re-reads, recalculates, commits.

## The "Absolute Reset" Logic (Stock-Take)

1. **Input:** `Node: A, Item: X, Counted_Qty: 100`
2. **Projection Lookup:** `stock_balances` shows `quantity_on_hand: 120`
3. **Variance:** `100 - 120 = -20`
4. **Event Generated:** `transaction_type: STOCK_COUNT`, `quantity: -20`, `adjustment_reason: STOCK_COUNT_VARIANCE`
5. **Projection Updated:** `ledger_stock_balances` updated to `100`

## Handling Reversals (Correction Flow)

When the Idempotency Guard detects an edit (e.g., Receipt changed from 10 to 15):

1. Find original Event #101 (`RECEIPT`, `+10`)
2. Insert Event #202: `type: REVERSAL`, `qty: -10`, `linked_to: 101`
3. Insert Event #203: `type: RECEIPT`, `qty: +15`, `source_event_id: same`
4. Update Projection: net result `+5`

## Business Rules (Enforcement)

During commit, the Ledger evaluates the Configuration Hierarchy policies:

- **Negative Stock Check:** If `policy.negative_stock.behavior = BLOCK` and an ISSUE would drop the balance below zero → **reject** and rollback.
- **Expiry Check (Deferred):** If `policy.expiry.reject_expired_receipts = TRUE` and a RECEIPT has an `expiry_date` in the past → **reject**. See [Configuration Hierarchy](../architecture/configuration-hierarchy.md) for policy details. Requires `batch_id` and `expiry_date` columns (post-MVP).

## Atomicity Guarantee

The `ledger_inventory_events` insert and the `ledger_stock_balances` update happen in a **single Database Transaction**. Either both succeed, or both fail.

## Temporal Ordering

The Event Store distinguishes two timestamps on every event:

| Timestamp | Name | Role |
|---|---|---|
| `created_at` | System Time | When the DB wrote the row. Determines insertion order and `running_balance` calculation. |
| `occurred_at` | Business Time | When the event happened in the field. Used for time-based reporting. |

**Rules:**

1. `running_balance` is computed in **system-time order** (insertion order). It is a performance optimization for current-state queries, not a historical truth.
2. Events are **never re-ordered after insertion**. If two events arrive out of business-time order, `running_balance` reflects system-time order.
3. Historical balance queries ("stock on hand on March 1st") must be computed by summing events with `occurred_at <= target_date`, not by reading `running_balance`.

## Backdated Events (Offline Submissions)

Field workers frequently go offline and submit events with `occurred_at` timestamps days or weeks in the past. The Ledger handles these as follows:

1. The event is processed normally — the Idempotency Guard checks `source_event_id` for dedup regardless of `occurred_at`.
2. The `running_balance` is calculated against the **current** balance (system-time order), not the balance at the backdated `occurred_at`.
3. For STOCK_COUNT: the variance is calculated against today's balance. A stock count backdated 5 days ago does **not** retroactively recalculate events processed in between.

> **Design Choice:** Retroactive re-ordering would require replaying all subsequent events — an expensive operation that introduces its own correctness risks. Instead, the system treats backdated events as "late arrivals" that apply to the current state.

## Adjustment Reasons

The `ADJUSTMENT` transaction type covers multiple real-world scenarios with **different audit risk profiles**. To allow auditors to distinguish them, every ADJUSTMENT and STOCK_COUNT event should carry an `adjustment_reason`:

| `adjustment_reason` | Triggered By | Risk Profile |
|---|---|---|
| `STOCK_COUNT_VARIANCE` | Stock-take "Absolute Reset" logic | Routine — expected during physical counts |
| `DAMAGE` | Manual correction for damaged goods | Medium — requires documentation |
| `EXPIRY` | Manual write-off for expired stock | Medium — may indicate ordering problems |
| `FOUND_STOCK` | Unexpected surplus discovered | Medium — investigate source |
| `LOSS_IN_TRANSIT` | In-Transit write-off (see [In-Transit Registry](in-transit-registry.md)) | High — potential theft or logistics failure |
| `ADMINISTRATIVE` | Catch-all for supervisor-initiated corrections | High — requires justification |

> This field is **metadata**, not a new transaction type. The `transaction_type` enum remains fixed (6 canonical types). `adjustment_reason` is a **⚙️ Policy-level** addition — the set of valid reasons is configurable and may grow.

## Related Docs

- **Previous step:** [Approval Gatekeeper](approval-gatekeeper.md)
- **Transfer orchestration:** [In-Transit Registry](in-transit-registry.md)
- **All tables:** [Database Schema](database-schema.md)
- **Temporal concerns:** [Correlation & Traceability](../architecture/correlation-traceability.md)
