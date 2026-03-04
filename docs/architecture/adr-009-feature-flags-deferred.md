# ADR-009: Feature Flags — Deferred

**Status:** Accepted  
**Date:** 2026-03-04  
**Context:** Pre-production, single developer + single deployment

## Decision

Feature flags are **deferred** to a future phase. They are not needed at this stage because:

1. **No production traffic** — all deployments are dev/staging
2. **Single deployment target** — no need for per-environment toggles
3. **Single developer** — no trunk-based development requiring feature isolation

## Future Injection Strategy

When introduced, feature flags will be injected as **cross-cutting middleware**, not embedded in domain logic:

| Scope | Injection Point | Example |
|-------|----------------|---------|
| Module toggle | FastAPI router-level dependency | `Depends(require_feature("adapter_v2"))` |
| Worker toggle | Lifespan startup guard | Skip `create_task()` if flag is off |
| Per-tenant | ActorContext enrichment | Attach flags from DB to actor context |

## Constraints

- Feature flags must **never** leak into domain services (PolicyResolver, EventStoreService, etc.)
- Flag evaluation must be **synchronous** (no async DB call per request)
- Flag storage should use `kernel_system_policy` table with `policy_key = 'feature_flag.*'`

## Consequences

- No feature flag infrastructure to maintain during rapid iteration
- Future adoption is straightforward via the injection points above
- ADR should be revisited when the system moves to multi-tenant or production deployment
