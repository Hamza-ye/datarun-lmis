# Approval Gatekeeper (Area E)

## Purpose

Intercepts high-impact commands and holds them in a "Staged" state until authorized by a designated role. If the Idempotency Guard says "This is new," the Gatekeeper evaluates the Approval Policy.

## Tables

### `ledger_staged_commands` — The Waiting Room

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Internal staging record ID |
| `source_event_id` | String (FK) | Links to the Idempotency Registry |
| `command_type` | String | e.g., `STOCK_COUNT`, `ADJUSTMENT` |
| `payload` | JSONB | Full, normalized command (ready to execute) |
| `stage_reason` | String | Why stopped (e.g., `VAR_THRESHOLD_EXCEEDED`, `MANUAL_TYPE`) |
| `status` | Enum | `AWAITING`, `APPROVED`, `REJECTED`, `EXPIRED` |
| `node_id` | String | Facility or MU the command belongs to |
| `created_at` | Timestamp | Audit timestamp |
| `updated_at` | Timestamp | Last status change |

### `ledger_approval_audit` — Legal Record

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Unique audit ID |
| `staged_command_id` | UUID (FK) | Links to `ledger_staged_commands` |
| `actor_id` | String | Supervisor who took action |
| `action` | Enum | `APPROVE`, `REJECT` |
| `comment` | Text | Justification |
| `occurred_at` | Timestamp | Exact moment of action |

## Execution Flow

1. **Evaluate Policy:** Run the `PolicyResolver` (Global → Local).
   - *Question:* Does an `ADJUSTMENT` of 500 units at Node `MU-1` need approval?
   - *Answer:* Yes.
2. **Stage Command:**
   - Write the normalized command to `ledger_staged_commands`.
   - Update `ledger_idempotency_registry` status to `STAGED`.
   - Return `202 Accepted (Staged for Approval)` to the caller.
3. **Finalize (Post-Approval):**
   - Supervisor clicks "Approve."
   - Ledger pulls the `payload` from `ledger_staged_commands`.
   - Pushes it to the [Event Store](event-store.md).

> **Key Invariant:** The `payload` in the staging table is already normalized and "Ready to Fire." When the supervisor approves, no further translation or lookup is needed — the math just happens.

## Policy Configuration

See [Architecture → Configuration Hierarchy](../architecture/configuration-hierarchy.md) for the full policy resolution chain.

| Policy | Type | Example |
| --- | --- | --- |
| `policy.approval.required_on` | `List[TransactionTypes]` | `[ADJUSTMENT, STOCK_COUNT]` |
| `policy.approval.auto_approve_threshold` | `Integer` | Variance < 10 units → bypass |
| `policy.approval.role_required` | `String` | MU: `SUPERVISOR`, WH: `MANAGER` |
| `policy.approval.bypass_emergency` | `Boolean` | Emergency orders skip queue |

## Related Docs

- **Previous step:** [Idempotency Guard](idempotency-guard.md)
- **Next step:** [Event Store](event-store.md)
- **Auth/RBAC:** [Architecture → Auth & Authorization](../architecture/auth-and-authorization.md)
