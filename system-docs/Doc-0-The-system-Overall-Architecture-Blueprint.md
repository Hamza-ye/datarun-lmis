# The system Architecture Blueprint
This is supposed to be a professional, architecture-grade blueprint based on battle-tested public health logistics and Event-Driven Architecture for the system and its parts we intended to implement here.

Here is your end-to-end high level framework, stripped of fluff and focused on execution.

---

### 1. Battle-Tested Strategies for Append-Only Ledgers

Professional supply chain systems rely on specific, proven patterns to maintain data integrity when field data is messy, offline, or mutable.

* **Double-Entry Inventory Accounting:** Every movement involves symmetrical entries. A transfer isn't just `+` and `-`. It is `- Source`, `+ In-Transit`, `- In-Transit`, `+ Destination`. This ensures nothing vanishes into the void.
* **CQRS (Command Query Responsibility Segregation):** The `Write Model` is a strict, append-only log of events (Facts). The `Read Model` (Projections) calculates the "Current Balance" and "In-Transit" states asynchronously.
* **The "Stock-by-Difference" Reconciliation:** When a `STOCK_COUNT` command arrives, the ledger does not calculate a delta; it inserts an absolute `RESET` event for that timestamp, implicitly closing the gap between recorded movements and physical reality.
* **Compensating Transactions (Reverse & Replace):** Mutations (edits/deletes) from the field never trigger an `UPDATE` or `DELETE` in the ledger. They trigger a `-OldValue` (Reversal) linked to the original `source_event_id`, followed by a `+NewValue` (Correction).
* **Canonical Base Units (Smallest Accounting Unit):** All ledger mathematics occur exclusively in the smallest dispensable unit (e.g., individual tablets, not boxes) to entirely eliminate floating-point rounding errors.

---

### 2. Areas of Focus (The Blueprint)

#### Area A: Ingestion (The Client / External Actor)

* **Purpose:** External systems must normalize their domain data into strict internal Ledger Commands before submission.
* **Capabilities:** Schema validation; dynamic mapping of JSON paths to internal properties; external-to-internal ID resolution; UOM normalization to Base Units.
* **I/O:** *Reads* raw field data. *Writes* normalized Commands to the Ledger queue via API.
* **Boundaries:** *In-Scope:* Structural translation and validation (done client-side). *Out-of-Scope:* State, balances, business rules, or stock history.

#### Area B: Idempotency & Lifecycle Manager (The Ledger)

* **Purpose:** Guard the ledger against duplicate, out-of-order, or edited submissions.
* **Capabilities:** Duplicate detection via `source_event_id`; version comparison (`version_timestamp`); orchestration of "Reverse & Replace" flows for edited field data; timeline recalculation for back-dated (offline) entries.
* **I/O:** *Reads* incoming Commands. *Reads* previous event metadata. *Writes* verified Events (New, Reversal, or Correction) to the Event Store.
* **Data-Configurable:** Replay policy (e.g., maximum allowable back-date window).
* **Boundaries:** *In-Scope:* State transitions and collision handling. *Out-of-Scope:* Calculating stock totals or enforcing UOMs.

* **Boundaries:** *In-Scope:* State transitions and collision handling. *Out-of-Scope:* Calculating stock totals or enforcing UOMs.

*(For detailed execution flow on Reversals and Edits, see [**Doc-3: Area B & E**](Doc-3-The-Ledger-Area-B&E-Idempotency-Guard-&-Approval.md))*


##### The Shared Kernel (The Common Language, The Ledger)

* **Purpose:** Provide the immutable definitions and registries used by the Ledger.
* **Artifacts:**
* **Commodity Registry:** Canonical list of items (IDs, Names, Categories).
* **UoM Registry:** Base units and conversion factors (e.g., 1 Box = 100 Tablets).
* **Node Hierarchy:** The source of truth for all Supply Nodes and their types.
* **Responsibility:** Ensures that when a Client Command specifies `Item_A`, the Ledger knows exactly what that means mathematically.

---

#### Area C: Core Accounting & Projection (The Ledger)

* **Purpose:** The mathematical heart of the system; enforcing stock rules and calculating balances.
* **Capabilities:** Appending atomic events; projecting current balances (Quantity on Hand); projecting batch/expiry statuses; executing the `STOCK_COUNT` absolute reset; enforcing negative inventory policies.
* **I/O:** *Reads* validated Events. *Writes* to the `inventory_events` table. *Writes* (updates) the Read-Optimized `current_stock_balances` table.
* **Data-Configurable:** Negative stock allowance; batch requirement rules; expiry thresholds.
* **Boundaries:** *In-Scope:* Symmetrical accounting and math. *Out-of-Scope:* Interpreting external IDs or handling "In-Transit" delays.

*(For detailed execution flow on the Absolute Reset math for Stock Counts and Concurrency, see [**Doc-4: Area C**](Doc-4-The-Ledger-Area-C-Immutable-Event-Store.md))*

---

#### Area D: Orchestration & In-Transit Workflow (The Ledger)
Handling the "Push" logistics requires parking the stock in a virtual space so it doesn't artificially inflate the destination's balance before it physically arrives.

* **Purpose:** Manage multi-step logistics flows across time and space.
* **Capabilities:** Creating `InTransitRecords` for push/pull transfers; listening for receiving events to close open transfers; triggering auto-receive/auto-confirm routines for stale pushes.
* **I/O:** *Reads* Dispatch Events. *Writes* `In-Transit` states. *Writes* Auto-Receipt Events when timers expire.
* **Data-Configurable:** Auto-receive time limits (days); auto-confirm default behaviors.
* **Boundaries:** *In-Scope:* State machines for moving stock. *Out-of-Scope:* Actually adding/subtracting the final balances (Area C does this).

*(For detailed execution flow on Orchestration and Auto-Receipt Cron Jobs, see [**Doc-5: Area D**](Doc-5-The-Ledger-Area-D-In-Transit-Registry.md))*

---

### 3. Responsibility Split: Client vs. Ledger

| Responsibility | Client App / Submitting Actor | Ledger Module (Stateful) |
| --- | --- | --- |
| **Trust Level** | Zero Trust (Sanitizes everything) | Absolute Authority (Source of Truth) |
| **Data Format** | JSON parsing & JSON Path extraction | Strongly typed Internal Commands |
| **UOM** | Converts to Base Units before submission | Only knows "Tablets" (Base Units) |
| **State** | None. Should just buffer and forward. | Owns the Event Log and Current Balances. |
| **Edits/Deletes** | Detects updates and forwards a command | Executes the Compensating Transaction math |

---

### 4. Configuration Hierarchy (Global  Local)

Professional systems avoid configuration fatigue by resolving policies at runtime using an inheritance chain. The system checks Level 4. If null, it checks Level 3, and so on.

1. **Global Default** (e.g., System-wide)
2. **Commodity Category** (e.g., "Clinical Drugs" vs. "Consumables")
3. **Supply Node Type** (e.g., "Mobile Unit" vs. "National Warehouse")
4. **Specific Supply Node** (e.g., "District Clinic #402")


To avoid "Configuration Fatigue," you do not store configs directly on the Node table unless it is an exception. You build a `PolicyResolver` service.

**The Execution Flow for Resolving a Policy:**
When the system needs to know if a specific clinic can have negative stock, the Resolver checks in this exact order:

1. `SELECT value FROM node_overrides WHERE node_id = 'Clinic-A' AND policy = 'ALLOW_NEGATIVE'` -> *(Returns NULL)*
2. `SELECT value FROM node_type_policies WHERE type = 'PRIMARY_CLINIC' AND policy = 'ALLOW_NEGATIVE'` -> *(Returns NULL)*
3. `SELECT value FROM global_policies WHERE policy = 'ALLOW_NEGATIVE'` -> *(Returns FALSE)*

The system respects the global default (`FALSE`) without needing to configure a thousand individual clinics.

**Data-Configurable Policies:**

* `policy.negative_stock.behavior`: `[ALLOW | WARN | BLOCK]` *(Global: BLOCK. Mobile Unit: ALLOW)*
* `policy.transfer.auto_receive_days`: `[Integer]` *(Global: 14. Specific Clinic: 30)*
* `policy.batch.tracking_required`: `[Boolean]` *(Category 'Drugs': TRUE. Category 'Bednets': FALSE)*
* `policy.consumption.calculation_method`: `[IMPLIED_BY_COUNT | EXPLICIT_ISSUE]`


---

## NEW LATE ADDED focus area, the approval Area:

#### Area E: Approval & Governance Flow (The Ledger)

* **Purpose:** To intercept high-impact commands and hold them in a "Staged" state until authorized by a designated role.
* **Capabilities:** * Rule-based interception (e.g., intercept all `ADJUSTMENT` types or any `TRANSFER` >  value).
* Tracking approval signatures (who, when, comments).
* Managing the transition from `STAGED` to `COMMITTED` (to Area C) or `REJECTED`.


* **I/O:** * *Reads* Verified Commands from Area B.
* *Writes* to `pending_approvals` table.
* *Writes* (releases) to Area C once approved.


* **Data-Configurable:** Approval thresholds; required roles per node type; bypass-flags for certain nodes (e.g., "MUs don't need approval for Receipts").
* **Boundaries:** * *In-Scope:* Workflow state and authorization checks.
* *Out-of-Scope:* Calculating stock balances or handling UoM.


**configuration updates:**

Approval is almost never "one size fits all." It is highly dependent on the **Node Type** and the **Volume** of the transaction.

| Policy Name | Options / Type | Example Behavior |
| --- | --- | --- |
| `policy.approval.required_on` | `List[TransactionTypes]` | Global: `[ADJUSTMENT, STOCK_COUNT]`. |
| `policy.approval.auto_approve_threshold` | `Integer` | If Variance < 10 units, bypass approval. |
| `policy.approval.role_required` | `String` | Mobile Unit: `SUPERVISOR`. Warehouse: `MANAGER`. |
| `policy.approval.bypass_emergency` | `Boolean` | Allows "Emergency Orders" to skip the queue during crises. |


### 3. Updated Transaction Lifecycle (The "Staging" Pattern)

With Area E included, the journey of a Command changes from a direct line to a gated workflow.

1. **Ingestion:** Client System submits the structured Ledger Command.
2. **Idempotency (Area B):** Ledger ensures we haven't seen this `source_event_id` before.
3. **Governance Check (Area E):** * The `ApprovalResolver` checks the hierarchy.
* **If No Approval Needed:** Command proceeds immediately to Area C.
* **If Approval Needed:** Command is written to `pending_approvals` with status `AWAITING`. The Ledger sends a `202 Accepted (Pending Approval)` response to the Client.


4. **Action:** A supervisor logs in, reviews the `AWAITING` queue, and clicks **Approve**.
5. **Commitment (Area C):** The Ledger moves the data from the "Staging" area to the "Event Store," and the stock balance finally updates.



---

### 4. Canonical Transaction Types

To maintain industry compatibility (GS1/OpenLMIS standards), the Ledger will only recognize these fixed transaction types.

| Transaction Type | Concept | Stock Effect (Base Units) |
| --- | --- | --- |
| **RECEIPT** | Stock arriving from an external source or higher level. | `(+) Destination` |
| **ISSUE** | Stock leaving to a patient or lower-level facility (Consumption). | `(-) Source` |
| **TRANSFER** | Stock moving between nodes within the system. | `(-) Source`  `(+) In-Transit`  `(+) Destination` |
| **ADJUSTMENT** | Manual correction for damage, expiry, or found stock. | `(+/-) Node` |
| **STOCK_COUNT** | The "Physical Audit" snapshot. | `(Override) Balance` (Calculates variance) |
| **REVERSAL** | The "Undo" part of a compensating transaction. | `(Opposite) of original event` |

---

### 5. Revised Prioritized Starting Point

We cannot build the "Accounting Math" (Area C) without knowing if the data coming into it is "Committed" or just "Staged," nor can we test without duplicating records. 

**Recommended Implementation Order:**

1. **Identity Guard (Area B):** Build the table that tracks `source_event_id`. This protects against duplicates from the first test.
2. **Staging & Approval (Area E):** Build the "Waiting Room" for commands to test flow without affecting stock.
3. **The Event Store & Projection (Area C):** Implement the append-only table, `CREDIT/DEBIT` logic, and "Current Balance" view.
4. **Logistics Workflow (Area D):** Layer on the "In-Transit" logic once the basic plus/minus math is stable.

