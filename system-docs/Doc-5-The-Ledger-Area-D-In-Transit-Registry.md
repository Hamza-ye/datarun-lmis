# Area D: The In-Transit Registry

Area D is where we solve the "Black Hole" problem in logistics: stock that has left the Warehouse but hasn't yet arrived at the Clinic.

In a basic system, a transfer is just minus here, plus there. In a **battle-tested** system, Area D ensures that stock is accounted for even while it's on a truck. It manages the **state machine** of a movement across time.

---

### 1. The In-Transit Registry Schema

This is the "Work-in-Progress" table. It tracks every open transfer until it is safely closed.

**Table Name:** `ledger_in_transit_registry`
*Purpose: Track stock currently "between" locations.*

| Column | Type | Description |
| --- | --- | --- |
| `transfer_id` | **UUID (PK)** | Unique ID for the movement (linked to the Dispatch event). |
| `source_node_id` | `String` | Where it came from. |
| `dest_node_id` | `String` | Where it is going. |
| `item_id` | `String` | The commodity. |
| `qty_shipped` | `BigInt` | Total sent (Base Units). |
| `qty_received` | `BigInt` | Total acknowledged by destination so far. |
| `status` | `Enum` | `OPEN`, `PARTIAL`, `COMPLETED`, `STALE_AUTO_CLOSED`. |
| `dispatched_at` | `Timestamp` | When Area C recorded the `DEBIT` from source. |
| `auto_close_after` | `Timestamp` | Calculated deadline (from Config Hierarchy). |

---

### 2. The Multi-Step Transfer Flow

Area D orchestrates how Areas B, E, and C interact during a movement.

#### Step 1: The Dispatch (Departure)

1. The Warehouse sends a "Dispatch" command.
2. **Area B/E** approve and verify.
3. **Area C** executes a `DEBIT` from the Warehouse.
4. **Area D** creates a record in `ledger_in_transit_registry` with `status: OPEN`.
* *Note:* The Clinic's balance has **not** changed yet.



#### Step 2: The Receipt (Arrival)

1. The Clinic sends a "Receipt" command, referencing the `transfer_id`.
2. **Area D** validates the quantity:
* If `qty_received == qty_shipped`: **Area C** executes `CREDIT` to Clinic; **Area D** sets status to `COMPLETED`.
* If `qty_received < qty_shipped`: **Area C** executes `CREDIT` for the partial amount; **Area D** sets status to `PARTIAL`.



---

### 3. The "Auto-Confirm" Logic (Closing the Loop)

In many field scenarios, a clinic might forget to "Receive" the stock in the app, even though they put it on the shelf. This leaves the system's data "dirty."

**The Orchestrator Job:**
A background worker (Cron) runs every night and performs the following:

1. **Policy Lookup:** For every `OPEN` record in the registry, it asks the **Policy Resolver**: *"What is the `auto_receive_days` for this destination node?"*
2. **Comparison:** If `Current_Date > dispatched_at + auto_receive_days`:
* It calculates the remaining balance: .
* It generates a **System Event**: `type: CREDIT`, `reason: AUTO_RECEIPT`.
* **Area C** processes this event to update the Clinic's stock.
* **Area D** marks the registry record as `STALE_AUTO_CLOSED`.



---

### 4. Integration with the "Client" and "Approval"

* **Client Role:** The Submitting Client must ensure that a "Receipt" payload includes the `transfer_id` so Area D knows which "In-Transit" record to close.
* **Approval Role:** If a "Receipt" shows a significant **Discrepancy** (e.g., Warehouse sent 100, Clinic received 20), **Area E** should intercept this for investigation before Area C is allowed to reconcile the loss.

---

### 5. Summary of Area D Artifacts

* **State Machine:** Logic to handle the transition from `DISPATCHED` to `RECEIVED`.
* **Discrepancy Handler:** Logic to deal with "Lost in Transit" scenarios (usually triggering an `ADJUSTMENT` event in Area C to account for the missing units).
* **The Registry Table:** The source of truth for "What is currently on the road?"

### Final Ledger Check

We have now covered:

* **Area B:** Idempotency (Duplicates)
* **Area E:** Approval (Gatekeeping)
* **Area C:** Accounting (The Math)
* **Area D:** Orchestration (The Movement)
