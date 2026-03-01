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
| `status` | Enum | `OPEN`, `PARTIAL`, `COMPLETED`, `STALE_AUTO_CLOSED`, `FAILED_AUTO_CLOSE` |
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

## Integration Notes

- **Client Role:** The submitting Client must include `transfer_id` so the Registry knows which in-transit record to close.
- **Approval Role:** Significant discrepancies (e.g., sent 100, received 20) should trigger the Approval Gatekeeper for investigation.

## Related Docs

- **Event math:** [Event Store](event-store.md)
- **All tables:** [Database Schema](database-schema.md)
- **Policy config:** [Architecture → Configuration Hierarchy](../architecture/configuration-hierarchy.md)
