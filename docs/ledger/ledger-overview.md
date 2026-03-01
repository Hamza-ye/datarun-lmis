# Ledger — Overview

## Role in the Architecture

The Ledger is the **stateful accounting core** of the system. It owns the Event Log, enforces stock rules, and calculates balances. It is the **absolute source of truth** for inventory.

## Sub-Domains (formerly "Areas")

The Ledger is internally organized into four sub-domains, each responsible for a distinct part of the inventory lifecycle:

| Sub-Domain | Old Name | Responsibility | Document |
| --- | --- | --- | --- |
| **Idempotency Guard** | Area B | Deduplication, version detection, reversal generation | [idempotency-guard.md](idempotency-guard.md) |
| **Approval Gatekeeper** | Area E | Staging high-impact commands, supervisor approval | [approval-gatekeeper.md](approval-gatekeeper.md) |
| **Event Store** | Area C | Append-only event log, stock projections, OCC | [event-store.md](event-store.md) |
| **In-Transit Registry** | Area D | Transfer state machine, auto-receipt, discrepancies | [in-transit-registry.md](in-transit-registry.md) |

## Key Architectural Decisions

- **Event Sourcing** ([ADR-002](../adrs/002-event-sourcing.md)): The event log is append-only. No UPDATE/DELETE.
- **CQRS** ([ADR-003](../adrs/003-cqrs-projections.md)): Separate write model (events) from read model (balances).
- **Synchronous Execution** ([ADR-004](../adrs/004-sync-execution-no-kafka.md)): PostgreSQL ACID transactions, no Kafka.
- **Base Units Only**: All math uses the smallest dispensable unit (e.g., tablets). No boxes.

## Command Flow

```
Adapter POST → Idempotency Guard → Approval Gatekeeper → Event Store → Stock Projection
                                                              ↓
                                                     In-Transit Registry (for TRANSFERs)
```

1. **Idempotency Guard** checks `source_event_id` for duplicates and detects edits.
2. **Approval Gatekeeper** evaluates if the command needs supervisor sign-off.
3. **Event Store** appends the immutable event and updates the balance projection atomically.
4. **In-Transit Registry** manages the multi-step transfer state machine (for TRANSFER types).

## Related Docs

| Topic | Document |
| --- | --- |
| Database tables | [Database Schema](database-schema.md) |
| Edge cases | [Ledger Edge Cases](edge-cases.md) |
| Transaction types | [Architecture → Transaction Types](../architecture/transaction-types.md) |
| Policy cascade | [Architecture → Configuration Hierarchy](../architecture/configuration-hierarchy.md) |
