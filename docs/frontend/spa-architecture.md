# Angular SPA Architecture

## Overview

The frontend defines the strict, production-grade architectural rules for the LMIS UI. If a requested UI feature violates these rules, it must be rejected or redesigned.

## 1. Directory Structure & Bounded Contexts

`frontend/src/app` must mirror the backend's Modular Monolith structure:

| Directory | Role | Contents |
| --- | --- | --- |
| `@core/` | The Nervous System | Singleton services, HTTP Interceptors (Auth, Error), Router Guards |
| `@shared/` | The Common Toolbox | Dumb UI components, Reusable Directives, UI Pipes |
| `@features/` | Bounded Contexts | Isolated domain modules (`adapter`, `ledger`, `kernel`) |

**Isolation Rule:** A component inside `features/adapter` can NEVER import from `features/ledger`. They communicate only through routing or backend state changes.

## 2. Container vs. Presenter (Smart vs. Dumb)

| Type | Responsibility | HTTP Calls |
| --- | --- | --- |
| **Smart Containers** (Pages/Views) | Inject Services, fetch data, manage state (Signals). Pass data down via `@Input()`. Handle actions from `@Output()`. | YES |
| **Dumb Presenters** (UI Components) | Pure HTML/CSS rendering. Highly reusable. Easily unit tested. | **ZERO** |

## 3. State Management: Native Signals

Uses modern **Angular 19+ Signals** (`signal`, `computed`, `effect`). No NgRx or Redux boilerplate.

- Component state: localized within Smart Containers using `signal()`.
- Global state: in `@core` or `@shared` Singleton Services exposing `computed()` signals.

## 4. Shared Kernel Rule (Performance)

The UI must **never** perform an HTTP request per row to resolve a UUID to a name.

- All UUID resolution via cached `@shared` resolver pipes (e.g., `{{ node_id | resolveNodeName }}`).
- Pipes rely on a `TopologyService` that fetches `/api/kernel/nodes` once on bootstrap (or lazy-loads and caches).

## 5. TypeScript Strictness & OpenAPI Contract

- Every API request/response must be typed using DTOs matching `/openapi/openapi.yaml`.
- The `any` keyword is **strictly forbidden** in service and component definitions.

## 6. Development Strategy: Vertical Slivers

Build in isolated, vertical slivers:
- Build the Adapter DLQ → test → commit.
- Build the Gatekeeper Inbox → test → commit.

This preserves the ability to revert changes without destroying adjacent domains.

## Related Docs

- **Backend APIs:** Individual BC docs in [adapter/](../adapter/), [ledger/](../ledger/), [kernel/](../kernel/)
- **Composition endpoints:** [Composition Overview](../composition/composition-overview.md)
