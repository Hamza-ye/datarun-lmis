### The Strategy: The "Cleanse & Emit" Pipeline
No longer querying or knowing the shared module and its tables, it has it's own added by users dectionaries of cross-walk and mappings roles to do it's job in providing in outputing a command in the way a destination wants.

Instead of writing hard-coded `if/else` statements in your Adapter code, we give the Adapter a **Transformation DSL (Domain Specific Language)** in JSON.

The pipeline does three things:

1. **Extract:** Pull the raw data using JSONPath.
2. **Cleanse (Crosswalks):** Run the messy data through defined normalization rules and dictionaries.
3. **Emit:** Construct the strict Ledger Command.

---

### The JSON Mapping Schema (The "A-to-B" Contract)

Here is how you model the Adapter's configuration to handle your `ACT-80` and implied UOM edge cases seamlessly.
This schema separates the **Rules** (JSON) from the **Data** (Crosswalk DB).

```json
{
  "contract_id": "odk_monthly_stock_report",
  "version": "v1.2",
  "source_system": "commcare_mobile",
  "status": "ACTIVE",

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
      "description": "Normalizes messy field dates to the Ledger's standard",
      "field_date": {
        "path": "$.report_date",
        "source_format": "DD-MM-YYYY",
        "target_format": "YYYY-MM-DD"
      }
    }
  },

  "output_commands": [
    {
      "description": "Generates a STOCK_COUNT command for every item in the array",
      "condition": {
        "path": "$.report_type",
        "equals": "inventory_count"
      },
      "command_type": { "static": "STOCK_COUNT" },
      "target_node": { 
        "path": "$.facility_code", 
        "crosswalk": "external:node_lookup" 
      },
      "transaction_date": { "transform": "date_formats.field_date" },
      "loop_over": "$.drugs_list[*]",
      "payload": {
        "item_id": { "path": "$.drug_code", "crosswalk": "external:commodity_lookup" },
        "quantity": { "path": "$.counted_qty", "cast_to": "INTEGER" },
        "uom": { "path": "$.unit", "crosswalk": "inline:uom_codes" },
        "program": { "static": "MALARIA_NMCP" } 
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

* You don't want the Ledger crashing.
* The `on_unmapped: "REJECT_PAYLOAD"` tells the Adapter to halt and throw an error back to the source, OR you can configure it to `SEND TO DEAD LETTER`, which puts the payload in a holding queue for an admin to map later.

#### 3. External Dictionaries (`external_dictionaries`)

Notice the `node_lookup`. Instead of a map, it provides a `namespace: "dhis2_org_units"`.

* **How it works:** Your database has a simple table: `id`, `namespace`, `source_value`, `internal_value`.
* When the Adapter sees `facility_code: "12345"`, it queries the DB: `SELECT internal_value FROM adapter_crosswalks WHERE namespace = 'dhis2_org_units' AND source_value = '12345'`.
* **Why it's brilliant:** The Ministry adds 50 new clinics. You just bulk-upload them to the DB table. The JSON contract never changes.

#### 4. Conditional Routing (`condition`)

Sometimes one source form handles both Receipts and Issues.

* By adding a `condition` block to the `output_commands`, the Adapter can evaluate the payload. If `report_type == 'inventory_count'`, it emits a `STOCK_COUNT` command. You could add a second block in that array where if `report_type == 'receipt'`, it emits a `RECEIPT` command.

#### 5. Static Injection (`"static": "MALARIA_NMCP"`)

Field apps often omit data that the central ledger desperately needs. For example, the ledger might track inventory by "Funding Program" (Malaria vs. HIV), but the Malaria field app doesn't bother sending that because it assumes you know.

* The `"static"` rule allows the Adapter to inject constant values into the command so the Ledger's strict schema is satisfied.

#### 6. Date Normalization (`transformations`)

Field apps are notorious for sending dates as `22-02-2026` or `02/22/26`. The Ledger must **strictly** accept only one format (e.g., ISO-8601 `YYYY-MM-DD`). The Adapter takes on the burden of translating human-readable dates into database-friendly dates.

### The Boundary Check

Does this violate our rules? **No.**
The Adapter is still stateless regarding *inventory*. It is simply acting as a highly configurable router and translator. It reads the JSON, reads the Crosswalk DB, formats the data, and throws it over the fence to the Ledger.

---

## database schema for the adapter_crosswalks table and the Dead Letter Queue (DLQ) table

### 1. The Crosswalk Registry (Relational Table)

This table acts as the "External Dictionary" mentioned in your JSON contract. It’s designed to be indexed for high-speed lookups during the mapping phase.

**Table Name:** `adapter_crosswalks`

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key. |
| `namespace` | String | Groups mappings (e.g., `dhis2_nodes`, `odk_commodities`). |
| `source_value` | String | The "messy" value from the external app (e.g., `act_80`). |
| `internal_id` | String | The clean ID for your Ledger (e.g., `PROD-AL-01`). |
| `is_active` | Boolean | Allows deactivating a mapping without deleting history. |
| `metadata` | JSONB | **Creative addition:** Store UOM defaults or pack sizes specific to this source. |

---

### 2. The Dead Letter Queue (DLQ) Strategy

In professional systems, we assume **something will break.** The DLQ is where "Invalid" or "Unmapped" payloads go to wait for human intervention.

**The Workflow:**

1. **The Failure:** The Adapter tries to map `facility_code: "999"` but finds no entry in `adapter_crosswalks`.
2. **The Park:** Instead of crashing, the Adapter saves the entire original JSON payload to the `dead_letter_queue` table.
3. **The Alert:** An admin is notified: *"New unmapped facility code '999' found."*
4. **The Resolution:** The admin adds the mapping to the `adapter_crosswalks` table and clicks **"Reprocess"** on the DLQ entry.
5. **The Success:** The Adapter pulls the payload from the DLQ, maps it successfully (now that the entry exists), and pushes it to the Ledger.

**Table Name:** `dead_letter_queue`

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key. |
| `raw_payload` | JSONB | The original, unmodified data from the source app. |
| `error_type` | String | `UNMAPPED_NODE`, `UNMAPPED_COMMODITY`, `MALFORMED_JSON`. |
| `failed_value` | String | The specific string that caused the mapping failure. |
| `status` | String | `PENDING`, `REPROCESSED`, `IGNORED`. |
| `attempts` | Integer | Number of times reprocessing has been tried. |

---

### 3. "Creativity & Simplicity": The Contextual Metadata Hook

Here is a "pro-tip" strategy often used in global health systems (like mSupply): **Source-Specific Rules.**

Sometimes, Source A sends "AL 6x1" where a "unit" is a **tablet**, but Source B sends "AL 6x1" where a "unit" is a **full treatment course**.

* Instead of hardcoding this in logic, you store this "Factor" in the `metadata` column of the `adapter_crosswalks` table.
* **The Logic:** When mapping, the Adapter asks: *"Is there a `multiplier` in the crosswalk metadata for this item?"* If yes, multiply the quantity before sending it to the Ledger.
* **Result:** You handle two different reporting behaviors with the **same** code and **different** data.

---

### 4. The Integration Audit Trail (Run Logs)

Every time the Adapter wakes up to process a payload, it must leave a "breadcrumb." This is not just for debugging; it’s for **accountability**.

**Artifact:** `adapter_logs`

* **Purpose:** A permanent, immutable record of every attempt to map data.
* **Fields:**
* `run_id`: UUID.
* `contract_version_id`: Link to the specific version of the mapping used.
* `payload_id`: Link to the raw ingestion record.
* `status`: `SUCCESS`, `FAILED_MAPPING` (stopped in Adapter), `FAILED_DESTINATION` (rejected by Ledger).
* `ledger_response`: The JSON response/error from the Ledger module.
* `execution_time_ms`: Performance tracking.

> **Architect's Note:** This log allows you to answer the question: *"Why did this facility’s stock not update on Tuesday?"* You can find the log, see the mapping used, and see the Ledger's specific reason for rejection.

---

### 5. The Dead Letter Management Flow (Replay & Dry-Runs)

When an admin "fixes" a mapping in the DLQ, they need a safe way to test it.

**The Replay State Machine:**

1. **PENDING:** The record is stuck (e.g., Unmapped Node).
2. **DRY_RUN:** The Admin clicks "Test." The Adapter runs the mapping and sends it to the Ledger with a `dry_run=true` flag.
* **Result A (Fail):** Admin sees the error, stays in PENDING.
* **Result B (Success):** Admin sees "Valid Mapping," transitions to READY.


3. **APPLIED:** The Admin clicks "Submit." The Adapter sends the real command (`dry_run=false`). The DLQ record moves to `COMPLETED`.

**The Ledger Interface:**
The Ledger must support a `POST /commands?dry_run=true` endpoint. In this mode, the Ledger performs **all validations** (Negative stock check, UOM check, Schema check) but **rolls back the transaction** before writing to the Event Store. It returns a `200 OK` or `400 Error`.

---

### 6. Mapping Lifecycle & Governance

Your draft for the lifecycle is excellent. Let’s polish the rules to ensure the "Historical Truth" is never broken.

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

To be "Production Grade," your Adapter module now owns:

1. **The Registry:** `mapping_contracts` (The Rules).
2. **The Crosswalk:** `adapter_crosswalks` (The Dictionary).
3. **The Buffer:** `dead_letter_queue` (The Hospital for bad data).
4. **The Audit:** `adapter_logs` (The History).
5. **The Interface:** A standard way to call the Ledger with a `dry_run` flag.
