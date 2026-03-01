# System Overview — Datarun Health LMIS

## Vision

We are building a **domain-oriented ingestion platform** around a shared Data-Collection backbone. The system translates field observations into canonical artifacts consumed by independent Bounded Contexts (Ledger, Inventory, CaseMgmt, etc.). The translation layer is purposely narrow and auditable; it is realized as an Anti-Corruption Layer (ACL) inside the ingestion context.

## Architecture Pattern

> A Shared Event Backbone + Independent Domain Services

Key patterns in use:
- **Domain-Driven Design (DDD)** and Bounded Contexts
- **Event-Carried State Transfer**
- **Anti-Corruption Layers (ACLs)** for ingestion/translation
- **Backend-for-Frontend (BFF)** for UI composition ([ADR-007](../adrs/007-api-composition-strategy.md))

```
          General Data Collection
                    ↓
         Ingestion / ACL Layer (DSL + Mapper)
                    ↓
   -----------------------------------
   |        |            |           |
 Ledger   CaseMgmt      ...     Other Domains
```

Each domain owns its DB, UI, roles, and invariants. Domains consume events produced by the ingestion/ACL layer.

## Bounded Contexts

| Bounded Context | Codebase Location | Responsibility |
| --- | --- | --- |
| **Adapter** (ACL) | `backend/app/adapter` | Ingestion, structural translation, reliable delivery |
| **Ledger** | `backend/app/ledger` | Inventory accounting, event sourcing, approvals, in-transit |
| **Shared Kernel** | `backend/app/kernel` | Registries (Nodes, Commodities), Policy Engine |
| **Composition** (BFF) | `backend/app/composition` | Cross-BC data aggregation for the UI |
| **Frontend** | `frontend/` | Angular 19+ SPA |

### Deployment Model

**Modular Monolith** ([ADR-001](../adrs/001-modular-monolith.md)): Single FastAPI process, single PostgreSQL database. Bounded Contexts are banned from importing each other's Python classes. The Adapter communicates with the Ledger via HTTP loopback.

## Responsibility Split: Adapter vs. Ledger

| Concern | Adapter (ACL) | Ledger (Stateful) |
| --- | --- | --- |
| **Trust Level** | Zero Trust (sanitizes everything) | Absolute Authority (source of truth) |
| **Data Format** | JSON parsing & JSONPath extraction | Strongly typed Internal Commands |
| **UOM** | Converts to Base Units before submission | Only knows Base Units |
| **State** | Stateless pipeline (buffer and forward) | Owns the Event Log and Balances |
| **Edits/Deletes** | Detects updates & forwards commands | Executes Compensating Transaction math |

## Related Docs

| Topic | Document |
| --- | --- |
| Configuration cascade | [Configuration Hierarchy](configuration-hierarchy.md) |
| Canonical transaction types | [Transaction Types](transaction-types.md) |
| Authentication & RBAC | [Auth & Authorization](auth-and-authorization.md) |
| ADRs | [All ADRs](../adrs/) |
