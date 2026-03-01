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

| Policy Key | Options / Type | Example |
| --- | --- | --- |
| `policy.negative_stock.behavior` | `ALLOW \| WARN \| BLOCK` | Global: `BLOCK`. Mobile Unit: `ALLOW` |
| `policy.transfer.auto_receive_days` | `Integer` | Global: `14`. Specific Clinic: `30` |
| `policy.batch.tracking_required` | `Boolean` | Category 'Drugs': `TRUE`. 'Bednets': `FALSE` |
| `policy.consumption.calculation_method` | `IMPLIED_BY_COUNT \| EXPLICIT_ISSUE` | Per programme need |
| `policy.approval.required_on` | `List[TransactionTypes]` | Global: `[ADJUSTMENT, STOCK_COUNT]` |
| `policy.approval.auto_approve_threshold` | `Integer` | If Variance < 10 units, bypass approval |
| `policy.approval.role_required` | `String` | Mobile Unit: `SUPERVISOR`. Warehouse: `MANAGER` |
| `policy.approval.bypass_emergency` | `Boolean` | Allows emergency orders to skip the queue |

## Related Docs

- **Schema:** See [Kernel → Policy Engine](../kernel/policy-engine.md) for the `kernel_system_policy` table
- **Consumers:** Used by the Ledger's [Idempotency Guard](../ledger/idempotency-guard.md), [Approval Gatekeeper](../ledger/approval-gatekeeper.md), and [In-Transit Registry](../ledger/in-transit-registry.md)
