### The Strategy: The Asynchronous "Store, Cleanse & Forward" Pipeline

The Adapter is a completely standalone, domain-agnostic mapping and routing engine. It has its own isolated database, its own schemas, and zero knowledge of the destination system (like the Ledger). Its only job is to receive a JSON payload, validate it against configured rules, store it, transform it, and blindly forward it to a configured endpoint.

Instead of writing hard-coded `if/else` statements in your Adapter code, we give the Adapter a **Transformation DSL (Domain Specific Language)** in JSON.

The pipeline does four asynchronous things:

1. **Receive & Store (The Inbox):** Receive the raw data, validate its basic structure, save it to the `adapter_inbox`, and immediately return a `202 Accepted` to the source.
2. **Extract:** A background worker pulls the raw data from the Inbox using JSONPath.
3. **Cleanse (Crosswalks):** Run the messy data through defined normalization rules and dictionaries.
4. **Emit & Forward:** Construct the final Payload based on the configuration and POST it to the destination URL.

---

### The JSON Mapping Schema (The "A-to-B" Contract)

Here is how you model the Adapter's configuration to handle variations like `ACT-80` and format the data exactly how the destination wants it. This schema separates the **Rules** (JSON) from the **Data** (Crosswalk DB).

```json
{
  "contract_id": "odk_monthly_stock_report",
  "version": "v1.2",
  "source_system": "commcare_mobile",
  "status": "ACTIVE",

  "destination": {
    "url": "https://api.internal/ledger/v1/commands",
    "method": "POST"
  },

  "trigger_conditions": {
    "description": "How the Adapter knows to use THIS contract",
    "match_path": "$.form_metadata.xmlns",
    "match_value": "http://openrosa.org/form/stock_report_v2"
  },

  "metadata": {
    "source_event_id": { "path": "$.meta.instanceID" },
    "version_timestamp": { "path": "$.meta.submissionDate", "format": "ISO8601" }
  },

  "crosswalks": {
    "inline_dictionaries": {
      "uom_codes": {
        "description": "Small, rarely changing lists stay in JSON",
        "pre_processing": ["UPPERCASE"],
        "map": { "BXS": "BOX", "TABS": "TABLET" },
        "on_unmapped": "USE_DEFAULT",
        "default": "TABLET"
      }
    },
    "external_dictionaries": {
      "node_lookup": {
        "description": "Pointers to the DB for large, frequently changing lists",
        "db_table": "adapter_crosswalks",
        "namespace": "dhis2_org_units",
        "on_unmapped": "DEAD_LETTER_QUEUE"
      },
      "commodity_lookup": {
        "db_table": "adapter_crosswalks",
        "namespace": "national_drug_codes",
        "on_unmapped": "DEAD_LETTER_QUEUE"
      }
    }
  },

  "transformations": {
    "date_formats": {
      "description": "Normalizes messy field dates to standard formats",
      "field_date": {
        "path": "$.report_date",
        "source_format": "DD-MM-YYYY",
        "target_format": "YYYY-MM-DD"
      }
    }
  },
  
  "dry_run": {
    "supported": true,
    "inject_path": "$.metadata.is_dry_run"
  },

  "output_payloads": [
    {
      "description": "Generates a formatted object for every item in the array",
      "condition": {
        "path": "$.report_type",
        "equals": "inventory_count"
      },
      "static_fields": {
         "command_type": "STOCK_COUNT",
         "program": "MALARIA_NMCP"
      },
      "mapped_fields": {
        "target_node": { "path": "$.facility_code", "crosswalk": "external:node_lookup" },
        "transaction_date": { "transform": "date_formats.field_date" }
      },
      "loop_over": "$.drugs_list[*]",
      "loop_payload": {
        "item_id": { "path": "$.drug_code", "crosswalk": "external:commodity_lookup" },
        "quantity": { "path": "$.counted_qty", "cast_to": "INTEGER" },
        "uom": { "path": "$.unit", "crosswalk": "inline:uom_codes" }
      }
    }
  ]
}
```

### Why this design is "Battle-Tested" and Professional

#### 1. The Pre-Processing Pipeline (`pre_processing`)

You mentioned getting `ACT-80`, `act80`, and `act_80`. Instead of mapping every single typo in a dictionary, the schema defines a pre-processing pipeline: `["TRIM", "UPPERCASE", "REMOVE_SPECIAL_CHARS"]`.

* All three variations automatically become `ACT80`.
* The Adapter code just runs the string through those standard string manipulation functions before doing the dictionary lookup.

* Also Hardcoding 600 clinics into a JSON file is exactly the kind of "configuration smell" we want to avoid. If the Ministry of Health opens a new clinic, you shouldn't have to deploy a new JSON mapping version; you should just add a row to a database.

#### 2. The `on_unmapped` Strategy

What happens when the field sends `NEW_DRUG_X` and it's not in the crosswalk?

* You don't want the Destination crashing.
* The `on_unmapped: "REJECT_PAYLOAD"` tells the Adapter to halt and throw an error back to the source, OR you can configure it to `SEND TO DEAD LETTER`, which puts the payload in a holding queue for an admin to map later without dropping the data.

#### 3. External Dictionaries (`external_dictionaries`)

Notice the `node_lookup`. Instead of a map, it provides a `namespace: "dhis2_org_units"`.

* **How it works:** Your database has a simple table: `id`, `namespace`, `source_value`, `internal_value`.
* When the Adapter sees `facility_code: "12345"`, it queries the DB: `SELECT internal_value FROM adapter_crosswalks WHERE namespace = 'dhis2_org_units' AND source_value = '12345'`.
* **Why it's brilliant:** The Ministry adds 50 new clinics. You just bulk-upload them to the DB table. The JSON contract never changes.

#### 4. Conditional Routing (`condition`)

Sometimes one source form handles both Receipts and Issues.

* By adding a `condition` block to the `output_payloads`, the Adapter can evaluate the payload. If `report_type == 'inventory_count'`, it formats it one way. You could add a second block in that array where if `report_type == 'receipt'`, it formats it completely differently.

#### 5. Static Injection (`static_fields`)

The Adapter doesn't intrinsically know what a `STOCK_COUNT` is. It only knows that the user configured it to inject the static key-value pair `"command_type": "STOCK_COUNT"` into the output JSON. This allows the Adapter to fulfill the strict schema requirements of whatever downstream system it is talking to, without carrying domain logic itself.

#### 6. Date Normalization (`transformations`)

Field apps are notorious for sending dates as `22-02-2026` or `02/22/26`. The Destination must **strictly** accept only one format (e.g., ISO-8601 `YYYY-MM-DD`). The Adapter takes on the burden of translating human-readable dates into database-friendly dates.

### The Boundary Check

Does this violate our rules? **No.**
The Adapter is entirely stateless regarding the actual business domain (e.g. *inventory*). It is simply acting as a highly configurable router, buffer, and translator. It reads the JSON, reads the Crosswalk DB, formats the data based on user configuration, and throws it over the fence to the URL provided.

---

## Database schema for the Adapter (The Isolated Sub-System)

The Adapter owns its own independent database schema.

### 1. The Store-and-Forward Inbox

To prevent data loss when downstream systems are down, or when mapping rules are complex, the Adapter acts as an asynchronous buffer. When a source system pushes data, it immediately lands here.

**Table Name:** `adapter_inbox`

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key (Internal Inbox ID). |
| `source_system` | String | e.g., `commcare_mobile`. |
| `raw_payload` | JSONB | The exact bits submitted by the external app. |
| `received_at` | Timestamp | When the payload hit the API. |
| `status` | Enum | `RECEIVED`, `MAPPED`, `FORWARDED`, `DLQ`. |

**The Workflow:** The Source POSTs to the Adapter. The Adapter saves to `adapter_inbox`. The Adapter immediately returns `HTTP 202 Accepted` to the Source. The Source disconnects. A background worker then picks up the `RECEIVED` row and starts the mapping process.

---

### 2. The Crosswalk Registry (Relational Table)

This table acts as the "External Dictionary" mentioned in your JSON contract. It’s designed to be indexed for high-speed lookups during the mapping phase.

**Table Name:** `adapter_crosswalks`

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key. |
| `namespace` | String | Groups mappings (e.g., `dhis2_nodes`, `odk_commodities`). |
| `source_value` | String | The "messy" value from the external app (e.g., `act_80`). |
| `internal_id` | String | The clean ID required by the Destination (e.g., `PROD-AL-01`). |
| `is_active` | Boolean | Allows deactivating a mapping without deleting history. |
| `metadata` | JSONB | **Creative addition:** Store contextual defaults or multipliers specific to this source. |

---

### 3. The Dead Letter Queue (DLQ) Strategy

In professional systems, we assume **something will break.** The DLQ is where "Invalid" or "Unmapped" payloads go to wait for human intervention without blocking the rest of the queue.

**The Workflow:**

1. **The Failure:** The Adapter worker tries to map `facility_code: "999"` but finds no entry in `adapter_crosswalks`.
2. **The Park:** The worker updates the `adapter_inbox` status to `DLQ` and copies the context into the `dead_letter_queue` table.
3. **The Alert:** An admin is notified: *"New unmapped facility code '999' found."*
4. **The Resolution:** The admin adds the mapping to the `adapter_crosswalks` table and clicks **"Reprocess"** on the DLQ entry.
5. **The Success:** The Adapter pulls it from the DLQ, maps it successfully, and forwards it to the destination.

**Table Name:** `dead_letter_queue`

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key. |
| `inbox_id` | UUID | Link to the original payload in `adapter_inbox`. |
| `error_type` | String | `UNMAPPED_NODE`, `UNMAPPED_COMMODITY`, `DESTINATION_REJECTED`. |
| `failed_value` | String | The specific string that caused the mapping failure. |
| `status` | String | `PENDING`, `REPROCESSED`, `IGNORED`. |
| `attempts` | Integer | Number of times reprocessing has been tried. |

---

### 4. The Integration Audit Trail (Run Logs)

Every time the Adapter attempts to map and forward a payload, it leaves a "breadcrumb." This is the definitive record of what the Adapter sent and what the Destination replied.

**Artifact:** `adapter_logs`

* **Purpose:** A permanent, immutable record of every routing attempt.
* **Fields:**
  * `run_id`: UUID.
  * `inbox_id`: Link to the raw ingestion record.
  * `contract_version_id`: Link to the specific mapping rules used.
  * `status`: `SUCCESS`, `FAILED_MAPPING` (stopped internally), `FAILED_DESTINATION` (rejected by HTTP endpoint).
  * `destination_http_code`: The status code returned (e.g. 200, 400).
  * `destination_response`: The exact JSON text returned by the destination system.
  * `execution_time_ms`: Performance tracking.

> **Architect's Note:** If the Destination system rejects the payload, you don't blame the Source. You look in `adapter_logs`, read the `destination_response`, and adjust your mapping JSON accordingly.

---

### 5. The Dead Letter Management Flow (Replay & Generic Dry-Runs)

When an admin "fixes" a mapping in the DLQ, they need a safe way to test it. This relies on the Adapter injecting the `dry_run` flag defined in the configuration. The Adapter doesn't care what the Destination does with the flag—it just injects it to the specified JSON path and fires it off.

**The Replay State Machine:**

1. **PENDING:** The record is stuck (e.g., Unmapped Node).
2. **DRY_RUN:** The Admin clicks "Test." The Adapter injects the `{ "is_dry_run": true }` flag (or whatever is configured in `dry_run.inject_path`) into the mapped payload, and POSTs it to the destination.
    * **Result A (Fail):** Destination returns 400 Validation Error. Admin sees the error in the logs, stays in PENDING.
    * **Result B (Success):** Destination returns 200/202 (having likely rolled back its own transaction due to the flag). Admin sees "Destination Accepted," transitions to READY.
3. **APPLIED:** The Admin clicks "Submit." The Adapter strips the `dry_run` flag (or sets it to false) and sends the real payload. The DLQ record moves to `COMPLETED`.

---

### 6. Mapping Lifecycle & Governance

| State | Editability | Execution Role | Deletion Rule |
| --- | --- | --- | --- |
| **DRAFT** | Full | None (Test only) | Hard Delete allowed if `runs == 0`. |
| **ACTIVE** | **Locked** | Processes live traffic | **Blocked.** Must deprecate first. |
| **DEPRECATED** | **Locked** | None | **Soft-Delete only.** Keep for audit history. |

**The "Atomic Flip" Rule:**
When a user clicks "Activate" on `v1.1`, the system performs an atomic transaction:

1. Check if any `v1.0` is `ACTIVE`.
2. Set `v1.0` to `DEPRECATED`.
3. Set `v1.1` to `ACTIVE`.
4. Log the transition.

> **Pro-Tip:** Never allow editing of an `ACTIVE` version. If you need a change, **Clone to DRAFT**, edit, and re-activate. This ensures that if you look at a log from 3 months ago, you can see exactly which mapping rules were in place at that moment.

---

### 7. Admin Job Tracking (The "Cleanup" Log)

When an admin reprocesses 500 records from the DLQ, you need a record of that **Job**.

**Artifact:** `adapter_admin_jobs`

* **Purpose:** Tracks bulk operations.
* **Fields:** `job_type` (REPLAY/BULK_DELETE), `triggered_by`, `affected_records_count`, `success_count`, `failure_count`.
* **Why:** If an admin accidentally reprocesses the wrong batch, you need a way to identify which transactions were triggered by that specific manual action.

---

### Final Summary for your Adapter Doc

To be "Production Grade", the Adapter module is an isolated, async engine that owns:

1. **The Policies:** `mapping_contracts` (The Rules & Destination URLs).
2. **The Inbox:** `adapter_inbox` (The Async "Store-and-Forward" Buffer).
3. **The Crosswalk:** `adapter_crosswalks` (The Dictionary).
4. **The Hospital:** `dead_letter_queue` (For unmapped or failed data).
5. **The History:** `adapter_logs` (The immutable record of mapping and forwarding).
