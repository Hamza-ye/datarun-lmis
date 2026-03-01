# Canonical Transaction Types

## Overview

To maintain industry compatibility (GS1/OpenLMIS standards), the Ledger recognizes only these fixed transaction types. The Adapter's job is to map any external form submission into one of these canonical types.

## Transaction Types

| Transaction Type | Concept | Stock Effect (Base Units) |
| --- | --- | --- |
| **RECEIPT** | Stock arriving from an external source or higher level | `(+) Destination` |
| **ISSUE** | Stock leaving to a patient or lower-level facility (Consumption) | `(-) Source` |
| **TRANSFER** | Stock moving between nodes within the system | `(-) Source` → `(+) In-Transit` → `(+) Destination` |
| **ADJUSTMENT** | Manual correction for damage, expiry, or found stock | `(+/-) Node` |
| **STOCK_COUNT** | The "Physical Audit" snapshot | `(Override) Balance` (Calculates variance) |
| **REVERSAL** | The "Undo" part of a compensating transaction | `(Opposite) of original event` |

## Transaction Lifecycle (The "Staging" Pattern)

With the Approval Gatekeeper included, the journey of a Command follows a gated workflow:

1. **Ingestion:** Client system submits the structured Ledger Command.
2. **Idempotency Guard:** Ledger ensures we haven't seen this `source_event_id` before.
3. **Governance Check:**
   - The `PolicyResolver` checks the configuration hierarchy.
   - **If No Approval Needed:** Command proceeds immediately to the Event Store.
   - **If Approval Needed:** Command is written to `staged_commands` with status `AWAITING`. Returns `202 Accepted (Pending Approval)`.
4. **Action:** A supervisor reviews the `AWAITING` queue and clicks **Approve**.
5. **Commitment:** The Ledger moves the data from staging to the Event Store. The stock balance updates.

## Base Unit Invariant

All ledger mathematics occur exclusively in the **smallest dispensable unit** (e.g., individual tablets, not boxes). This entirely eliminates floating-point rounding errors. UOM conversion is the Adapter's responsibility, never the Ledger's.

## Related Docs

- **Adapter mapping:** See [Adapter → Mapping DSL Reference](../adapter/mapping-dsl-reference.md) for how external forms map to these types
- **Ledger Event Store:** See [Ledger → Event Store](../ledger/event-store.md) for how events are recorded
- **Approval:** See [Ledger → Approval Gatekeeper](../ledger/approval-gatekeeper.md) for staging/approval flow
