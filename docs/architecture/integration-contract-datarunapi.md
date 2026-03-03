# Integration Contract — DatarunAPI

## Purpose

This document pins the integration boundary between the LMIS Adapter BC and DatarunAPI. It defines:
- What DatarunAPI **is** to LMIS
- What API surface LMIS depends on
- How authentication works across the boundary
- Evolution and versioning expectations

---

## DatarunAPI Identity

| Property | Value |
|---|---|
| **DDD Role** | Open-Host Service (OHS) + Published Language (PL) |
| **Codebase** | [DataRun-ye/data-run-api](https://github.com/DataRun-ye/data-run-api) |
| **Tech Stack** | Java, Spring Boot, PostgreSQL |
| **Mobile Client** | [DataRun-ye/data-run-mobile](https://github.com/DataRun-ye/data-run-mobile) (Flutter/Dart) |
| **Deployment** | Independent. Separate server, separate DB, separate release cycle. |
| **Nature** | General-purpose data collection platform. Domain-agnostic. |

---

## Published Language (Submission Schema)

DatarunAPI's core output consumed by the Adapter is the **submission payload**: a JSON object representing data collected via a template-driven mobile form.

### Key Entities in DatarunAPI's Model

| Entity | Purpose | LMIS Interpretation |
|---|---|---|
| `data_template` | Form definition (fields, repeat blocks) | Adapter mapping contract targets a specific template UID |
| `submission` | Collected data instance | `raw_payload` stored in `adapter_inbox` |
| `activity` | Collection context (e.g., "Malaria Unit Flow Q1") | Used to scope which mapping contract applies |
| `party` | Actor/location registry | Crosswalk-resolved to Kernel `node_id` |
| `assignment` | Links template + team + org_unit + period | Determines who can submit what, where |
| `org_unit` | Organizational hierarchy | Mapped to Kernel Node Registry via crosswalks |

> [!IMPORTANT]
> DatarunAPI's entities are **generic**. The interpretation as stock receipts, transfers, adjustments, etc. is the **Adapter's mapping contract**, not DatarunAPI's responsibility.

---

## Authentication Across the Boundary

### Identity Provider: DatarunAPI

DatarunAPI is the **single identity provider** for all systems. It issues RS256-signed JWTs and publishes its public key at `/.well-known/jwks.json`.

| Channel | Mechanism |
|---|---|
| Adapter → DatarunAPI | **Service account.** Adapter authenticates with a dedicated credential, receives a DatarunAPI JWT. Used for pulling submissions or registering webhooks. |
| LMIS Web UI | **SSO via DatarunAPI.** User authenticates once, receives JWT. LMIS validates via JWKS and enriches with its own authorization (`lmis_user_permissions`). |
| Mobile App → DatarunAPI | **Direct login.** RS256 JWT. No LMIS involvement. |

### Identity vs. Authorization Split

DatarunAPI's JWT contains **identity only** (`sub`, `name`, generic roles). LMIS-specific authorization (`allowed_nodes`, `ledger_supervisor`) lives in LMIS's own `lmis_user_permissions` table. See [Auth & Authorization](auth-and-authorization.md).

### Phase 2 (Future)

Keycloak replaces DatarunAPI as identity provider. LMIS authorization layer stays unchanged. See [ADR-008](../adrs/008-auth-phased-strategy.md).

---

## Versioning & Evolution

| Expectation | Rule |
|---|---|
| **API versioning** | DatarunAPI should version its REST API (e.g., `/api/v1/submissions`). The Adapter pins to a specific version. |
| **Non-breaking additions** | New fields in submission JSON are safe — the Adapter's mapping contract ignores unmapped fields. |
| **Breaking changes** | Require a new API version. The Adapter creates a new mapping contract version targeting the new schema. Old contracts remain `ACTIVE` for the old API version until deprecated. |
| **Schema discovery** | DatarunAPI should provide an OpenAPI spec or endpoint documentation. The Adapter's mapping contract is the declared translation from this schema to `LedgerCommand`. |

---

## Constraints & Known Limitations

1. **No real-time push (yet).** The Adapter currently pulls submissions via polling or scheduled sync. Webhooks are a planned enhancement.
2. **DatarunAPI's Party Access Model** is ~80% implemented. The Adapter should gracefully handle missing `party` fields.
3. **DatarunAPI has known dead code and design issues.** These are internal and do not affect the integration contract as long as the API surface remains stable.

## Related Docs

- [Context Map](context-map.md)
- [Adapter Overview](../adapter/adapter-overview.md)
- [Mapping Contract Lifecycle](../adapter/mapping-contract-lifecycle.md)
