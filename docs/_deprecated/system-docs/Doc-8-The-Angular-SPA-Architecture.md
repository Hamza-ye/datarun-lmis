# Arch-Doc 8: The Angular SPA Architecture

This document defines the strict, production-grade architectural rules for the National LMIS Ledger Frontend. It serves as the absolute control plane for all UI development. If a requested UI feature violates these rules, it must be rejected or redesigned.

---

## 1. Directory Structure & Bounded Contexts

The `frontend/src/app` directory must perfectly mirror the backend's Modular Monolith structure. No "Big Ball of Mud" architectures are permitted.

*   `@core/`: **The Nervous System.** Contains Singleton services, HTTP Interceptors (Auth, Error), and Router Guards. Nothing here should relate to specific business domains.
*   `@shared/`: **The Common Toolbox.** Contains Dumb UI components (e.g., Glassmorphism Buttons, Status Badges), Reusable Directives, and isolated UI Pipes.
*   `@features/`: **The Bounded Contexts.** Isolated domain modules (`adapter`, `ledger`, `kernel`). 
    *   *Rule:* A component inside `features/adapter` can NEVER import a component from `features/ledger`. They must remain perfectly decoupled and communicate only through routing or backend state changes.

## 2. Container vs. Presenter (Smart vs. Dumb)

Every UI feature must be split into two types of components:

*   **Smart Containers (Pages/Views):**
    *   Responsible for injecting Services, fetching data from the API, and managing state (Signals).
    *   They pass raw data down to Dumb Components via `@Input()` bindings.
    *   They handle actions emitted from Dumb Components via `@Output()` bindings.
*   **Dumb Presenters (UI Components):**
    *   Purely responsible for rendering HTML/CSS.
    *   They **must make ZERO HTTP calls**.
    *   They are highly reusable and easily Unit Tested as pure state machines.

## 3. State Management: Native Signals

We do not use NgRx or heavy Redux boilerplate. The application relies entirely on modern **Angular 19+ Signals** (`signal`, `computed`, `effect`) for reactivity.

*   Component state should be localized within the Smart Container using `signal()`.
*   Global state (like the current Auth Context or the cached Node Topology) should reside in `@core` or `@shared` Singleton Services exposing `computed()` signals or `BehaviorSubjects` / `Observables` if handling async HTTP streams.

## 4. The Shared Kernel Rule (Performance Invariant)

The system deals heavily in UUIDs (`node_id`, `item_id`). The UI must **never** perform an HTTP request per row to resolve a UUID to a human-readable name.

*   *Rule:* All UUID resolution must be handled by cached `@shared` resolver pipes (e.g., `{{ transaction.node_id | resolveNodeName }}`). 
*   These pipes rely on a `TopologyService` that fetches the `/api/kernel/nodes` dictionary exactly **once** on application bootstrap (or lazy-loads and caches it).

## 5. Typescript Strictness & The OpenAPI Contract

The frontend layer represents the final consumer of the backend API.

*   *Rule:* Every API request and response must be strictly typed using Data Transfer Objects (DTOs) that perfectly match the `/openapi/openapi.yaml` specification.
*   The `any` keyword is **strictly forbidden** in service and component class definitions.

## 6. Development Strategy: Vertical Slivers

Development happens in vertical, isolated slivers. A single Git commit should never attempt to build the entire Ledger UI. 
*   We build the Adapter DLQ, test it, and commit. 
*   We build the Gatekeeper Inbox, test it, and commit. 
This preserves the ability to revert changes without destroying adjacent domains.
