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
| `policy.approval.role_required` | `String` | Resolved at runtime from `lmis_user_permissions.lmis_roles` |
| `policy.approval.bypass_emergency` | `Boolean` | Emergency orders skip queue |
| `policy.approval.reversal_requires_approval` | `ALWAYS \| THRESHOLD \| NEVER` | Controls whether edit-triggered reversals require approval. Default: `ALWAYS`. See [Idempotency Guard](idempotency-guard.md). |
| `policy.approval.expiry_days` | `Integer` | Staged commands older than this are expired by the Lifecycle Worker. Default: `30`. |

## Staged Command Expiry

Staged commands that sit in `AWAITING` indefinitely represent a governance risk: balances, registries, and even the commodity itself may have changed since staging. A **Lifecycle Worker** (orchestrator) manages expiry:

1. The worker is a background cron job (same pattern as the In-Transit auto-close worker).
2. It queries: `WHERE status = 'AWAITING' AND created_at + policy.approval.expiry_days < now()`.
3. For each match, it calls `GatekeeperService.expire(id)` which transitions the status to `EXPIRED`.
4. The Idempotency Registry entry is updated to `FAILED` so the source can re-submit if needed.

> **Invariant:** `EXPIRED → APPROVED` is a forbidden transition. Once expired, a command must be re-submitted from the source.

> **Design Note:** The expiry trigger is an **orchestration concern**, not domain logic. The Approval Gatekeeper defines valid state transitions (`AWAITING → EXPIRED`); the Lifecycle Worker decides *when* to trigger them based on policy. Domain models are passive; orchestrators are active.

## Reversal Approval Policy

When the Idempotency Guard detects an edited form and generates a `REVERSAL` command, whether that reversal requires approval is a **configurable policy**, not a hard rule:

| `policy.approval.reversal_requires_approval` | Behaviour |
|---|---|
| `ALWAYS` (default) | Every reversal is staged for approval regardless of size |
| `THRESHOLD` | Reversal is staged only if it exceeds `auto_approve_threshold` |
| `NEVER` | Reversals are processed immediately (for low-governance environments) |

> The reversal *mechanism* (Reverse & Replace) is an invariant of an append-only ledger. Requiring human approval for every reversal is a governance policy. See [Idempotency Guard](idempotency-guard.md).

## Related Docs

- **Previous step:** [Idempotency Guard](idempotency-guard.md)
- **Next step:** [Event Store](event-store.md)
- **Auth/RBAC:** [Architecture → Auth & Authorization](../architecture/auth-and-authorization.md)
- **Policy config:** [Architecture → Configuration Hierarchy](../architecture/configuration-hierarchy.md)
