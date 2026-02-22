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

#### Area A: Ingestion & Translation Engine (The Adapter)

* **Purpose:** Normalize unpredictable external JSON into strict internal Ledger Commands.
* **Capabilities:** Schema validation; dynamic mapping of JSON paths to internal properties; external-to-internal ID resolution; UOM normalization to Base Units.
* **I/O:** *Reads* raw JSON webhooks/syncs. *Reads* mapping configurations. *Writes* normalized Commands to the Ledger queue.
* **Data-Configurable:** Form-to-Command mapping templates; Payload versioning rules.
* **Boundaries:** *In-Scope:* Structural translation and validation. *Out-of-Scope:* State, balances, business rules, or stock history.

#### Area B: Idempotency & Lifecycle Manager (The Ledger)

* **Purpose:** Guard the ledger against duplicate, out-of-order, or edited submissions.
* **Capabilities:** Duplicate detection via `source_event_id`; version comparison (`version_timestamp`); orchestration of "Reverse & Replace" flows for edited field data; timeline recalculation for back-dated (offline) entries.
* **I/O:** *Reads* incoming Commands. *Reads* previous event metadata. *Writes* verified Events (New, Reversal, or Correction) to the Event Store.
* **Data-Configurable:** Replay policy (e.g., maximum allowable back-date window).
* **Boundaries:** *In-Scope:* State transitions and collision handling. *Out-of-Scope:* Calculating stock totals or enforcing UOMs.

This is the most critical logic to get right. In an append-only ledger, you cannot use SQL `UPDATE` or `DELETE`.

**The Execution Flow for an Edited Form:**

1. **Detection:** The Ledger receives Command V2 with `source_event_id: "ABC"` and `version/version_timestamp: 2`.
2. **Lookup:** It queries the `inventory_events` table and finds `event_id: 101` matches `source_event_id: "ABC"`.
3. **Reversal (The Undo):** The Ledger automatically generates a new event: `type: "REVERSAL", qty: +50, linked_to: 101`. This zeroes out the original mistake while keeping the audit trail intact.
4. **Correction (The Redo):** The Ledger generates another new event: `type: "ISSUE", qty: -40, source_event_id: "ABC", version: 2`.
5. **Projection Update:** The `current_stock_balances` table is recalculated based on these new events.


##### The Shared Kernel (The Common Language, The Ledger)

* **Purpose:** Provide the immutable definitions and registries used by both the Adapter and the Ledger.
* **Artifacts:**
* **Commodity Registry:** Canonical list of items (IDs, Names, Categories).
* **UoM Registry:** Base units and conversion factors (e.g., 1 Box = 100 Tablets).
* **Node Hierarchy:** The source of truth for all Supply Nodes and their types.
* **Responsibility:** Ensures that when the Adapter says `Item_A`, the Ledger knows exactly what that means mathematically.

---

#### Area C: Core Accounting & Projection (The Ledger)

* **Purpose:** The mathematical heart of the system; enforcing stock rules and calculating balances.
* **Capabilities:** Appending atomic events; projecting current balances (Quantity on Hand); projecting batch/expiry statuses; executing the `STOCK_COUNT` absolute reset; enforcing negative inventory policies.
* **I/O:** *Reads* validated Events. *Writes* to the `inventory_events` table. *Writes* (updates) the Read-Optimized `current_stock_balances` table.
* **Data-Configurable:** Negative stock allowance; batch requirement rules; expiry thresholds.
* **Boundaries:** *In-Scope:* Symmetrical accounting and math. *Out-of-Scope:* Interpreting external IDs or handling "In-Transit" delays.

**The Execution Flow for a Stock-Count:**

1. **The Claim:** The nurse submits a physical count: *"I have 100 units on the shelf."*
2. **The System Check:** The Ledger checks the `current_stock_balances` table. It thinks the facility should have **120** units based on historical receipts and issues.
3. **The Variance Calculation:** . In this case, .
4. **The Event:** The Ledger inserts an event: `type: "ADJUSTMENT_VARIANCE", qty: -20, reason: "STOCK_COUNT_RESET"`.
5. **The Result:** The running total is now perfectly synced to 100, and you have a permanent record that 20 units were lost or consumed unrecorded.

---

#### Area D: Orchestration & In-Transit Workflow (The Ledger)
Handling the "Push" logistics requires parking the stock in a virtual space so it doesn't artificially inflate the destination's balance before it physically arrives.

* **Purpose:** Manage multi-step logistics flows across time and space.
* **Capabilities:** Creating `InTransitRecords` for push/pull transfers; listening for receiving events to close open transfers; triggering auto-receive/auto-confirm routines for stale pushes.
* **I/O:** *Reads* Dispatch Events. *Writes* `In-Transit` states. *Writes* Auto-Receipt Events when timers expire.
* **Data-Configurable:** Auto-receive time limits (days); auto-confirm default behaviors.
* **Boundaries:** *In-Scope:* State machines for moving stock. *Out-of-Scope:* Actually adding/subtracting the final balances (Area C does this).

**The Execution Flow for a Two-Step Transfer:**

1. **Dispatch:** MU submits a dispatch form. Ledger creates event: `type: "DEBIT", node: "MU-1", qty: 50`.
2. **Transit Record Creation:** The Orchestrator creates a row in the `in_transit_records` table: `status: "OPEN", from: "MU-1", to: "HF-2", qty: 50, created_at: "2026-02-21"`.
3. **Auto-Receive Cron Job:** A nightly job checks the `in_transit_records` table against the Configuration Hierarchy.
4. **The Policy Check:** It asks the config engine: *"What is the `auto_receive_days` policy for Node HF-2?"* The engine returns `14 days`.
5. **Closure:** If `created_at` is older than 14 days, the Orchestrator generates a Ledger event: `type: "CREDIT", node: "HF-2", qty: 50, reason: "AUTO_RECEIVE"`. It then updates the transit record to `status: "SYSTEM_CLEARED"`.

---

### 3. Responsibility Split: Adapter vs. Ledger

| Responsibility | Adapter Module (Stateless) | Ledger Module (Stateful) |
| --- | --- | --- |
| **Trust Level** | Zero Trust (Sanitizes everything) | Absolute Authority (Source of Truth) |
| **Data Format** | JSON parsing & JSON Path extraction | Strongly typed Internal Commands |
| **UOM** | Converts "Boxes"  "Tablets" using config | Only knows "Tablets" (Base Units) |
| **State** | None. Forgets payloads after translating. | Owns the Event Log and Current Balances. |
| **Edits/Deletes** | Detects `status:deleted` and forwards a command | Executes the Compensating Transaction math |

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

1. **Ingestion:** Adapter normalizes the data.
2. **Idempotency (Area B):** Ledger ensures we haven't seen this `source_event_id` before.
3. **Governance Check (Area E):** * The `ApprovalResolver` checks the hierarchy.
* **If No Approval Needed:** Command proceeds immediately to Area C.
* **If Approval Needed:** Command is written to `pending_approvals` with status `AWAITING`. The Ledger sends a `202 Accepted (Pending Approval)` response to the Adapter.


4. **Action:** A supervisor logs in, reviews the `AWAITING` queue, and clicks **Approve**.
5. **Commitment (Area C):** The Ledger moves the data from the "Staging" area to the "Event Store," and the stock balance finally updates.


### 3. Updated Transaction Lifecycle (The "Staging" Pattern)

With Area E included, the journey of a Command changes from a direct line to a gated workflow.

1. **Ingestion:** Adapter normalizes the data.
2. **Idempotency (Area B):** Ledger ensures we haven't seen this `source_event_id` before.
3. **Governance Check (Area E):** * The `ApprovalResolver` checks the hierarchy.
* **If No Approval Needed:** Command proceeds immediately to Area C.
* **If Approval Needed:** Command is written to `pending_approvals` with status `AWAITING`. The Ledger sends a `202 Accepted (Pending Approval)` response to the Adapter.


4. **Action:** A supervisor logs in, reviews the `AWAITING` queue, and clicks **Approve**.
5. **Commitment (Area C):** The Ledger moves the data from the "Staging" area to the "Event Store," and the stock balance finally updates.

---

### 4. Revised Prioritized Starting Point

The introduction of Approval changes the priority. We cannot build the "Accounting Math" (Area C) without knowing if the data coming into it is "Committed" or just "Staged."

**The New Order:**

1. **Identity Guard (Area B):** Still #1. We must protect against duplicates first.
2. **Staging & Approval (Area E):** Build the "Waiting Room" for commands. This allows you to test the flow without actually affecting stock math yet.
3. **The Event Store & Projection (Area C):** Build the final "Truth" store where approved commands are converted into immutable facts.
4. **Logistics Workflow (Area D):** Layer on the "In-Transit" logic.

