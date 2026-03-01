# Idempotency Guard (Area B)

## Purpose

Before the Ledger looks at a command, the Idempotency Guard checks the registry. If it has seen the `source_event_id` before, it immediately stops to prevent double-counting.

## Registry Table

**Table:** `ledger_idempotency_registry`

| Column | Type | Description |
| --- | --- | --- |
| `source_event_id` | String (PK) | Unique ID from the source (e.g., ODK InstanceID) |
| `status` | Enum | `PROCESSING`, `COMPLETED`, `STAGED`, `FAILED` |
| `result_summary` | JSONB | Cached result snippet (returned on duplicate hits) |
| `created_at` | Timestamp | When the first attempt happened |
| `updated_at` | Timestamp | For tracking retry attempts |

> **Invariant:** The `source_event_id` column has a `UNIQUE` constraint. The database's unique index is the final line of defense against concurrent duplicate inserts.

## Execution Flow

1. `SELECT * FROM ledger_idempotency_registry WHERE source_event_id = 'ABC'`
   - **If exists:** Return the cached `result_summary` (idempotent success).
   - **If not:** Insert with status `PROCESSING`.
2. Proceed to the [Approval Gatekeeper](approval-gatekeeper.md).

## Handling Edited Forms (The "Reversal" Flow)

When a field worker edits a previously submitted form:

1. **Detection:** The Guard detects an incoming `source_event_id` with a newer `version_timestamp`.
2. **Generation:** The Guard generates:
   - A `REVERSAL` command for the old state
   - A new command for the new state
3. **Governance:** Regardless of the original command's threshold, the `REVERSAL` is **immediately parked** in `ledger_staged_commands` with reason "Symmetry of Governance: Reversal of modified transaction."
4. **Resolution:** A supervisor must approve the undo before the Event Store reverses the original units.

> **Principle — Symmetry of Governance:** If the original action required approval, reversing it has equally significant impact and must also require approval.

## Related Docs

- **Next step in flow:** [Approval Gatekeeper](approval-gatekeeper.md)
- **Schema:** See [Database Schema](database-schema.md)
