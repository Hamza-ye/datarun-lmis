# Adapter Database Schema

## Overview

The Adapter owns its own independent database schema. It shares zero tables with the Ledger.

## Tables

### `adapter_inbox` — The Unified Inbox

The Store-and-Forward buffer. When DatarunAPI pushes data (or the Adapter pulls it), it immediately lands here. Also serves as the DLQ state machine (no separate DLQ table).

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Internal Inbox ID |
| `correlation_id` | UUID | Groups logical retries together |
| `parent_inbox_id` | UUID (nullable) | Points to previous failed attempt (for replays) |
| `source_system` | String | e.g., `datarun_api` |
| `source_event_id` | String | Unique ID from the source for dedup |
| `payload` | JSONB | Exact bits submitted by external app (`raw_payload`) |
| `mapped_payload` | JSONB (nullable) | Exact JSON produced by Layer 2 transformation |
| `mapping_id` | String (nullable) | Contract ID used for this transformation |
| `mapping_version` | String (nullable) | Contract version used for this transformation |
| `status` | Enum | `RECEIVED`, `PROCESSING`, `MAPPED`, `FORWARDED`, `DLQ`, `RETRY_EGRESS`, `DESTINATION_REJECTED`, `REPROCESSED` |
| `error_message` | String | Failure reason (if DLQ/ERROR) |
| `created_at` | Timestamp | When the payload hit the API |
| `updated_at` | Timestamp | Last status change |

**Check Constraint:** `(status NOT IN ('MAPPED', 'FORWARDED', 'RETRY_EGRESS', 'DESTINATION_REJECTED')) OR (mapping_id IS NOT NULL AND mapping_version IS NOT NULL AND mapped_payload IS NOT NULL)`

**Partial Index (Performance):**
```sql
CREATE INDEX idx_inbox_pending ON adapter_inbox (status) WHERE status IN ('RECEIVED', 'MAPPED', 'RETRY_EGRESS');
```
Guarantees sub-millisecond polling in tables with millions of forwarded/failed rows. Includes `MAPPED` because the Layer 3 egress worker polls for both `MAPPED` and `RETRY_EGRESS` rows.

---

### `adapter_crosswalks` — The Dictionary

External dictionary for high-speed lookups during mapping.

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Primary Key |
| `namespace` | String | Grouping (e.g., `datarun_nodes`, `datarun_commodities`) |
| `source_value` | String | "Messy" value from external app (e.g., `act_80`) |
| `internal_id` | String | Clean ID for destination (e.g., `PROD-AL-01`) |
| `metadata_json` | JSONB | Contextual defaults or multipliers (e.g., `transform_factor`) |
| `is_active` | Boolean | Default `TRUE`. Deactivated entries are treated as unmapped (the dictionary's `on_unmapped` strategy applies). |
| `created_at` | Timestamp | Record creation time |
| `updated_at` | Timestamp | Last modification time |

**UNIQUE Constraint:**
```sql
UNIQUE (namespace, source_value)
```
> **Invariant:** Duplicate `(namespace, source_value)` pairs must be rejected at insert time. Without this, crosswalk lookups return non-deterministic results.

**Deactivation Semantics:** When a node is deactivated in the Shared Kernel (e.g., clinic closed), the corresponding crosswalk entry should be set to `is_active = FALSE` rather than deleted. This preserves audit history while preventing new payloads from mapping to retired entities.

---

### `mapping_contracts` — The Rule Store

Stores the pure JSON DSL that powers the transformation engine.

| Column | Type | Description |
| --- | --- | --- |
| `id` | String (PK) | Contract identifier (e.g., `hf_receipt_902`) |
| `version` | String | Semantic version |
| `status` | Enum | `DRAFT`, `REVIEW`, `APPROVED`, `ACTIVE`, `DEPRECATED`, `REJECTED` |
| `visible_in_ui` | Boolean | Default `TRUE`. Set to `FALSE` to hide from active UI (replaces the former `ARCHIVED` status). |
| `dsl_config` | JSONB | The JSON DSL config blob |
| `sample_in` | JSONB (nullable) | Sample input payload for contract testing |
| `expected_out` | JSONB (nullable) | Expected output for contract validation |
| `test_result_metadata` | JSONB (nullable) | Results from the last test run |
| `created_at` | Timestamp | Record creation time |

---

### `adapter_egress_logs` — The Delivery Audit Trail

Immutable record of every Layer 3 delivery attempt.

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Unique log entry identifier |
| `inbox_id` | UUID (FK) | Link to `adapter_inbox` |
| `contract_version_id` | String (nullable) | Mapping rules version used |
| `destination_url` | String | Target URL for the delivery attempt |
| `request_payload` | JSONB | Exact payload sent (denormalized for audit — survives inbox reprocessing) |
| `destination_http_code` | Integer (nullable) | HTTP status code returned (`NULL` on network error) |
| `destination_response` | Text (nullable) | Exact response from destination |
| `status` | String (nullable) | `SUCCESS`, `FAILED`, `TIMEOUT`, `NETWORK_ERROR` |
| `retry_count` | Integer | Number of delivery attempts |
| `execution_time_ms` | Integer (nullable) | Total processing time (ms) |
| `created_at` | Timestamp | When the delivery attempt was logged |

---

### `adapter_admin_jobs` — Bulk Operation Tracker

Tracks bulk admin operations (e.g., reprocessing 500 DLQ records).

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Job ID |
| `job_type` | String | `CROSSWALK_IMPORT`, `BULK_REPLAY`, `BULK_DELETE` |
| `status` | String | `PENDING`, `RUNNING`, `COMPLETED`, `FAILED` |
| `submitted_by` | String (nullable) | Actor ID of the user who triggered the job |
| `parameters` | JSONB (nullable) | Input parameters (e.g., filter criteria, file path) |
| `result_summary` | JSONB (nullable) | Output results (e.g., `{"processed": 500, "failed": 3}`) |
| `error_message` | String (nullable) | Error details if job failed |
| `created_at` | Timestamp | When the job was triggered |
| `updated_at` | Timestamp | Last status change |
