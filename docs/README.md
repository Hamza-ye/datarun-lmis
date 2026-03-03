# Datarun Health LMIS — Documentation Index

## How to Use These Docs

Each folder corresponds to a **Bounded Context** (or cross-cutting concern). When working on a specific part of the system, reference **only** the relevant folder to keep AI context windows small.

---

## Quick Reference

| Working On | Load These Docs |
| --- | --- |
| **Adapter mapping/ingestion** | `adapter/` |
| **Ledger accounting/events** | `ledger/` |
| **Registries, nodes, commodities** | `kernel/` |
| **BFF / UI aggregation** | `composition/` |
| **Angular frontend** | `frontend/` |
| **System-wide decisions** | `architecture/` + `adrs/` |

---

## Folder Structure

### [`architecture/`](architecture/) — Cross-Cutting Concerns
- [System Overview](architecture/system-overview.md) — Vision, bounded context map, deployment model
- [Context Map](architecture/context-map.md) — DDD strategic relationships between all BCs
- [Integration Contract — DatarunAPI](architecture/integration-contract-datarunapi.md) — OHS boundary, auth channels, versioning
- [Configuration Hierarchy](architecture/configuration-hierarchy.md) — 4-level policy resolution cascade
- [Transaction Types](architecture/transaction-types.md) — The 6 canonical types and lifecycle
- [Auth & Authorization](architecture/auth-and-authorization.md) — Phased strategy, JWT, scopes, RBAC, ActorContext

### [`adrs/`](adrs/) — Architectural Decision Records
- [ADR-001: Modular Monolith](adrs/001-modular-monolith.md)
- [ADR-002: Event Sourcing](adrs/002-event-sourcing.md)
- [ADR-003: CQRS Projections](adrs/003-cqrs-projections.md)
- [ADR-004: Sync Execution (No Kafka)](adrs/004-sync-execution-no-kafka.md)
- [ADR-005: Async Workers via Lifespan](adrs/005-async-workers-lifespan.md)
- [ADR-006: 3-Layer Adapter Pipeline](adrs/006-three-layer-adapter-pipeline.md)
- [ADR-007: API Composition Strategy](adrs/007-api-composition-strategy.md)
- [ADR-008: Auth Phased Strategy](adrs/008-auth-phased-strategy.md)

### [`adapter/`](adapter/) — Adapter Bounded Context (ACL)
- [Adapter Overview](adapter/adapter-overview.md) — Constitution, 3-layer pipeline, decoupling
- [Mapping DSL Reference](adapter/mapping-dsl-reference.md) — JSON schema spec, operations, dictionaries
- [Database Schema](adapter/database-schema.md) — All adapter tables
- [DLQ and Replay](adapter/dlq-and-replay.md) — Unified inbox, error correction, replay logic
- [Mapping Contract Lifecycle](adapter/mapping-contract-lifecycle.md) — DRAFT→ACTIVE→DEPRECATED
- [Edge Cases](adapter/edge-cases.md) — Failure scenarios and recovery
- [`test-fixtures/`](adapter/test-fixtures/) — Cleaned source-event payloads + mapping contracts

### [`ledger/`](ledger/) — Ledger Bounded Context
- [Ledger Overview](ledger/ledger-overview.md) — Sub-domains, command flow, key ADRs
- [Idempotency Guard](ledger/idempotency-guard.md) — Deduplication and edit detection
- [Approval Gatekeeper](ledger/approval-gatekeeper.md) — Staging and supervisor approval
- [Event Store](ledger/event-store.md) — Append-only events, OCC, stock-take reset
- [In-Transit Registry](ledger/in-transit-registry.md) — Transfer state machine, auto-receipt
- [Database Schema](ledger/database-schema.md) — All ledger tables (index)
- [Edge Cases](ledger/edge-cases.md) — Failure scenarios and recovery

### [`kernel/`](kernel/) — Shared Kernel
- [Kernel Overview](kernel/kernel-overview.md) — Role and design principles
- [Node Registry](kernel/node-registry.md) — Supply node topology with SCD Type 2
- [Commodity Registry](kernel/commodity-registry.md) — Items, base units, immutable multipliers
- [Policy Engine](kernel/policy-engine.md) — Configuration as data, resolution hierarchy
- [Edge Cases](kernel/edge-cases.md) — Topology drift and recovery

### [`composition/`](composition/) — BFF / Composition Layer
- [Composition Overview](composition/composition-overview.md) — BFF rules, fault tolerance, partial response

### [`frontend/`](frontend/) — Frontend Architecture
- [Frontend Architecture](frontend/spa-architecture.md) — Multi-app strategy, SSO, LMIS Angular SPA rules

---

## Deprecated Docs

Old documentation has been moved to [`_deprecated/`](_deprecated/). These are preserved for historical reference only. **Do not use them as authoritative sources.**
