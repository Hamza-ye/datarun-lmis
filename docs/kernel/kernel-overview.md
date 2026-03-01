# Shared Kernel — Overview

## Role in the Architecture

The Shared Kernel is the **central nervous system** of the Modular Monolith. It provides the immutable definitions and registries used by the Ledger's sub-domains (Idempotency Guard, Event Store, In-Transit Registry, Approval Gatekeeper).

Because the Ledger relies on strict mathematical rules, the definitions it uses must be **unambiguous and historically accurate**.

## Components

| Component | Purpose | Document |
| --- | --- | --- |
| **Node Registry** | Supply Node topology with temporal accuracy (SCD Type 2) | [node-registry.md](node-registry.md) |
| **Commodity Registry** | Canonical items, base units, immutable multipliers | [commodity-registry.md](commodity-registry.md) |
| **Policy Engine** | Configuration-as-data, hierarchical policy resolution | [policy-engine.md](policy-engine.md) |

## Design Principles

1. **Temporal Accuracy:** Historical configuration changes must never corrupt past data (SCD Type 2).
2. **Immutability of Base Units:** If packaging changes, create a new ID — never update the multiplier.
3. **Configuration as Data:** Business rules live in DB tables, not in Python code.

## Related Docs

- **Edge cases:** [Kernel Edge Cases](edge-cases.md)
- **Policy consumers:** [Ledger docs](../ledger/)
