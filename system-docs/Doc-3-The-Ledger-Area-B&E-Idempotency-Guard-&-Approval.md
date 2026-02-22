# Area B: The Idempotency Guard

Before the Ledger even looks at a command, it checks this registry. If it has seen the `source_event_id` before, it immediately stops to prevent double-counting.

**Table Name:** `ledger_idempotency_registry`
*Purpose: Ensure every field submission results in exactly one ledger operation.*

| Column | Type | Description |
| --- | --- | --- |
| `source_event_id` | **String (PK)** | The unique ID from the source (e.g., ODK InstanceID). |
| `status` | `Enum` | `PROCESSING`, `COMPLETED`, `STAGED`, `FAILED`. |
| `result_summary` | `JSONB` | Stores a snippet of the result (e.g., "Event #501 Created") to return on duplicate hits. |
| `created_at` | `Timestamp` | When the first attempt happened. |
| `updated_at` | `Timestamp` | For tracking retry attempts. |

> **Architect's Note:** In a high-traffic system, this table should be backed by a unique constraint on `source_event_id`. If a race condition occurs where two identical requests hit at the same millisecond, the database's primary key constraint is your final line of defense.

---

### Area E: The Approval Gatekeeper (The "Staging" Area)

If Area B says "This is new," the Ledger then evaluates the **Approval Policy**. If the policy triggers, the command is "parked" here instead of moving to the Event Store.

**Table Name:** `ledger_staged_commands`
*Purpose: A durable "Waiting Room" for high-impact transactions.*

| Column | Type | Description |
| --- | --- | --- |
| `id` | **UUID (PK)** | Internal reference for this staging record. |
| `source_event_id` | `String` | Foreign Key to the Idempotency Registry. |
| `command_type` | `String` | e.g., `STOCK_COUNT`, `ADJUSTMENT`. |
| `payload` | **JSONB** | The full, normalized command (ready to be executed). |
| `stage_reason` | `String` | Why was it stopped? (e.g., `VAR_THRESHOLD_EXCEEDED`, `MANUAL_TYPE`). |
| `status` | `Enum` | `AWAITING`, `APPROVED`, `REJECTED`, `EXPIRED`. |
| `node_id` | `String` | The facility or MU the command belongs to. |
| `created_at` | `Timestamp` | Audit timestamp. |

**Table Name:** `ledger_approval_audit`
*Purpose: The legal record of "Who said this was okay?"*

| Column | Type | Description |
| --- | --- | --- |
| `id` | **UUID (PK)** | Unique audit ID. |
| `staged_command_id` | `UUID` | Link to the `ledger_staged_commands`. |
| `actor_id` | `String` | The ID of the supervisor who took action. |
| `action` | `Enum` | `APPROVE`, `REJECT`. |
| `comment` | `Text` | Justification for the approval/rejection. |
| `occured_at` | `Timestamp` | Exact moment of action. |

---

### The "Gatekeeper" Logic Flow

1. **Check Identity:** `SELECT * FROM ledger_idempotency_registry WHERE source_event_id = 'ABC'`.
* If exists: Return the `result_summary` (Idempotency success).
* If not: Insert with status `PROCESSING`.


2. **Evaluate Policy:** Run the `PolicyResolver` (Global → Local).
* *Question:* Does an `ADJUSTMENT` of 500 units at Node `MU-1` need approval?
* *Answer:* Yes.


3. **Stage Command:** * Write the normalized command to `ledger_staged_commands`.
* Update `ledger_idempotency_registry` status to `STAGED`.
* Return `202 Accepted (Staged for Approval)` to the calling Client.


4. **Finalize (Post-Approval):** * When the supervisor clicks "Approve," the Ledger pulls the `payload` from `ledger_staged_commands` and pushes it to the **Event Store (Area C)**.

### Summary of Success Criteria

* **No "Double-Dipping":** Even if the internet is flaky and the phone sends the same data 10 times, the `ledger_idempotency_registry` ensures the "Staging" or "Commit" only happens once.
* **Safe Staging:** The `payload` in the staging table is already normalized. It’s "Ready to Fire." This means when the supervisor approves, no further translation or lookup is needed—the math just happens.
