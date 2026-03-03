# Composition Layer (BFF) — Overview

## Purpose

The Composition Layer (`backend/app/composition`) is the **Backend-for-Frontend** that aggregates data from multiple Bounded Contexts into unified API responses for the UI.

See [ADR-007](../adrs/007-api-composition-strategy.md) for the full architectural decision.

## Rules

1. **No Domain Leakage:** The Composition layer can call domain services, but domain services MUST NEVER call the Composition Layer.
2. **Fault Tolerance:**
   - Every sub-service call has a per-subsystem timeout (e.g., Ledger 500ms, Kernel 300ms).
   - Uses a **Partial Response** pattern: if a sub-service fails, return the rest of the data with a `warnings` indicator.
3. **Context Propagation:** Forward `X-Correlation-ID` and `ActorContext` (Auth) through every call.
4. **Read-Model Threshold:** If >30% of requests require the same multi-context join, or latency targets are missed, move the join to a dedicated Read-Model table populated by domain events.

## Example Use Case

A "Facility Overview" dashboard needs:
- Node details → **Kernel**
- Current stock → **Ledger**
- Recent sync history → **Adapter**

The Composition Layer orchestrates these three calls, merges the responses, and returns a single payload to the frontend.

> [!NOTE]
> The BFF queries **Adapter, Ledger, and Kernel only**. It never queries DatarunAPI directly. DatarunAPI is upstream of the Adapter — the BFF has no relationship with it. See [Context Map](../architecture/context-map.md).

## Required Capabilities

- Clean domain APIs for each Bounded Context
- Shared authentication and context propagation
- Optional gateway or dedicated BFF for aggregation

## Related Docs

- **ADR:** [ADR-007 — API Composition Strategy](../adrs/007-api-composition-strategy.md)
- **Auth context:** [Architecture → Auth & Authorization](../architecture/auth-and-authorization.md) ([ADR-008](../adrs/008-auth-phased-strategy.md))
- **Context Map:** [Architecture → Context Map](../architecture/context-map.md)
