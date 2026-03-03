# Composition Layer (BFF) — Overview

## Purpose

The Composition Layer (`backend/app/composition`) provides **multi-BC read aggregation** — endpoints that combine data from multiple Bounded Contexts into unified API responses for the UI.

See [ADR-007](../adrs/007-api-composition-strategy.md) for the full architectural decision.

## Scope: What the BFF Does (and Doesn't)

| ✅ BFF Does | ❌ BFF Does NOT |
| --- | --- |
| Aggregate reads from Adapter + Ledger + Kernel | Proxy single-BC reads or writes |
| Apply per-subsystem timeouts and partial responses | Execute domain logic |
| Define view-optimized response shapes | Handle auth, correlation IDs, or error formatting (that's middleware) |

> [!IMPORTANT]
> **Routing rule for the SPA:**
> - **Multi-BC reads** (e.g., Facility Overview dashboard) → call BFF composition endpoints
> - **Single-BC reads** (e.g., stock balances) → call the Ledger's own HTTP API directly
> - **Writes** (e.g., approve a staged command) → call the domain BC's own HTTP API directly
>
> The BFF is not a gateway or proxy. It exists solely for cross-BC data composition.

## Rules

1. **No Domain Leakage:** The Composition layer can call domain services, but domain services MUST NEVER call the Composition Layer.
2. **Fault Tolerance:**
   - Every sub-service call has a per-subsystem timeout (e.g., Ledger 500ms, Kernel 300ms).
   - Uses a **Partial Response** pattern: if a sub-service fails, return the rest of the data with a `warnings` indicator.
3. **Read-Model Threshold:** If >30% of requests require the same multi-context join, or latency targets are missed, move the join to a dedicated Read-Model table populated by domain events.

## Cross-Cutting Concerns ≠ BFF

Auth validation, `ActorContext` enrichment, `X-Correlation-ID` injection, and error formatting are **FastAPI middleware** — they apply to all routes (BFF routes, Ledger routes, Adapter routes) identically. They are not BFF responsibilities.

```
All HTTP requests → FastAPI Middleware (JWT validation, ActorContext, Correlation ID)
                       ↓
    Composition routes → Multi-BC aggregation
    Ledger routes     → Direct domain operations
    Adapter routes    → Direct domain operations
```

## Example Use Case

A "Facility Overview" dashboard needs:
- Node details → **Kernel**
- Current stock → **Ledger**
- Recent sync history → **Adapter**

The Composition Layer orchestrates these three calls, merges the responses, and returns a single payload to the frontend.

> [!NOTE]
> The BFF queries **Adapter, Ledger, and Kernel only**. It never queries DatarunAPI directly. DatarunAPI is upstream of the Adapter — the BFF has no relationship with it. See [Context Map](../architecture/context-map.md).

## Related Docs

- **ADR:** [ADR-007 — API Composition Strategy](../adrs/007-api-composition-strategy.md)
- **Auth context:** [Architecture → Auth & Authorization](../architecture/auth-and-authorization.md) ([ADR-008](../adrs/008-auth-phased-strategy.md))
- **Context Map:** [Architecture → Context Map](../architecture/context-map.md)
