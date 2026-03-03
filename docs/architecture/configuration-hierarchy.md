# Configuration Hierarchy — Policy Resolution Engine

## Overview

Professional supply-chain systems avoid configuration fatigue by resolving policies at runtime using an inheritance chain. The system checks from most-specific to least-specific, using the first non-null value found.

## Resolution Order (Most-Specific → Least-Specific)

1. **Specific Supply Node** (e.g., "District Clinic #402")
2. **Supply Node Type** (e.g., "Mobile Unit" vs. "National Warehouse")
3. **Commodity Category** (e.g., "Clinical Drugs" vs. "Consumables")
4. **Global Default** (system-wide)

## The PolicyResolver Execution Flow

When the system needs to know if a specific clinic can have negative stock:

1. `SELECT value FROM node_overrides WHERE node_id = 'Clinic-A' AND policy = 'ALLOW_NEGATIVE'` → *(Returns NULL)*
2. `SELECT value FROM node_type_policies WHERE type = 'PRIMARY_CLINIC' AND policy = 'ALLOW_NEGATIVE'` → *(Returns NULL)*
3. `SELECT value FROM global_policies WHERE policy = 'ALLOW_NEGATIVE'` → *(Returns FALSE)*

The system respects the global default (`FALSE`) without configuring a thousand individual clinics.

## Data-Configurable Policies

### Inventory Rules

| Policy Key | Options / Type | Example |
| --- | --- | --- |
| `policy.negative_stock.behavior` | `ALLOW` / `WARN` / `BLOCK` | Global: `BLOCK`. Mobile Unit: `ALLOW` |
| `policy.batch.tracking_required` | `Boolean` | Category 'Drugs': `TRUE`. 'Bednets': `FALSE` |
| `policy.consumption.calculation_method` | `IMPLIED_BY_COUNT` / `EXPLICIT_ISSUE` | Per programme need |

### Approval Policies

| Policy Key | Options / Type | Example |
| --- | --- | --- |
| `policy.approval.required_on` | `List[TransactionTypes]` | Global: `[ADJUSTMENT, STOCK_COUNT]` |
| `policy.approval.auto_approve_threshold` | `Integer` | If Variance < 10 units, bypass approval |
| `policy.approval.role_required` | `String` | Resolved at runtime from `lmis_user_permissions.lmis_roles` |
| `policy.approval.bypass_emergency` | `Boolean` | Allows emergency orders to skip the queue |
| `policy.approval.reversal_requires_approval` | `ALWAYS` / `THRESHOLD` / `NEVER` | Default: `ALWAYS`. See [Approval Gatekeeper](../ledger/approval-gatekeeper.md#reversal-approval-policy). |
| `policy.approval.expiry_days` | `Integer` | Default: `30`. Staged commands older than this are expired. |

### Transfer Policies

| Policy Key | Options / Type | Example |
| --- | --- | --- |
| `policy.transfer.auto_receive_days` | `Integer` | Global: `14`. Specific Clinic: `30` |
| `policy.transfer.loss_writeoff_requires_approval` | `Boolean` | Default: `TRUE`. See [In-Transit Registry](../ledger/in-transit-registry.md#loss-write-off-lost_in_transit). |
| `policy.transfer.partial_receipt_deadline_days` | `Integer` | Default: `30`. See [In-Transit Registry](../ledger/in-transit-registry.md#partial-receipt-completion). |
| `policy.transfer.discrepancy_threshold_pct` | `Integer (%)` | Default: `20`. See [In-Transit Registry](../ledger/in-transit-registry.md#discrepancy-escalation). |

### Deferred Policies (Post-MVP)

| Policy Key | Options / Type | Notes |
| --- | --- | --- |
| `policy.expiry.reject_expired_receipts` | `Boolean` | Requires `batch_id` and `expiry_date` columns on `inventory_events`. |

## Related Docs

- **Schema:** See [Kernel → Policy Engine](../kernel/policy-engine.md) for the `kernel_system_policy` table
- **Consumers:** Used by the Ledger's [Idempotency Guard](../ledger/idempotency-guard.md), [Approval Gatekeeper](../ledger/approval-gatekeeper.md), and [In-Transit Registry](../ledger/in-transit-registry.md)
