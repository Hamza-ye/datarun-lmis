# DatarunAPI Web Frontend — Architecture Overview

> **Status:** Source of Truth  
> **Last updated:** 2026-03-05  
> **Audience:** Frontend developer building DatarunAPI's web application

---

## 1. What This Frontend Is

The DatarunAPI Web Frontend is the web-based UI for the DatarunAPI data collection platform. It provides administrative configuration, web-based data capture, and submission review.

### What It Does

| Module | Purpose |
|---|---|
| **Admin** | Template design, user management, team/assignment configuration, activity management |
| **Data Capture** | Render dynamic forms from V2 template trees, collect data into normalized V2 submissions |
| **Review** | Browse/search submissions, pivot/analytics views |

### What It Does NOT Do

- **No Ledger views** — inventory accounting belongs to the LMIS SPA
- **No Adapter monitoring** — ingestion pipeline belongs to the LMIS SPA
- **No cross-BC composition** — this frontend talks only to DatarunAPI's own API
- **No LMIS domain vocabulary** — this app knows "templates", "submissions", "assignments". It does not know "stock", "commodity", or "ledger"

---

## 2. Architectural Position

```
DatarunAPI Web Frontend (this app)
        │
        │  Consumes V2 REST API exclusively
        ▼
DatarunAPI Backend (Java · Spring Boot)
    │           │
    │ V1 REST   │ V2 REST
    ▼           ▼
Mobile App   This Frontend
(Flutter)   (Angular)
```

**Key relationships:**

| Relationship | Detail |
|---|---|
| **To DatarunAPI Backend** | V2 REST API consumer. All reads and writes go through `/api/v2/*` endpoints. |
| **To LMIS SPA** | None at code level. Shared SSO via DatarunAPI's JWKS endpoint. Users can cross-link between apps. |
| **To LMIS Platform** | None. This frontend has no relationship to the LMIS BFF, Ledger, Adapter, or Kernel. |
| **Authentication** | SSO via DatarunAPI's own JWT (RS256 + JWKS). See [Auth & Authorization](../../architecture/auth-and-authorization.md). |

---

## 3. Tech Stack

| Concern | Choice | Rationale |
|---|---|---|
| **Framework** | Angular 19+ | Known to the team. DI enforces service layering. Reactive Forms map directly to V2 state model. |
| **State Management** | Angular Signals | Native, lightweight. No NgRx/Redux needed at this scale. |
| **Form Engine** | Headless (custom) | See [Form Engine Contract](form-engine.md). Framework-agnostic TypeScript core. |
| **HTTP** | Angular HttpClient | Standard. Typed DTOs from OpenAPI spec. |
| **Styling** | Component-scoped CSS | Avoid global utility frameworks. Each component owns its styles. |

---

## 4. Layer Structure (Clean Architecture)

Each module (Admin, Data Capture, Review) follows the same four layers. Imports flow **downward only**.

```
┌─────────────────────────────────────────────────┐
│  Presentation Layer                              │
│    Smart containers (pages) + Dumb presenters    │
│    Angular components, routing, templates        │
│    ─ Depends on: Application Layer               │
├─────────────────────────────────────────────────┤
│  Application Layer                               │
│    Use-case orchestration, component state        │
│    Angular services using Signals                │
│    ─ Depends on: Domain Layer                    │
├─────────────────────────────────────────────────┤
│  Domain Layer                                    │
│    Contracts: V2 submission shape, tree nodes    │
│    Value objects, interfaces, rule types         │
│    Pure TypeScript — no Angular imports          │
│    ─ Depends on: nothing                         │
├─────────────────────────────────────────────────┤
│  Infrastructure Layer                            │
│    V2 REST client (HttpClient wrappers)          │
│    Future: IndexedDB for offline persistence     │
│    ─ Depends on: Domain Layer (implements ports) │
└─────────────────────────────────────────────────┘
```

### Folder Layout

```
src/app/
├── core/                          ← Singleton services, guards, interceptors
│   ├── auth/                      ← JWT handling, auth guard
│   ├── http/                      ← Error interceptor, base API client
│   └── layout/                    ← App shell, nav, sidebar
│
├── shared/                        ← Reusable dumb components, pipes, directives
│   ├── components/                ← Generic UI (buttons, modals, tables)
│   └── pipes/                     ← Formatting (dates, labels, etc.)
│
├── domain/                        ← Pure TypeScript contracts (NO Angular)
│   ├── submission/                ← V2Submission, Values, Collections types
│   ├── template-tree/             ← TreeNode, NodeType, Binding types
│   └── rule-engine/               ← Rule, Namespace resolver interfaces
│
├── features/
│   ├── admin/                     ← Template designer, user mgmt, assignments
│   │   ├── pages/                 ← Smart containers
│   │   ├── components/            ← Feature-specific dumb components
│   │   └── services/              ← Feature-specific application services
│   │
│   ├── data-capture/              ← Form renderer (uses Form Engine)
│   │   ├── pages/                 ← Smart container: FormFillPage
│   │   ├── components/            ← Field renderers by type
│   │   ├── engine/                ← Headless Form Engine (see form-engine.md)
│   │   └── services/              ← SubmissionService (online POST, future offline queue)
│   │
│   └── review/                    ← Submission browser, pivot views
│       ├── pages/
│       ├── components/
│       └── services/
│
└── infrastructure/
    ├── api/                       ← V2 REST client implementations
    └── persistence/               ← Future: IndexedDB adapters
```

### Isolation Rules

1. **`features/admin/` must NEVER import from `features/data-capture/`** — they communicate only through routing or shared domain types.
2. **`domain/` must NEVER import Angular** — it's pure TypeScript, testable without a framework.
3. **`features/*` must NEVER import from `infrastructure/` directly** — they consume domain interfaces. Infrastructure provides implementations via Angular DI.
4. **`shared/` components are dumb** — zero HTTP calls, zero service injection, zero state. `@Input()` in, `@Output()` out.

---

## 5. Smart Container vs. Dumb Presenter Pattern

| Type | Where | Responsibility | Injects Services? | Makes HTTP Calls? |
|---|---|---|---|---|
| **Smart Container** | `features/*/pages/` | Fetches data, manages state, passes down via `@Input()`, handles `@Output()` events | Yes | Yes (via services) |
| **Dumb Presenter** | `features/*/components/` and `shared/components/` | Pure rendering. Receives data, emits events. Highly reusable. | No | Never |

---

## 6. API Contract

This frontend consumes **V2 REST endpoints only**:

| Endpoint | Method | Module | Purpose |
|---|---|---|---|
| `/api/v2/formTemplates` | GET | Data Capture | List available templates |
| `/api/v2/formTemplates/{uid}` | GET | Data Capture | Get V2 template tree for rendering |
| `/api/v2/dataSubmission` | POST | Data Capture | Submit normalized V2 submission |
| `/api/v2/dataSubmission` | GET | Review | Browse/search submissions |
| `/api/v2/dataSubmission/{uid}` | GET | Review + Data Capture | Load existing submission for review or editing |
| `/api/v1/dataFormTemplates` | POST | Admin | Template CRUD (until V2 write endpoints exist) |
| (auth endpoints) | POST | Core | Login, token refresh |

> [!NOTE]
> Admin module uses V1 for template writes initially. This is acceptable because template write is an admin-only operation and the V1 endpoint remains stable. When V2 template write endpoints are built, Admin migrates — but this is internal to DatarunAPI and invisible to external consumers.

---

## 7. Offline Support (Deferred)

The Form Engine is designed as a pure state machine with no infrastructure dependencies. This means offline persistence (IndexedDB + sync queue) can be added as an infrastructure layer without modifying the engine, the UI components, or the V2 API contract.

**Deferred until:** Core online flow is stable and tested.

**When implemented:** The `SubmissionService` gains a second delivery path (IndexedDB queue) alongside the existing direct POST. The Form Engine API does not change.

---

## 8. Related Docs

| Topic | Document | When to Read |
|---|---|---|
| **Form Engine contract** | [Form Engine](form-engine.md) | When building the Data Capture module |
| **V2 data contracts** | [V2 Contract](../../form_template_and_submission_v2_contract_discussion.md) | When you need the full V2 spec (submission shape, template tree, rules, migration) |
| **Auth & SSO** | [Auth & Authorization](../../architecture/auth-and-authorization.md) | When implementing login and guards |
| **System context** | [Context Map](../../architecture/context-map.md) | When you need to understand how this app relates to LMIS |
| **Integration boundary** | [Integration Contract](../../architecture/integration-contract-datarunapi.md) | When you need to understand V1/V2 coexistence |
