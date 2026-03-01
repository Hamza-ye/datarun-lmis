# ADR-004: Synchronous Ledger Execution vs. Event Broker (Kafka)

## Status
Accepted

## Context
Modern architectures often use Kafka or RabbitMQ to stream events between domains.

## Decision
Inside the Ledger module itself, execution will be **Synchronous**, relying on PostgreSQL ACID transactions.

- We will *not* introduce Kafka/RabbitMQ into the core infrastructure.
- Staging commands (Approval Gatekeeper) and Idempotency Guard will use PostgreSQL tables as their "queues."

## Consequences

### Positive
- Massively simplified infrastructure. A Postgres DB is sufficient to handle hundreds of transactions per second, which far exceeds the current requirements for the LMIS.
- By avoiding distributed message queues, we eliminate the complexity of distributed transactions, two-phase commits, and message broker maintenance.

### Negative
- Horizontal scaling is limited to what PostgreSQL can handle (sufficient for foreseeable load).
