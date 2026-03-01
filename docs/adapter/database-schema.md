# Adapter Database Schema

## Overview

The Adapter owns its own independent database schema. It shares zero tables with the Ledger.

## Tables

### `adapter_inbox` — The Unified Inbox

The Store-and-Forward buffer. When a source system pushes data, it immediately lands here. Also serves as the DLQ state machine (no separate DLQ table).

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Internal Inbox ID |
| `correlation_id` | UUID | Groups logical retries together |
| `parent_inbox_id` | UUID (nullable) | Points to previous failed attempt (for replays) |
| `source_system` | String | e.g., `commcare_mobile` |
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
CREATE INDEX idx_inbox_pending ON adapter_inbox (status) WHERE status IN ('RECEIVED', 'RETRY_EGRESS');
```
Guarantees sub-millisecond polling in tables with millions of forwarded/failed rows.

---

### `adapter_crosswalks` — The Dictionary

External dictionary for high-speed lookups during mapping.

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Primary Key |
| `namespace` | String | Grouping (e.g., `dhis2_nodes`, `odk_commodities`) |
| `source_value` | String | "Messy" value from external app (e.g., `act_80`) |
| `internal_id` | String | Clean ID for destination (e.g., `PROD-AL-01`) |
| `metadata_json` | JSONB | Contextual defaults or multipliers (e.g., `transform_factor`) |
| `created_at` | Timestamp | Record creation time |

---

### `mapping_contracts` — The Rule Store

Stores the pure JSON DSL that powers the transformation engine.

| Column | Type | Description |
| --- | --- | --- |
| `id` | String (PK) | Contract identifier (e.g., `hf_receipt_902`) |
| `version` | String | Semantic version |
| `status` | Enum | `DRAFT`, `REVIEW`, `APPROVED`, `ACTIVE`, `DEPRECATED`, `ARCHIVED`, `REJECTED` |
| `dsl_config` | JSONB | The JSON DSL config blob |
| `created_at` | Timestamp | Record creation time |

---

### `adapter_egress_logs` — The Delivery Audit Trail

Immutable record of every Layer 3 delivery attempt.

| Column | Type | Description |
| --- | --- | --- |
| `run_id` | UUID (PK) | Unique run identifier |
| `inbox_id` | UUID (FK) | Link to `adapter_inbox` |
| `contract_version_id` | String | Mapping rules version used |
| `status` | Enum | `SUCCESS`, `FAILED_MAPPING`, `FAILED_DESTINATION` |
| `destination_http_code` | Integer | HTTP status code returned |
| `destination_response` | Text | Exact JSON response from destination |
| `retry_count` | BigInteger | Number of delivery attempts |
| `delivery_time_ms` | BigInteger | Performance tracking |
| `execution_time_ms` | BigInteger | Total processing time |

---

### `adapter_admin_jobs` — Bulk Operation Tracker

Tracks bulk admin operations (e.g., reprocessing 500 DLQ records).

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Job ID |
| `job_type` | String | `REPLAY`, `BULK_DELETE` |
| `triggered_by` | String | Actor ID |
| `affected_records_count` | Integer | Total records targeted |
| `success_count` | Integer | Successfully processed |
| `failure_count` | Integer | Failed during reprocessing |
| `created_at` | Timestamp | When the job was triggered |
