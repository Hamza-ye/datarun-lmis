# In-Transit Registry (Area D)

## Purpose

Solves the "Black Hole" problem in logistics: stock that has left the Warehouse but hasn't yet arrived at the Clinic. Manages the **state machine** of a movement across time.

## Registry Table

**Table:** `ledger_in_transit_registry`

| Column | Type | Description |
| --- | --- | --- |
| `transfer_id` | UUID (PK) | Unique ID for the movement (linked to Dispatch event) |
| `source_node_id` | String | Where it came from |
| `dest_node_id` | String | Where it is going |
| `item_id` | String | The commodity |
| `qty_shipped` | BigInt | Total sent (Base Units) |
| `qty_received` | BigInt | Total acknowledged by destination so far |
| `status` | Enum | `OPEN`, `PARTIAL`, `COMPLETED`, `STALE_AUTO_CLOSED`, `FAILED_AUTO_CLOSE`, `LOST_IN_TRANSIT` |
| `dispatched_at` | Timestamp | When the DEBIT from source was recorded |
| `auto_close_after` | Timestamp (nullable) | Calculated deadline from Config Hierarchy |
| `created_at` | Timestamp | Record creation |
| `updated_at` | Timestamp | Last status change |

### Internal DLQ

**Table:** `ledger_internal_dlq` — Catches failures in internal orchestration (e.g., auto-receipt failing).

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Unique error ID |
| `source_process` | String | e.g., `AREA_D_AUTO_RECEIPT` |
| `reference_id` | String | Link to the failed `transfer_id` |
| `error_message` | String | Exception reason from the Event Store |
| `created_at` | Timestamp | When the failure occurred |

## Multi-Step Transfer Flow

### Step 1: Dispatch (Departure)

1. Warehouse sends a "Dispatch" command.
2. Idempotency Guard & Approval Gatekeeper verify.
3. Event Store executes a `DEBIT` from the Warehouse.
4. In-Transit Registry creates a record with `status: OPEN`.
5. *The Clinic's balance has NOT changed yet.*

### Step 2: Receipt (Arrival)

1. Clinic sends a "Receipt" command, referencing the `transfer_id`.
2. Registry validates:
   - `qty_received == qty_shipped` → Event Store CREDITs Clinic; status = `COMPLETED`.
   - `qty_received < qty_shipped` → Event Store CREDITs partial amount; status = `PARTIAL`.

## Auto-Confirm Logic (Closing the Loop)

A background Cron worker runs nightly:

1. **Policy Lookup:** For every `OPEN` record, asks the PolicyResolver: *"What is `auto_receive_days` for this destination node?"*
2. **Comparison:** If `Current_Date > dispatched_at + auto_receive_days`:
   - Calculates remaining balance: `qty_shipped - qty_received`
   - Generates a System Event: `type: CREDIT, reason: AUTO_RECEIPT`
   - Event Store processes the credit to update the Clinic's stock.
   - Registry marks the record as `STALE_AUTO_CLOSED`.

### Internal Error Boundary

If the auto-receive attempt fails (e.g., destination Clinic is disabled in the Shared Kernel):

1. Event Store throws a validation exception.
2. Registry updates the status to `FAILED_AUTO_CLOSE`.
3. Registry writes to `ledger_internal_dlq`:
   - `source_process: AREA_D_AUTO_RECEIPT`
   - `reference_id: transfer_id`
   - `error_message: "Node deactivated in Shared Kernel"`
4. System alert generated for administrator investigation.

## Loss Write-Off (LOST_IN_TRANSIT)

Goods are regularly lost, stolen, or damaged in transit — especially in remote supply chains. Without an explicit mechanism, lost shipments either stay in `OPEN` limbo indefinitely, get silently auto-received (fabricating a receipt for goods that never arrived), or require unexplained manual ADJUSTMENT events that break the audit trail.

### The Write-Off Flow

1. A supervisor submits a `LedgerCommand` with `transaction_type: ADJUSTMENT`, `adjustment_reason: 'LOSS_IN_TRANSIT'`, and the `transfer_id` of the affected transfer.
2. The Ledger API router detects this pattern (`ADJUSTMENT` + `LOSS_IN_TRANSIT` reason + `transfer_id` present) and routes to the In-Transit Registry's `process_loss()` method.
3. The In-Transit Registry updates the transfer record status to `LOST_IN_TRANSIT`.
4. The system generates a **zero-quantity** `ADJUSTMENT` event at the **source** node with `adjustment_reason: LOSS_IN_TRANSIT`.

> **Why zero-quantity?** The dispatch step already deducted the full `qty_shipped` from the source node's balance. Writing a negative adjustment here would **double-deduct**. The zero-quantity event preserves the audit trail (the loss is recorded as an event) without altering the balance that was already correctly reduced at dispatch.

5. The `qty_shipped - qty_received` remainder is the written-off quantity, tracked at the **transfer registry level**.

> **Accounting Identity:** `qty_shipped = qty_received + qty_lost`. This identity is enforced by the In-Transit Registry record, not by duplicating deductions in the Event Store. A transfer cannot simply vanish.

### Policy

| Policy | Type | Effect |
|---|---|---|
| `policy.transfer.loss_writeoff_requires_approval` | Boolean | If `TRUE`, the write-off command is routed through the Approval Gatekeeper before the ADJUSTMENT is generated. Default: `TRUE`. |

See [Configuration Hierarchy](../architecture/configuration-hierarchy.md).

## Partial Receipt Completion

When a transfer is `PARTIAL` (some goods received, some outstanding), a completion protocol determines what happens to the remainder:

1. **Deadline:** `policy.transfer.partial_receipt_deadline_days` (from Config Hierarchy). Clock starts at `dispatched_at`.
2. **On Deadline Expiry:** The system does **not** silently auto-receive the remainder. Instead:
   - The transfer is flagged for supervisor investigation.
   - A system alert is generated.
   - The supervisor must either: (a) confirm receipt of the remainder, (b) mark as `LOST_IN_TRANSIT`, or (c) extend the deadline.
3. **Invariant:** Partial transfers must **not** be silently auto-closed as `STALE_AUTO_CLOSED`. Auto-close applies only to `OPEN` transfers with zero receipts (full auto-receipt). `PARTIAL` transfers have evidence of actual logistics activity and demand explicit resolution.

## Discrepancy Escalation

Significant discrepancies between `qty_shipped` and `qty_received` are automatically routed through the Approval Gatekeeper:

| Policy | Type | Effect |
|---|---|---|
| `policy.transfer.discrepancy_threshold_pct` | Integer (%) | If `(qty_shipped - qty_received) / qty_shipped > threshold` on receipt, the receipt command is staged for approval. Default: `20%`. |

## Integration Notes

- **Client Role:** The submitting Client must include `transfer_id` so the Registry knows which in-transit record to close.
- **Approval Role:** The Approval Gatekeeper gates loss write-offs and significant discrepancies based on configurable policy.

## Related Docs

- **Event math:** [Event Store](event-store.md)
- **All tables:** [Database Schema](database-schema.md)
- **Policy config:** [Architecture → Configuration Hierarchy](../architecture/configuration-hierarchy.md)
- **Adjustment reasons:** [Event Store → Adjustment Reasons](event-store.md#adjustment-reasons)
