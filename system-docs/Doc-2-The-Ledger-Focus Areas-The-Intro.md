
# Module 2 — The Ledger Focus Area

The Ledger is divided into three distinct sub-modules (Areas B, C, and D) to ensure vertical testability and separation of concerns.

## 1. Area B: Identity & Lifecycle Manager (The Guard)

**Intent:** To ensure that the Ledger remains an immutable "Fact Store" where every entry is unique, traceable, and recoverable. It acts as the gatekeeper before any math happens.

* **Responsibilities:**
* Verifying `source_event_id` to prevent duplicate processing.
* Managing the **Reverse & Replace** logic for edited submissions.
* Sequencing events based on `version_timestamp` rather than arrival time.


* **Required Artifacts:**
* **Idempotency Registry:** A high-speed lookup table of `source_event_id` and their processing status.
* **Event Lifecycle Policy:** Data-driven rules on how long after the "Fact" an event can be edited or reversed (The "Closing the Books" window).

## 2. Area C: Atomic Accounting Engine (The Bookkeeper)

**Intent:** The mathematical core. It performs the "Symmetrical Accounting" and maintains the current state of the world (Stock on Hand).

* **Responsibilities:**
* Appending verified events to the permanent **Event Store**.
* Performing the **Absolute Reset** math for `STOCK_COUNT` commands.
* Maintaining **Materialized Views** (Projections) of current balances for rapid querying.

* **Required Artifacts:**
* **The Event Store:** The append-only table containing every `CREDIT`, `DEBIT`, and `ADJUSTMENT`.
* **Stock Projections:** A read-optimized table storing `node_id | item_id | batch | quantity`.
* **Accounting Schema:** Definitions for how different transaction types impact the ledger.


## 3. Area D: Logistics Orchestrator (The Workflow Engine)

**Intent:** To manage the "Space and Time" gap in logistics, specifically stock that has left one location but not yet arrived at another.

* **Responsibilities:**
* Managing the **In-Transit** lifecycle (Open  Received  Stale).
* Executing **Auto-Confirmation** policies based on time-triggers.
* Linking Dispatch events from a Source to Receipt events at a Destination.


* **Required Artifacts:**
* **In-Transit Registry:** A state-tracking table for pending transfers.
* **Policy Engine:** The resolver that pulls `auto_receive_days` from the Global  Local hierarchy.


---

## 4. Canonical Transaction Types

To maintain industry compatibility (GS1/OpenLMIS standards), the Ledger will only recognize these fixed transaction types. The **Adapter** is responsible for mapping "messy" field names into these "Clean" types.

| Transaction Type | Concept | Stock Effect (Base Units) |
| --- | --- | --- |
| **RECEIPT** | Stock arriving from an external source or higher level. | `(+) Destination` |
| **ISSUE** | Stock leaving to a patient or lower-level facility (Consumption). | `(-) Source` |
| **TRANSFER** | Stock moving between nodes within the system. | `(-) Source`  `(+) In-Transit`  `(+) Destination` |
| **ADJUSTMENT** | Manual correction for damage, expiry, or found stock. | `(+/-) Node` |
| **STOCK_COUNT** | The "Physical Audit" snapshot. | `(Override) Balance` (Calculates variance) |
| **REVERSAL** | The "Undo" part of a compensating transaction. | `(Opposite) of original event` |

---

## 5. Prioritized Starting Point: The Idempotency Guard (Area B)

**Why:** If we build the math (Area C) first without the guard (Area B), we risk corrupting our database with duplicates from the very first test.

**Recommended Implementation Order:**

1. **Identity Guard (Area B):** Build the table that tracks `source_event_id`. This allows you to safely send payloads multiple times without worry.
2. **The Event Store (Area C):** Implement the append-only table and the `CREDIT/DEBIT` logic.
3. **The Projection (Area C):** Create the "Current Balance" view so you can actually see the results of your events.
4. **Logistics Workflow (Area D):** Layer on the "In-Transit" logic once the basic plus/minus math is stable.

---

## 6. Verification & Acceptance Criteria (Ledger Core)

* [ ] **Duplicate Test:** Submitting a command with the same `source_event_id` twice results in a `200 Already Processed` and no second entry in the Event Store.
* [ ] **Symmetry Test:** A `TRANSFER` command correctly decreases the source and places the equivalent quantity into the `In-Transit` registry.
* [ ] **Variance Test:** If the system thinks stock is 50, and a `STOCK_COUNT` of 40 is submitted, an adjustment of `-10` is automatically generated.
* [ ] **Base Unit Integrity:** All internal storage and math must be in integers (Base Units); no decimals allowed in the Ledger math layer.

**Would you like me to now provide the technical Database Schema for "Area B: The Idempotency Guard" and "Area C: The Event Store"?**