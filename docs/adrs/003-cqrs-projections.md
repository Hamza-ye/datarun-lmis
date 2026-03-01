# ADR-003: Command Query Responsibility Segregation (CQRS) for Balances

## Status
Accepted

## Context
Event Sourcing ([ADR-002](002-event-sourcing.md)) makes writing "Facts" incredibly safe, but makes reading "Current Stock" incredibly slow.

## Decision
We will separate the Write Model from the Read Model (CQRS).

- **Write Model:** The `inventory_events` table.
- **Read Model (Projections):** The `stock_balances` table. Whenever an event is written, the system synchronously updates the read model.
- To prevent race conditions during the Projection update, we mandate **Optimistic Concurrency Control** (OCC) using a `version` integer on the projection row.

## Consequences

### Positive
- Fetching stock for a dashboard is an instant `O(1)` index lookup.

### Negative
- Writing a transaction requires slightly more database coordination (updating the event and the projection in a single atomic DB transaction).
