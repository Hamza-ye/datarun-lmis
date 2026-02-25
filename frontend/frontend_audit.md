# Frontend Architecture Audit & Refactoring Plan

## Current State Analysis
A scan of `frontend/src/app` reveals a modern Angular 19+ foundation that has drifted from the strict architectural invariants defined in our System Docs (Docs 1-8).

### 1. Structural Strengths (Keepers)
- The application correctly implements isolated lazy-loaded modules (`@features/ledger`, `@features/kernel`, `@features/adapter`).
- The `app.routes.ts` structure is generally clean and aligns with the Backend's bounded contexts.
- The HTTP Interceptor patterns (`auth.interceptor.ts`, `error.interceptor.ts`) correctly implement stateless authentication without relying on tight coupling to a user object.

### 2. Architectural Violations (Refactoring Targets)

#### Violation A: Tech Stack Contamination
The `app-stock-balances` component heavily relies on Angular Material (`MatTableModule`, `MatPaginator`). 
**The Fix:** As mandated, we must strip out Angular Material and replace it with custom Vanilla SCSS (Glassmorphism, Inter font).

#### Violation B: Obsolete State Management (RxJS over Signals)
Services like `LedgerService` and `AuthService` are still using `BehaviorSubjects` and raw `Observables`.
**The Fix:** Refactor global state caches (like Auth and Topology) to use Angular 19 `signal()`, `computed()`, and the new `toSignal` interoperability function.

#### Violation C: Missing Shared Kernel Pipes
Components are rendering raw UUIDs or fetching lists repeatedly.
**The Fix:** Build `@shared/pipes/node-name.pipe.ts` backed by a central `TopologyService` Signal store to prevent NxN HTTP calls.

#### Violation D: API Contract Drift
The frontend `LedgerService` is calling `/api/ledger/gatekeeper/pending`, but the official Phase 4.5 OpenAPI spec changed this to `/api/ledger/gatekeeper/staged`. 
**The Fix:** Align all service methods with the `openapi.yaml` contract.

---

## The Execution Plan (Phase 5.2 - 5.5)

To prevent breaking the app, we will rebuild it iteratively using the **Sliver Strategy**:

### Sliver 1: The Core Rewrite & Design System (Phase 5.2)
- Remove `@angular/material` from `package.json`.
- Create `styles.scss` with the new Glassmorphism variables, dark-mode toggles, and typography.
- Refactor `AuthService` to use Signals instead of BehaviorSubjects.

### Sliver 2: The Shared Kernel Pipe (Phase 5.3)
- Build the `TopologyService` using Signals to cache `GET /api/kernel/nodes`.
- Build the `NodeNamePipe` and `CommodityNamePipe`.

### Sliver 3: Adapter Admin & DLQ (Phase 5.4)
- Build the DLQ Dashboard (HTML/SCSS) and wire it to the `POST /api/adapter/admin/dlq/{id}/retry` endpoint.

### Sliver 4: Ledger Gatekeeper & In-Transit (Phase 5.5)
- Build the Supervisor Inbox using the strictly typed Gatekeeper schemas from Phase 4.5.
- Build the In-Transit Table and "Receive Transfer" actions.
