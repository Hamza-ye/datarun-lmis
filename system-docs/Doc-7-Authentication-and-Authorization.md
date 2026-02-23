# Arch-Doc 7: Decoupled Authentication & Authorization

Authentication is the number one reason "decoupled" systems accidentally become tightly coupled. If the Adapter and the Ledger share a `users` table, or if the Ledger needs to call the Adapter to ask "is this user allowed?", the architectural boundary is destroyed.

This document outlines the battle-tested, standard approach for keeping Authentication (Identity) and Authorization (Access) clean, scalable, and perfectly separated in a Modular Monolith.

---

## 1. Authentication (Identity: "Who are you?")

**The Rule:** The system does NOT manage passwords, sessions, or logins. 

Authentication is entirely outsourced to a dedicated **Identity Provider (IdP)**. This could be Keycloak, Auth0, Azure AD, or AWS Cognito. 

1. A user (or an external source system) authenticates with the IdP.
2. The IdP returns a **JSON Web Token (JWT)**.
3. The client includes this JWT in the `Authorization: Bearer <token>` header of every HTTP request to our system.
4. Our FastAPI middleware validates the JWT's cryptographic signature using the IdP's public keys. 

**Why this preserves boundaries:**
Neither the Adapter nor the Ledger needs to query a database to know who the user is. The proof of identity is cryptographically baked into the token itself.

---

## 2. Authorization (Access: "What can you do?")

Authorization happens strictly downstream of the API router, but it is divided into two layers: **Scopes** (Endpoint Access) and **Claims** (Data Access).

### Layer A: Scopes & Roles (Endpoint Access)
The JWT issued by the IdP contains standard claims like `roles` or `scopes`. 

When a request hits an endpoint, the FastAPI Dependency Injection checks the token:

*   **External Source System:** Has `scope: submit_adapter_payload`. Can legally `POST /api/adapter/inbox`.
*   **Adapter Worker (Internal System Account):** Has `role: ledger_system_writer`. Can legally `POST /api/ledger/commands`. (This allows the Adapter to talk to the Ledger over HTTP securely).
*   **Supervisor User:** Has `role: ledger_supervisor`. Can legally `POST /api/ledger/gatekeeper/approve`.

**Why this preserves boundaries:**
The Ledger doesn't care *how* you got the `ledger_supervisor` role. It just checks the token string. It doesn't know your email or your password. It only sees: "Actor UUID 1234 has Role Supervisor."

### Layer B: Claims & RBAC (Data Access / Row-Level Security)
Knowing *what* you can do is not enough. We must restrict *where* you can do it. A Supervisor at Clinic A cannot approve transactions for Clinic B.

We inject **Contextual Claims** into the JWT during login at the IdP level:
```json
{
  "sub": "user_uuid_5678",
  "name": "Jane Doe",
  "roles": ["ledger_supervisor"],
  "allowed_nodes": ["DIST-A", "CLINIC_1"] 
}
```

When Area E (Gatekeeper) processes an approval, the logic looks like this:
1. Extract `allowed_nodes` from the validated JWT.
2. Look at the `StagedCommand`. Does its `node_id` fall under `DIST-A` or `CLINIC_1`?
3. (Using the **Shared Kernel's** Node Registry, the system knows `CLINIC_1` is under `DIST-A`).
4. If yes, proceed. If no, `403 Forbidden`.

---

## 3. The Implementation Strategy

To keep the separation of concerns perfect, the system will use **FastAPI Dependencies** to pass the "Actor Context" deeply into the service layers without tightly coupling the domain logic to the HTTP layer.

### The Dependency Injection Pattern
```python
# The HTTP Layer extracts the context from the token
async def get_current_actor(token_data = Depends(verify_jwt)) -> ActorContext:
    return ActorContext(
        actor_id=token_data.sub, 
        roles=token_data.roles, 
        allowed_nodes=token_data.allowed_nodes
    )

# The API Router passes it to the Service
@router.post("/ledger/gatekeeper/{id}/approve")
async def approve_staged_transaction(
    id: UUID, 
    payload: ApprovalPayload, 
    actor: ActorContext = Depends(get_current_actor)
):
    # Ensure they have the Supervisor role
    actor.require_role("ledger_supervisor")
    
    # Pass the stateless actor object to the Domain Service
    await GatekeeperService.resolve_command(session, id, payload, actor)
```

### The Domain Rule
Inside `GatekeeperService` or `EventStoreService`, the database models (`ApprovalAudit`, `InventoryEvent`) record the `actor_id` string. 

The domain logic **never** imports an `AppUser` model. It only stores the `actor_id`. If someone wants to know the email address of the actor, the Frontend queries the IdP directly using that `actor_id`.

## Summary
1. **No Shared Users Table:** All authentication happens via external IdP and JWTs.
2. **Stateless Roles:** Scopes and Roles live inside the token. Each Module (Adapter, Ledger) just asserts the required role on its own API router.
3. **Data Filtering via Token Claims:** The `allowed_nodes` array in the token acts as the RBAC boundary.
4. **Actor Context Object:** A standardized Python object is injected into services, so the domain logic remains pure and unaware of HTTP headers or JWT libraries.
