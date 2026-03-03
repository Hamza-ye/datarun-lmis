# Policy Engine (Configuration as Data)

## Purpose

The Idempotency Guard, Approval Gatekeeper, and In-Transit Registry rely on business rules that change over time. These rules live in database tables, not in Python code.

## Table

**Table:** `kernel_system_policy`

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Row identifier |
| `policy_key` | String | Policy name (e.g., `policy.approval.required_on`, `policy.transfer.auto_receive_days`) |
| `applies_to_node` | String (nullable) | Node scope: specific node UID, node type (e.g., `type:MU`), or `NULL` for global |
| `applies_to_item` | String (nullable) | Item scope: specific `item_id`, category (e.g., `category:DRUGS`), or `NULL` for all |
| `config` | JSONB | Policy configuration blob |
| `created_at` | Timestamp | Creation |
| `updated_at` | Timestamp | Last change |

### Scope Resolution

`NULL` means "unscoped" — the row applies to all entities in that axis.

| `applies_to_node` | Meaning |
|---|---|
| `NULL` | Global (applies to all nodes) |
| `type:MU` | Applies to all nodes of type "Mobile Unit" |
| `WH_KAMPALA` | Applies to a specific node |

| `applies_to_item` | Meaning |
|---|---|
| `NULL` | Applies to all items |
| `category:DRUGS` | Applies to all items in category "DRUGS" |
| `PARAM-01` | Applies to a specific item |

### Example Rows

| policy_key | applies_to_node | applies_to_item | config |
| --- | --- | --- | --- |
| `policy.approval.required_on` | `NULL` | `NULL` | `{"transaction_types": ["ADJUSTMENT"], "threshold_usd": 500}` |
| `policy.transfer.auto_receive_days` | `WH_KAMPALA` | `NULL` | `{"days": 14}` |
| `policy.negative_stock.behavior` | `NULL` | `NULL` | `{"behavior": "BLOCK"}` |
| `policy.negative_stock.behavior` | `type:MU` | `NULL` | `{"behavior": "ALLOW"}` |
| `policy.batch.tracking_required` | `NULL` | `category:DRUGS` | `{"required": true}` |
| `policy.approval.reversal_requires_approval` | `NULL` | `NULL` | `{"mode": "ALWAYS"}` |

## Resolution Hierarchy

When a module queries a policy, the resolver executes a **most-specific → least-specific** fallback chain:

1. **Specific node + specific item** (e.g., `WH_KAMPALA` + `PARAM-01`)
2. **Specific node + any item** (e.g., `WH_KAMPALA` + `NULL`)
3. **Node type + specific item** (e.g., `type:MU` + `PARAM-01`)
4. **Node type + any item** (e.g., `type:MU` + `NULL`)
5. **Any node + commodity category** (e.g., `NULL` + `category:DRUGS`)
6. **Global** (`NULL` + `NULL`)

The first non-null match wins.

> **Design Note:** Transaction-type scoping (e.g., "require approval only for ADJUSTMENT") is expressed inside the `config` JSON blob, not as a separate scope column. This avoids adding a third scope axis to the resolution hierarchy while keeping the schema simple.

## UNIQUE Constraint

```sql
UNIQUE (policy_key, applies_to_node, applies_to_item)
```

This guarantees that only one config blob exists per scope combination. Without it, the resolver could find multiple conflicting rows for the same scope.

> **Note:** `NULL` values in PostgreSQL are not equal to each other in UNIQUE constraints. Use `COALESCE` or partial indexes to enforce uniqueness at the global scope.

## Related Docs

- **Full policy list:** See [Architecture → Configuration Hierarchy](../architecture/configuration-hierarchy.md)
- **Consumers:** [Ledger → Approval Gatekeeper](../ledger/approval-gatekeeper.md), [Ledger → In-Transit Registry](../ledger/in-transit-registry.md), [Ledger → Event Store](../ledger/event-store.md)
