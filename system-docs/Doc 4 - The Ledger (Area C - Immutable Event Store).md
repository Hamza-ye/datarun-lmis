# Area C: The Immutable Event Store

This table stores "Facts." Once a row is written here, it is never updated or deleted. If a mistake was made, a **REVERSAL** event is added instead.

**Table Name:** `inventory_events`
*Purpose: The permanent, append-only ledger of all stock movements.*

| Column | Type | Description |
| --- | --- | --- |
| `event_id` | **BigInt (PK)** | Auto-incrementing sequence (global order). |
| `source_event_id` | `String` | Reference to the original submission (links to Area B/E). |
| `node_id` | `String` | Internal ID of the facility or MU. |
| `item_id` | `String` | Internal ID of the commodity (Shared Kernel). |
| `transaction_type` | `Enum` | `RECEIPT`, `ISSUE`, `TRANSFER`, `ADJUSTMENT`, `STOCK_COUNT`, `REVERSAL`. |
| `quantity` | **BigInt** | The delta. Always in **Base Units** (e.g., tablets). |
| `batch_id` | `String (Opt)` | For tracking specific lots/batches. |
| `expiry_date` | `Date (Opt)` | Essential for FEFO (First Expired, First Out) logic. |
| `occurred_at` | `Timestamp` | The "Business Time" (when it happened in the field). |
| `recorded_at` | `Timestamp` | The "System Time" (when the DB wrote the row). |
| `metadata` | `JSONB` | Contextual info (e.g., "Reason: Damaged in transit"). |

---

### Area C: The Stock Projection (Read Model)

Querying the `inventory_events` table to find the current balance of 500 items across 1,000 nodes would be too slow. We use a **Projection** (Materialized View) to store the pre-calculated "Current State."

**Table Name:** `stock_balances`
*Purpose: Fast lookup for current "Stock on Hand."*

| Column | Type | Description |
| --- | --- | --- |
| `node_id` | **String (Composite PK)** | The location. |
| `item_id` | **String (Composite PK)** | The commodity. |
| `batch_id` | **String (Composite PK)** | (Optional) if tracking by batch. |
| `quantity_on_hand` | **BigInt** | The running total. |
| `last_event_id` | `BigInt` | Pointer to the last event processed (for consistency checks). |
| `updated_at` | `Timestamp` | Last time the balance changed. |

---

### The "Absolute Reset" Logic (Stock-Take)

You asked how a standard system handles a `STOCK_COUNT` without knowing consumption. Here is the mathematical execution inside Area C:

1. **The Input:** A command arrives: `Node: A, Item: X, Counted_Qty: 100`.
2. **The Projection Lookup:** The Ledger checks `stock_balances`. It shows `quantity_on_hand: 120`.
3. **The Variance Calculation:**
The Ledger calculates the adjustment needed to reach the physical reality:



In this case: 

4. **The Event Generation:** The Ledger inserts an event into `inventory_events`:
* `transaction_type: ADJUSTMENT` (or `STOCK_COUNT_ADJUSTMENT`)
* `quantity: -20`


5. **The Projection Update:** The `stock_balances` table is updated to `100`.

---

### Handling Reversals (The "Correction" Flow)

If **Area B** detects an edit to a previous form (e.g., the user changed a "Receipt" from 10 to 15), Area C performs a **Symmetrical Reversal**:

1. Find original Event #101 (`RECEIPT`, `+10`).
2. Insert Event #202: `type: REVERSAL`, `qty: -10`, `linked_to: 101`.
3. Insert Event #203: `type: RECEIPT`, `qty: +15`, `source_event_id: "Same_ID"`.
4. Update Projection: The net result on the balance is a simple .

---

### Business Rules (Enforcement)

During the "Commit" to Area C, the Ledger evaluates the **Configuration Hierarchy** policies we defined in Doc 0:

* **Negative Stock Check:** If `policy.negative_stock.behavior = BLOCK` and an `ISSUE` would drop the balance below zero, the Ledger **rejects** the transaction and rolls back.
* **Expiry Check:** If a `RECEIPT` has an `expiry_date` in the past, the Ledger rejects it.

---

### Summary of Area C Integrity

* **Atomicity:** The `inventory_events` insert and the `stock_balances` update happen in a single **Database Transaction**. Either both succeed, or both fail.
* **Auditability:** Because we store the `source_event_id`, you can trace any number in the `stock_balances` table back to the exact ODK form or MU dispatch that caused it.
* **Simplicity:** Area C doesn't care about "Boxes" or "Packs." It only does math on `BigInt` tablets.
