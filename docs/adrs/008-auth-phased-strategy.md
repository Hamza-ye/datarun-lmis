# ADR-008: Authentication — Phased Strategy

**Status:** Accepted (Revised)
**Date:** 2026-03-03
**Revised:** 2026-03-03

## Context

DatarunAPI (our upstream data-collection platform) is the existing identity provider. It originally used HS256 (shared symmetric key) JWT signing. LMIS is a new downstream system that needs to validate user identity and enforce its own domain-specific authorization.

The original version of this ADR proposed separate user populations (LMIS issues its own JWTs). This was revised after DatarunAPI successfully migrated to **RS256 signing with a JWKS endpoint**, enabling a cleaner single-identity-provider model.

## Decision

We adopt a **two-phase authentication strategy** with a strict **identity vs. authorization split.**

### Core Principle: Identity ≠ Authorization

| Concern | Owner | Where It Lives |
|---|---|---|
| **Identity** ("who is this person?") | DatarunAPI | JWT `sub`, `name`, generic roles |
| **Authorization** ("what can they do in LMIS?") | LMIS | `lmis_user_permissions` table, keyed by `sub` |

DatarunAPI's JWT must **never** contain LMIS-specific claims (`allowed_nodes`, `ledger_supervisor`, etc.). This preserves DatarunAPI's domain-agnostic nature.

### Phase 1: DatarunAPI as Identity Provider (Current)

| Channel | Mechanism |
|---|---|
| **All users** | Authenticate against DatarunAPI → receive RS256-signed JWT |
| **LMIS validation** | FastAPI validates JWT via DatarunAPI's `/.well-known/jwks.json` (public key only) |
| **LMIS authorization** | LMIS looks up `sub` in its own `lmis_user_permissions` → builds `ActorContext` |
| **Service-to-service** | Adapter uses a service account to authenticate to DatarunAPI |

**Key properties:**
- Single sign-on across all services (one token, validated everywhere via JWKS).
- No shared secrets. LMIS only needs the public key.
- LMIS authorization is fully independent of DatarunAPI.
- Adding a new service = configuring one JWKS URI. No code changes to DatarunAPI.

### Phase 2: Federated Identity (Future)

Deploy Keycloak (or equivalent). Both DatarunAPI and LMIS become relying parties. Migrate user records to the IdP. The `ActorContext` enrichment pattern remains identical — only the JWT issuer and JWKS URI change.

## Consequences

**Positive:**
- Clean DDD boundary: DatarunAPI owns identity, LMIS owns authorization.
- SSO is automatic and free via JWKS-based validation.
- No LMIS vocabulary leaks into DatarunAPI's token claims.
- Phase 2 migration is non-breaking (swap JWKS URI, done).

**Negative:**
- LMIS must maintain its own `lmis_user_permissions` table to map `sub` → roles/nodes.
- New LMIS users must first exist in DatarunAPI (or Phase 2's IdP) to get a JWT.

**Neutral:**
- The `ActorContext` pattern works identically in both phases. Only the identity source changes.

## Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| **Share DatarunAPI's HS256 symmetric key** | Security liability. Shared secrets across system boundaries violate zero-trust principles. |
| **Deploy Keycloak immediately** | Operationally premature. DatarunAPI is in production with mobile clients. |
| **LMIS issues its own JWTs (separate populations)** | Originally proposed, then revised. Single identity provider is simpler and enables SSO. |
| **Embed LMIS claims in DatarunAPI's JWT** | Violates OHS boundary. DatarunAPI must not know LMIS vocabulary. |

## Related

- [Auth & Authorization](../architecture/auth-and-authorization.md)
- [Context Map](../architecture/context-map.md)
- [Integration Contract — DatarunAPI](../architecture/integration-contract-datarunapi.md)
