# Authentication & Authorization

## Overview

Authentication is the number one reason "decoupled" systems accidentally become tightly coupled. This document ensures that identity and access control are clean, scalable, and perfectly separated across the Modular Monolith.

## 1. Authentication (Identity: "Who are you?")

**Rule:** The system does NOT manage passwords, sessions, or logins.

Authentication is entirely outsourced to a dedicated **Identity Provider (IdP)** (Keycloak, Auth0, Azure AD, or AWS Cognito).

1. A user (or external source system) authenticates with the IdP.
2. The IdP returns a **JSON Web Token (JWT)**.
3. The client includes the JWT in the `Authorization: Bearer <token>` header.
4. FastAPI middleware validates the JWT's cryptographic signature using the IdP's public keys.

**Why this preserves boundaries:** Neither the Adapter nor the Ledger needs to query a database to know who the user is. Proof of identity is cryptographically baked into the token.

## 2. Authorization (Access: "What can you do?")

### Layer A: Scopes & Roles (Endpoint Access)

The JWT contains standard claims like `roles` or `scopes`. FastAPI Dependency Injection checks the token:

| Actor | Scope / Role | Allowed Actions |
| --- | --- | --- |
| External Source System | `scope: submit_adapter_payload` | `POST /api/adapter/inbox` |
| Adapter Worker (System Account) | `role: ledger_system_writer` | `POST /api/ledger/commands` |
| Supervisor User | `role: ledger_supervisor` | `POST /api/ledger/gatekeeper/{id}/approve` |

### Layer B: Claims & RBAC (Data Access / Row-Level Security)

We restrict *where* an actor can act by injecting **Contextual Claims** into the JWT:

```json
{
  "sub": "user_uuid_5678",
  "name": "Jane Doe",
  "roles": ["ledger_supervisor"],
  "allowed_nodes": ["DIST-A", "CLINIC_1"]
}
```

When the Approval Gatekeeper processes an approval:
1. Extract `allowed_nodes` from the validated JWT.
2. Check if the `StagedCommand`'s `node_id` falls under the actor's jurisdiction.
3. The Shared Kernel's Node Registry resolves the hierarchy (e.g., `CLINIC_1` is under `DIST-A`).
4. If authorized → proceed. If not → `403 Forbidden`.

## 3. The ActorContext Pattern

```python
# HTTP Layer extracts context from the token
async def get_current_actor(token_data = Depends(verify_jwt)) -> ActorContext:
    return ActorContext(
        actor_id=token_data.sub,
        roles=token_data.roles,
        allowed_nodes=token_data.allowed_nodes
    )

# API Router passes it to the Service
@router.post("/ledger/gatekeeper/{id}/approve")
async def approve_staged_transaction(
    id: UUID,
    payload: ApprovalPayload,
    actor: ActorContext = Depends(get_current_actor)
):
    actor.require_role("ledger_supervisor")
    await GatekeeperService.resolve_command(session, id, payload, actor)
```

**The Domain Rule:** Domain logic never imports an `AppUser` model. It only stores the `actor_id` string. If someone wants the actor's email, the Frontend queries the IdP directly.

## Summary

1. **No Shared Users Table:** All authentication via external IdP and JWTs.
2. **Stateless Roles:** Scopes/Roles live inside the token. Each module asserts the required role on its own API router.
3. **Data Filtering via Token Claims:** The `allowed_nodes` array in the token acts as the RBAC boundary.
4. **Actor Context Object:** A standardized Python object injected into services; domain logic remains pure and unaware of HTTP headers or JWT libraries.
