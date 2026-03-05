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

## V2 Published Language (Normalized Contracts)

DatarunAPI is introducing a V2 API alongside V1. The V2 Published Language uses **normalized contracts** that decouple data from UI layout.

### Two New Contract Shapes

| Contract | V1 Shape | V2 Shape | Reference |
|---|---|---|---|
| **Submission** | Section-wrapped JSON (`{ main: {…}, medicines: [{…}] }`) with arrays for repeaters | Flat `values` + identity-keyed `collections` maps | [V2 Contract §4](../form_template_and_submission_v2_contract_discussion.md#4-v2-submission-contract) |
| **Template** | Two flat arrays: `sections[]` + `fields[]` linked by `parent` string | Nested tree with typed nodes, `binding` semantics | [V2 Contract §5](../form_template_and_submission_v2_contract_discussion.md#5-v2-template-tree-contract) |

### What Changes for Downstream BCs

The V2 submission shape is structurally different from V1. A downstream BC (e.g., the Adapter) that switches from V1 to V2 must update its **mapping contract** to target the new JSON paths:

| V1 Path | V2 Path |
|---|---|
| `formData.main.visitdate` | `values.visitdate` |
| `formData.medicines[0].amd` | `collections.medicines.<row_id>.amd` |

No other changes are required — the Adapter's 3-layer pipeline, auth, and egress remain identical.

---

## V1 / V2 Coexistence

V1 and V2 endpoints run simultaneously on DatarunAPI. Both read from and write to the **same canonical store**.

```
Mobile (V1 consumer)  ──► V1 REST ──► Internal Translator ──► Canonical Store
                                                                    ▲
Web Frontend (V2 consumer) ──► V2 REST ──── passthrough ────────────┘
```

### Key Rules

1. **V1 endpoints are unchanged.** Mobile app continues to work without modification.
2. **V2 endpoints speak the canonical shape natively.** No translation overhead.
3. **The internal translator is NOT an API.** It lives inside DatarunAPI's service layer. External consumers never see it.
4. **No dual-write.** Single canonical store. V1 reads trigger on-the-fly denormalization.

### What Does NOT Change Between V1 and V2

| Stable | Detail |
|---|---|
| Auth (JWKS) | Same JWT, same endpoint, same validation |
| Entity UIDs | `submission.uid`, `template.uid` remain 11-char stable identifiers |
| Submission identity | `uid` + `serialNumber` are unchanged |
| API path prefix | V1: `/api/v1/*`, V2: `/api/v2/*` |

---

## Downstream BC Migration Path

Downstream BCs (e.g., the LMIS Adapter) are **not required** to migrate to V2. The path is:

1. **Today:** Adapter consumes V1 via existing mapping contracts. No change needed.
2. **When ready:** Adapter creates new mapping contract versions targeting V2 schema. Old contracts remain `ACTIVE` for V1.
3. **Transition:** Both contract versions can coexist. The Adapter can route some templates to V1 contracts and others to V2.
4. **Completion:** Once all templates are covered by V2 contracts, V1 contracts are deprecated. V1 API endpoints remain available until all consumers have migrated.

> [!IMPORTANT]
> DatarunAPI never forces a V2 migration on downstream BCs. Each BC migrates on its own schedule by updating its own mapping contracts.

---

## Constraints & Known Limitations

1. **No real-time push (yet).** The Adapter currently pulls submissions via polling or scheduled sync. Webhooks are a planned enhancement.
2. **DatarunAPI's Party Access Model** is ~80% implemented. The Adapter should gracefully handle missing `party` fields.
3. **DatarunAPI has known dead code and design issues.** These are internal and do not affect the integration contract as long as the API surface remains stable.

## Related Docs

- [Context Map](context-map.md)
- [Adapter Overview](../adapter/adapter-overview.md)
- [Mapping Contract Lifecycle](../adapter/mapping-contract-lifecycle.md)
