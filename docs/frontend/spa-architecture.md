# Frontend Architecture

## Overview

The frontend is built as **multiple standalone applications**, one per Bounded Context that requires a UI. All apps share a single sign-on (SSO) via DatarunAPI's JWKS endpoint.

> [!IMPORTANT]
> Each frontend app is an independent codebase that talks exclusively to its own BC's API. No frontend app may call another BC's API directly.

---

## 1. Multi-App Strategy

| App | Purpose | API Target | Status |
| --- | --- | --- | --- |
| **LMIS SPA** | Ledger dashboards, adapter monitoring, approvals | LMIS BFF (`/api/composition/*`) | Active development |
| **DatarunAPI Admin** | Template editor, activity config, user management, assignments | DatarunAPI REST API | Future (DatarunAPI currently has no web frontend) |
| **Future BC UIs** | CaseMgmt, Analytics, etc. | Each BC's own API | Future |

### Why Multiple Apps (Not One Big SPA)

1. **DDD boundary enforcement.** DatarunAPI admin configuring templates is a different BC from LMIS supervisors approving stock transactions. Mixing them in one codebase creates import-path entanglement.
2. **Independent evolution.** DatarunAPI admin might be 3 pages. LMIS SPA might be 30. Different velocities, different teams eventually.
3. **Tech flexibility.** DatarunAPI admin could be React, Vue, or even server-rendered. LMIS SPA is Angular 19+. SSO makes tech choice irrelevant across apps.

### SSO: How Users Move Between Apps

```
User authenticates once → DatarunAPI issues RS256 JWT
    ↓
JWT stored in browser (httpOnly cookie or localStorage)
    ↓
LMIS SPA: validates JWT via JWKS → builds ActorContext from lmis_user_permissions
DatarunAPI Admin: validates JWT via JWKS → grants access based on DatarunAPI roles
Future BC UI: validates JWT via JWKS → builds its own authorization context
```

Users move between apps via cross-linking (sidebar link opens the other app). They're already authenticated — no re-login needed.

### Future: Portal Shell (When Needed)

When there are 3+ frontends and the cross-linking UX becomes insufficient, add a thin shell:
- Module Federation (Webpack 5) or Native Federation (Angular 19)
- Shared nav bar + auth context
- Each app loaded as a remote module

**Do not build this until cross-linking is insufficient.** It adds significant build complexity.

---

## 2. LMIS SPA — Angular 19+ Architecture

The LMIS SPA is the primary frontend for the LMIS platform. It follows strict architectural rules.

### Directory Structure (Mirrors Backend Bounded Contexts)

| Directory | Role | Contents |
| --- | --- | --- |
| `@core/` | The Nervous System | Singleton services, HTTP Interceptors (Auth, Error), Router Guards |
| `@shared/` | The Common Toolbox | Dumb UI components, Reusable Directives, UI Pipes |
| `@features/` | Bounded Contexts | Isolated domain modules (`adapter`, `ledger`, `kernel`) |

**Isolation Rule:** A component inside `features/adapter` can NEVER import from `features/ledger`. They communicate only through routing or backend state changes.

### Container vs. Presenter (Smart vs. Dumb)

| Type | Responsibility | HTTP Calls |
| --- | --- | --- |
| **Smart Containers** (Pages/Views) | Inject Services, fetch data, manage state (Signals). Pass data down via `@Input()`. Handle actions from `@Output()`. | YES |
| **Dumb Presenters** (UI Components) | Pure HTML/CSS rendering. Highly reusable. Easily unit tested. | **ZERO** |

### State Management: Native Signals

Uses modern **Angular 19+ Signals** (`signal`, `computed`, `effect`). No NgRx or Redux boilerplate.

- Component state: localized within Smart Containers using `signal()`.
- Global state: in `@core` or `@shared` Singleton Services exposing `computed()` signals.

### Shared Kernel Rule (Performance)

The UI must **never** perform an HTTP request per row to resolve a UUID to a name.

- All UUID resolution via cached `@shared` resolver pipes (e.g., `{{ node_id | resolveNodeName }}`).
- Pipes rely on a `TopologyService` that fetches `/api/kernel/nodes` once on bootstrap (or lazy-loads and caches).

### TypeScript Strictness & OpenAPI Contract

- Every API request/response must be typed using DTOs matching `/openapi/openapi.yaml`.
- The `any` keyword is **strictly forbidden** in service and component definitions.

### Authentication in the SPA

```
1. SPA redirects to DatarunAPI login (or shows a login form that POSTs to DatarunAPI)
2. DatarunAPI returns RS256 JWT
3. SPA stores JWT and includes it in Authorization header for all BFF calls
4. BFF validates JWT via JWKS → enriches with lmis_user_permissions → ActorContext
```

The SPA never validates the JWT itself — that's the backend's job. The SPA only stores and forwards it.

### Development Strategy: Vertical Slivers

Build in isolated, vertical slivers:
- Build the Adapter DLQ view → test → commit.
- Build the Gatekeeper Inbox → test → commit.

This preserves the ability to revert changes without destroying adjacent domains.

---

## Related Docs

- **Auth:** [Auth & Authorization](../architecture/auth-and-authorization.md), [ADR-008](../adrs/008-auth-phased-strategy.md)
- **Backend APIs:** [adapter/](../adapter/), [ledger/](../ledger/), [kernel/](../kernel/)
- **Composition endpoints:** [Composition Overview](../composition/composition-overview.md)
- **Context Map:** [Architecture → Context Map](../architecture/context-map.md)
