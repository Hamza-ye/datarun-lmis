# Authentication & Authorization

## Overview

Authentication is the number one reason "decoupled" systems accidentally become tightly coupled. This document enforces a strict **identity vs. authorization split** to keep boundaries clean.

> [!IMPORTANT]
> **Identity** (who are you?) is owned by **DatarunAPI**. **Authorization** (what can you do in LMIS?) is owned by **LMIS**. These concerns must never be conflated. See [ADR-008](../adrs/008-auth-phased-strategy.md).

---

## 1. Authentication (Identity: "Who are you?")

### Phase 1: DatarunAPI as Identity Provider (Current)

DatarunAPI is the **single identity provider** for all systems:

| Channel | Flow |
| --- | --- |
| **Mobile App** | User logs in → DatarunAPI issues RS256 JWT → app uses token for API calls |
| **LMIS Web UI** | User logs in via DatarunAPI → DatarunAPI issues RS256 JWT → Angular SPA uses token for LMIS BFF calls |
| **Adapter (service-to-service)** | Service account authenticates to DatarunAPI → receives JWT for pulling submissions |

**How token validation works:**
1. DatarunAPI signs all JWTs with RS256 (asymmetric).
2. DatarunAPI exposes the public key at `/.well-known/jwks.json`.
3. LMIS's FastAPI middleware validates tokens using this public key. **No shared secrets.**
4. Any new service simply configures a `JwtDecoder` with DatarunAPI's JWKS URI — done.

**SSO is automatic:** A user authenticates once against DatarunAPI. That JWT is valid against any service that validates via the same JWKS endpoint.

### Phase 2: Federated Identity (Future)

When user management complexity demands it, deploy Keycloak (or equivalent). Both DatarunAPI and LMIS become **Relying Parties** of the IdP. The `ActorContext` pattern below remains unchanged — only the token source changes.

---

## 2. Identity vs. Authorization Split

> [!CAUTION]
> DatarunAPI's JWT must **never** contain LMIS-specific claims like `allowed_nodes`, `ledger_supervisor`, or `submit_adapter_payload`. These are LMIS vocabulary — they belong in LMIS's own authorization layer.

### What DatarunAPI's JWT Contains (Identity Only)

```json
{
  "sub": "user_uuid_5678",
  "name": "Jane Doe",
  "roles": ["DATA_COLLECTOR", "SUPERVISOR"]
}
```

Only generic, domain-agnostic claims. DatarunAPI doesn't know what a "ledger" or "node" is.

### What LMIS Adds (Authorization)

LMIS maintains its own `lmis_user_permissions` table in the **LMIS database** (not DatarunAPI's DB), keyed by the `sub` (user ID) from the token:

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Primary key |
| `user_id` | UUID (Unique) | Matches JWT `sub` claim from DatarunAPI |
| `display_name` | String | Cached from JWT `name` for admin convenience |
| `lmis_roles` | JSONB | e.g., `["ledger_supervisor", "adapter_admin"]` |
| `allowed_nodes` | JSONB | e.g., `["DIST-A", "CLINIC_1"]` |
| `is_active` | Boolean | Can be deactivated without touching DatarunAPI |
| `created_at` | Timestamp | When this LMIS permission was created |
| `updated_at` | Timestamp | Last permission change |

When a request arrives:
1. **Validate JWT** signature via DatarunAPI's JWKS → proves identity.
2. **Look up `sub`** in `lmis_user_permissions` → resolves LMIS-specific authorization.
3. **Build `ActorContext`** from both sources → inject into domain services.

---

## 3. Authorization (Access: "What can you do?")

### Layer A: LMIS Roles (Endpoint Access)

FastAPI Dependency Injection checks LMIS-managed roles:

| Actor | LMIS Role | Allowed Actions |
| --- | --- | --- |
| Adapter Worker (System Account) | `ledger_system_writer` | `POST /api/ledger/commands` |
| Supervisor User | `ledger_supervisor` | `POST /api/ledger/gatekeeper/{id}/approve` |
| Admin | `adapter_admin` | `POST /api/adapter/replay`, `GET /api/adapter/inbox` |

### Layer B: Node-Level RBAC (Data Access / Row-Level Security)

We restrict *where* an actor can act using `allowed_nodes` from the LMIS permissions table:

When the Approval Gatekeeper processes an approval:
1. Extract `allowed_nodes` from the `ActorContext` (sourced from LMIS DB, NOT the JWT).
2. Check if the `StagedCommand`'s `node_id` falls under the actor's jurisdiction.
3. The Shared Kernel's Node Registry resolves the hierarchy (e.g., `CLINIC_1` is under `DIST-A`).
4. If authorized → proceed. If not → `403 Forbidden`.

---

## 4. The ActorContext Pattern

```python
# Step 1: Validate JWT (identity from DatarunAPI)
async def verify_identity(token_data = Depends(verify_jwt)) -> TokenIdentity:
    return TokenIdentity(
        actor_id=token_data.sub,
        name=token_data.name,
    )

# Step 2: Enrich with LMIS authorization
async def get_current_actor(
    identity: TokenIdentity = Depends(verify_identity),
    session: AsyncSession = Depends(get_session),
) -> ActorContext:
    perms = await LmisPermissionsRepo.get_by_user_id(session, identity.actor_id)
    return ActorContext(
        actor_id=identity.actor_id,
        roles=perms.lmis_roles,
        allowed_nodes=perms.allowed_nodes,
    )

# Step 3: Use in domain service
@router.post("/ledger/gatekeeper/{id}/approve")
async def approve_staged_transaction(
    id: UUID,
    payload: ApprovalPayload,
    actor: ActorContext = Depends(get_current_actor)
):
    actor.require_role("ledger_supervisor")
    await GatekeeperService.resolve_command(session, id, payload, actor)
```

**The Domain Rule:** Domain logic never imports an `AppUser` model or JWT library. It receives `ActorContext` and nothing else.

> [!NOTE]
> The `ActorContext` pattern is **phase-agnostic**. Whether the JWT comes from DatarunAPI (Phase 1) or Keycloak (Phase 2), only `verify_identity` changes — the authorization lookup and domain services are untouched.

---

## Summary

1. **Identity = DatarunAPI.** Single sign-on across all services via JWKS.
2. **Authorization = LMIS.** Roles, node access, and permissions live in LMIS's own DB.
3. **JWT contains identity only.** No LMIS vocabulary in the token.
4. **ActorContext = identity + authorization.** Built by the HTTP layer, consumed by domain services.
5. **Phase 2: Federation.** Keycloak replaces DatarunAPI as identity provider. LMIS authorization layer stays unchanged.

## Related Docs

- [ADR-008: Auth Phased Strategy](../adrs/008-auth-phased-strategy.md)
- [Context Map](context-map.md)
- [Integration Contract — DatarunAPI](integration-contract-datarunapi.md)
