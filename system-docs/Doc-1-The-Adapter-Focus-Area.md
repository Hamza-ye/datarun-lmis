### The Strategy: The Asynchronous "Store, Cleanse & Forward" Pipeline

We are building a truly decoupled system, **the Adapter and the Ledger share zero database tables.** They do not share a "Master Data" database, or shared module db the ledger uses. They are completely blind to each other’s internal states.

The Adapter is a black box that takes a payload in, applies its own isolated rules, fires a generic HTTP request into the void, and logs whatever comes back.

### The Two Separate Universes

#### Universe A: The Adapter (The Self-Sufficient Engine)

The Adapter has its own configuration database. It does not query the Ledger. When you configure the Adapter, you populate its `adapter_crosswalks` table.

If the user wants to map a 50-pack of Paracetamol, they log into the **Adapter's UI** and configure:

* **Source System Code:** `PARAM-BOX-50`
* **Destination System Code:** `PARAM-01`
* **Transform Factor:** `50`

The Adapter stores this in *its own* database tables. When a message arrives, it does the math, builds the JSON command (`{ "item_id": "PARAM-01", "quantity": 100 }`), and POSTs it to the Ledger's URL.

#### Universe B: The Ledger (The Strict Receiver)

The Ledger has its own isolated `commodity_registry`. It only contains the pure definition of an item.

* `PARAM-01` | Paracetamol 500mg | TABLET | ACTIVE

The Ledger knows absolutely nothing about `PARAM-BOX-50`.

---

### The Error Correction Loop (The User's Job, High level pesudo)

Because they are perfectly decoupled, the adapter relies on **Contracts and Dead Letter Queues (DLQs)**. Here is the exact flow you described:

1. **The Mistake:** A new clinic uses a new app version and sends a code the Adapter has never seen: `PARAM-BOX-200`.
2. **Adapter Tries its Best:** The Adapter checks its internal crosswalk. It doesn't find `PARAM-BOX-200`.
3. **Adapter Fallback:** Based on your config (`"on_unmapped": "PASS_THROUGH"`), the Adapter shrugs, skips the math pipeline, and sends `{ "item_id": "PARAM-BOX-200", "quantity": 1 }` to the Ledger.
4. **Ledger Rejects:** The Ledger looks up `PARAM-BOX-200` in its own `commodity_registry`. It doesn't exist. The Ledger immediately responds to the HTTP request with:
`400 Bad Request: "Unknown item_id: PARAM-BOX-200"`.
5. **Adapter Logs It:** The Adapter catches the `400 Bad Request`. It writes the original payload and the Ledger's error message into the Adapter's Error Log / Dead Letter Queue.
6. **The User Fixes It:** * The system administrator checks the Adapter's Error Log.
* They see the Ledger rejected `PARAM-BOX-200`.
* They open the Adapter's mapping config.
* They add a new crosswalk rule: `PARAM-BOX-200`  `PARAM-01` (Transform Factor: 200).
* They click **"Replay Failed Message"** in the Adapter.


7. **Success:** The Adapter processes it again. This time it does the math, sends `{ "item_id": "PARAM-01", "quantity": 200 }`, and the Ledger responds `201 Created`.

---

### Why this is the Ultimate Architecture

By enforcing this strict "fire and log" boundary:

* We can swap out the Ledger entirely in 5 years, and the Adapter won't need a single line of code changed. You just point the URL somewhere else.
* We can have 10 different Adapters (one for ODK, one for DHIS2, one for a custom Web App), and the Ledger doesn't care. It just sits there evaluating perfectly mapped JSON commands.

We have successfully walled off the Adapter. It is now a perfect, self-sufficient transformation engine.

---

### The Engine: Asynchronous "Store, Cleanse & Forward"

Instead of writing hard-coded `if/else` statements in your Adapter code, we give the Adapter a **Transformation DSL (Domain Specific Language)** in JSON.

The pipeline does four asynchronous things:

1. **Receive & Store (The Inbox):** Receive the raw data, validate its basic structure, save it to the `adapter_inbox`, and immediately return a `202 Accepted` to the source.
2. **Extract:** A background worker pulls the raw data from the Inbox using JSONPath.
3. **Cleanse (Crosswalks):** Run the messy data through defined normalization rules and dictionaries.
4. **Emit & Forward:** Construct the final Payload based on the configuration and POST it to the destination URL.

---

### The JSON Mapping Schema (The "A-to-B" Contract)

Here is how you model the Adapter's configuration to handle variations like `ACT-80` and format the data exactly how the destination wants it. This schema separates the **Rules** (JSON) from the **Data** (Crosswalk DB).

## 1. Top-Level Structure

The schema is divided into **Environment** (Who am I?), **Ingress** (When do I run?), **Resources** (What do I know?), and **Execution** (How do I transform?).

| Key | Type | Requirement | Description |
| --- | --- | --- | --- |
| `contract_info` | `Object` | **Required** | Metadata identifying the mapping version and status. |
| `ingress` | `Object` | **Required** | Logic used to route incoming payloads to this contract. |
| `destination` | `Object` | **Required** | The HTTP endpoint and method where the Adapter will forward the payload. |
| `dry_run` | `Object` | Optional | Configuration for injecting the dry-run flag into payloads. |
| `dictionaries` | `Object` | Optional | Declarations of external DB lookups or internal static maps. |
| `processing_pipelines` | `Object` | Optional | Named sequences of atomic data operations. |
| `output_template` | `Array` | **Required** | The blueprint for one or more output commands. |

---

## 2. Resource & Error Definitions

### `dictionaries` Options

Dictionaries are used to translate source values to internal IDs.

* **`external`**: Hits the `adapter_crosswalks` table. Requires a `namespace`.
* **`inline`**: A simple key-value pair stored directly in the JSON.

#### `on_unmapped` (Enum)

This defines the behavior when a value (e.g., a Team ID) is not found in the dictionary.

1. **`DLQ` (Dead Letter Queue):** Stop processing, log the error, and move the entire payload to a manual review table.
2. **`PASS_THROUGH`:** Use the original raw value from the source. (Risky, but useful for your "Campaign Team" fallback).
3. **`USE_DEFAULT`:** Use a predefined `default` value provided in the config.
4. **`REJECT`:** Throw a hard 400 error back to the source system immediately.

---

## 3. The Processing Engine (`processing_pipelines`)

A pipeline is an **ordered array** of operations. Each operation (`op`) takes an input and passes its output to the next step.

### Supported Operations (`op`)

| Op Type | Parameters | Example/Behavior |
| --- | --- | --- |
| **`cast`** | `type`: `INT, FLOAT, STR, BOOL` | Converts data types. |
| **`multiply`** | `factor_from` OR `value` | Multiplies by a fixed number or a value from a dictionary's metadata. |
| **`add`** | `value_from` OR `value` | Mathematical addition (useful for offsets). |
| **`parse_date`** | `from`: e.g., `DD-MM-YYYY` | Converts a string into a standard Date Object. |
| **`format_date`** | `to`: e.g., `YYYY-MM-DD` | Outputs a Date Object into a specific string format. |
| **`regex`** | `pattern`, `replacement` | Advanced string manipulation. |
| **`case`** | `to`: `UPPER` or `LOWER` | Normalizes string casing. |

---

## 4. Execution Blueprint (`output_template`)

This is where you define the shape of the JSON you are sending to the Ledger.

### Field Mapping Logic

Every field within the template can be defined in one of three ways:

1. **Direct Path:** `{"path": "$.source.field"}`
2. **Dictionary Lookup:** `{"path": "$.source.field", "dictionary": "external:name"}`
3. **Pipeline Processing:** `{"path": "$.source.field", "pipeline": "name"}`

### The Iterator (The Loop)

* **`path`**: The JsonPath to the array (e.g., `$.items[*]`).
* **`fields`**: A sub-template applied to every object in that array.

---

## 5. Formal Schema Example (The "Code-Ready" Version)

```json
{
  "contract_info": { "id": "string", "version": "string", "status": "ACTIVE|DRAFT", "source_system": "string" },
  
  "ingress": { 
    "description": "Logic used to route incoming payloads to this contract",
    "trigger_path": "JsonPath", 
    "trigger_value": "any" 
  },

  "destination": {
    "url": "https://api.internal/ledger/v1/commands",
    "method": "POST"
  },

  "dry_run": {
    "supported": true,
    "inject_path": "$.metadata.is_dry_run"
  },

  "dictionaries": {
    "external": {
      "description": "Pointers to the DB for large, frequently changing lists",
      "name": { "namespace": "string", "on_unmapped": "DLQ|PASS_THROUGH|REJECT" }
    },
    "inline": {
      "description": "Simple key-value pairs stored directly in the JSON",
      "name": { "map": { "key": "value" }, "default": "any", "on_unmapped": "USE_DEFAULT|DLQ" }
    }
  },

  "processing_pipelines": {
    "pipeline_name": [
      { "op": "cast", "type": "INTEGER" },
      { "op": "multiply", "factor_from": "dictionary.dict_name.metadata.key" }
    ]
  },

  "output_template": [
    {
      "condition": { "path": "JsonPath", "equals": "any" },
      "envelope": { "field_name": { "path": "JsonPath" } },
      "static_injection": { "field_name": "constant_value" },
      "global_fields": { "field_name": { "path": "JsonPath", "dictionary": "..." } },
      "iterator": {
        "path": "JsonPath",
        "fields": { "field_name": { "path": "JsonPath", "pipeline": "..." } }
      }
    }
  ]
}

```
**[Check out a sample source events and their mapping Examples](/system-docs/adapter-source-events-examples/about_samples.md)**

### Why this DSL Design is Battle-Tested

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

In professional systems, we assume **something will break.** The DLQ is where "Invalid" or "Unmapped" payloads go to wait for human intervention without blocking the rest of the queue (as outlined in the **Error Correction Loop** earlier).

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

### 5. Advanced Dead Letter Management (Replay State Machine)

As outlined in the "Error Correction Loop" above, when an admin "fixes" a mapping in the DLQ, they need a safe way to test it. This relies on the Adapter injecting the `dry_run` flag defined in the configuration. The Adapter doesn't care what the Destination does with the flag—it just injects it to the specified JSON path and fires it off.

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
