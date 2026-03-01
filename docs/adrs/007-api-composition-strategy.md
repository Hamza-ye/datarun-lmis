# ADR-007: API Composition Strategy (Backend-for-Frontend)

## Status
Proposed

## Context
As we move toward a multi-domain ecosystem (Ledger, CaseMgmt, Inventory), the UI increasingly needs to display data that crosses Bounded Context boundaries. For example:
- A "Facility Overview" dashboard needs Node details (Kernel), current stock (Ledger), and recent sync history (Adapter).

Three primary options exist:
1. **Frontend Composition:** The UI calls 3 separate APIs and joins the data.
2. **Back-to-Back Composition:** One domain calls another to enrich its output.
3. **BFF / Composition Layer:** A dedicated module orchestrates calls to multiple domains.

## Decision
We will use a dedicated **Composition Layer** (`backend/app/composition`).

### Implementation Rules
1. **No Domain Leakage:** The Composition layer can call domain services, but domain services must never call the Composition Layer.
2. **Fault Tolerance:** Every call must have a per-subsystem timeout (e.g., Ledger 500ms, Kernel 300ms). Use a **Partial Response** pattern — if a sub-service fails, return the rest with a `warnings` indicator.
3. **Context Propagation:** Forward `X-Correlation-ID` and `ActorContext` (Auth) through every call.
4. **Read-Model Threshold:** If >30% of requests require the same multi-context join, or latency targets are missed, move the join to a dedicated Read-Model table populated by domain events.

## Consequences

### Positive
- **UI Performance:** Reduced round-trips for the browser.
- **Resilience:** A failure in a "History" sub-service doesn't break the "Current State" dashboard.

### Negative
- **Coupling:** Aggregator depends on the interfaces of multiple domains.
