# Policy Engine (Configuration as Data)

## Purpose

The Idempotency Guard, Approval Gatekeeper, and In-Transit Registry rely on business rules that change over time. These rules live in database tables, not in Python code.

## Table

**Table:** `kernel_system_policy`

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Row identifier |
| `policy_key` | String | Policy name (e.g., `approval_required`, `auto_receive_days`) |
| `applies_to_node` | String | Node scope (`GLOBAL`, specific node UID, or node type) |
| `applies_to_item` | String | Item scope (`ALL` or specific `item_id`) |
| `config` | JSON | Policy configuration blob |
| `created_at` | Timestamp | Creation |
| `updated_at` | Timestamp | Last change |

### Example Rows

| policy_key | applies_to_node | applies_to_item | config |
| --- | --- | --- | --- |
| `approval_required` | `GLOBAL` | `ALL` | `{"transaction_types": ["ADJUSTMENT"], "threshold_usd": 500}` |
| `auto_receive_days` | `WH_KAMPALA` | `ALL` | `{"days": 14}` |
| `negative_stock` | `GLOBAL` | `ALL` | `{"behavior": "BLOCK"}` |

## Resolution Hierarchy

When a module queries a policy, the Kernel executes a fallback chain:

1. Is there a specific policy for this `item_id` at this `node_id`?
2. If no → is there a policy for *any* item at this `node_id`?
3. If no → is there a policy for this `item_id` at the `parent_node_id`?
4. If no → use the `GLOBAL` default.

## Related Docs

- **Full policy list:** See [Architecture → Configuration Hierarchy](../architecture/configuration-hierarchy.md)
- **Consumers:** [Ledger → Approval Gatekeeper](../ledger/approval-gatekeeper.md), [Ledger → In-Transit Registry](../ledger/in-transit-registry.md)
