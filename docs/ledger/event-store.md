# Event Store & Stock Projections (Area C)

## Purpose

The mathematical heart of the system. Area C enforces stock rules, appends immutable events, and maintains the stock balance projections.

## The Event Store (Write Model)

**Table:** `inventory_events` — Permanent, append-only ledger of all stock movements.

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Universal unique identifier |
| `source_event_id` | String | Reference to the original submission (links to Idempotency Guard) |
| `node_id` | String | Internal ID of the facility or MU |
| `item_id` | String | Internal ID of the commodity (from Shared Kernel) |
| `transaction_type` | Enum | `RECEIPT`, `ISSUE`, `TRANSFER`, `ADJUSTMENT`, `STOCK_COUNT`, `REVERSAL` |
| `quantity` | BigInt | Absolute delta. Always in **Base Units** |
| `running_balance` | BigInt | Snapshot of the balance at insertion time |
| `occurred_at` | Timestamp | Business Time (when it happened in the field) |
| `created_at` | Timestamp | System Time (when the DB wrote the row) |

> **Invariant:** Once a row is written, it is **never updated or deleted**. Corrections are `REVERSAL` events.

## Stock Projections (Read Model)

**Table:** `stock_balances` — Fast lookup for current "Stock on Hand."

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
3. **Atomic Update:** `UPDATE stock_balances SET quantity = 110, version = 6 WHERE node_id = 'A' AND item_id = 'X' AND version = 5`
4. **Guard:** If another thread updated to version 6 first, our `WHERE version = 5` affects 0 rows.
5. **Retry:** Throws `StaleObjectException`, re-reads, recalculates, commits.

## The "Absolute Reset" Logic (Stock-Take)

1. **Input:** `Node: A, Item: X, Counted_Qty: 100`
2. **Projection Lookup:** `stock_balances` shows `quantity_on_hand: 120`
3. **Variance:** `100 - 120 = -20`
4. **Event Generated:** `transaction_type: ADJUSTMENT`, `quantity: -20`
5. **Projection Updated:** `stock_balances` updated to `100`

## Handling Reversals (Correction Flow)

When the Idempotency Guard detects an edit (e.g., Receipt changed from 10 to 15):

1. Find original Event #101 (`RECEIPT`, `+10`)
2. Insert Event #202: `type: REVERSAL`, `qty: -10`, `linked_to: 101`
3. Insert Event #203: `type: RECEIPT`, `qty: +15`, `source_event_id: same`
4. Update Projection: net result `+5`

## Business Rules (Enforcement)

During commit, the Ledger evaluates the Configuration Hierarchy policies:

- **Negative Stock Check:** If `policy.negative_stock.behavior = BLOCK` and an ISSUE would drop the balance below zero → **reject** and rollback.
- **Expiry Check:** If a RECEIPT has an `expiry_date` in the past → **reject**.

## Atomicity Guarantee

The `inventory_events` insert and the `stock_balances` update happen in a **single Database Transaction**. Either both succeed, or both fail.

## Related Docs

- **Previous step:** [Approval Gatekeeper](approval-gatekeeper.md)
- **Transfer orchestration:** [In-Transit Registry](in-transit-registry.md)
- **All tables:** [Database Schema](database-schema.md)
