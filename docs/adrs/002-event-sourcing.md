# ADR-002: Event Sourcing for the Accounting Core

## Status
Accepted

## Context
A Ledger is only useful if it is trusted. If the `stock_balances` table simply updates `quantity = 50`, auditors have no way to prove *why* the stock is 50.

## Decision
The Ledger Event Store will use **Event Sourcing**.

- The ultimate source of truth is the `inventory_events` table, which is **append-only**.
- `UPDATE` and `DELETE` SQL commands are strictly forbidden on the Event Store.
- To fix a mistake, a `REVERSAL` event must be appended.

## Consequences

### Positive
- Absolute auditability. We can rebuild the entire state of the system from Day 1 by replaying the events.

### Negative
- Querying the Event Store for current balances is too slow, necessitating CQRS (see [ADR-003](003-cqrs-projections.md)).
