# Mapping DSL Reference

## Overview

Instead of hard-coded `if/else` statements, the Adapter uses a **Transformation DSL** in JSON. This separates the **Rules** (JSON contract) from the **Data** (Crosswalk DB).

## Top-Level Schema

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `contract_info` | Object | **Yes** | Metadata: id, version, status, source_system |
| `ingress` | Object | **Yes** | Routing logic: `trigger_path` + `trigger_value` |
| `destination` | Object | **Yes** | HTTP endpoint and method for forwarding |
| `dry_run` | Object | No | Configuration for injecting dry-run flag |
| `dictionaries` | Object | No | External DB lookups or inline static maps |
| `processing_pipelines` | Object | No | Named sequences of atomic data operations |
| `output_template` | Array | **Yes** | Blueprint for output command(s) |

## Dictionaries

Dictionaries translate source values to internal IDs.

### External Dictionaries
Hit the `adapter_crosswalks` table. Require a `namespace`.

```json
"external": {
  "node_map": { "namespace": "mu_team_to_node", "on_unmapped": "PASS_THROUGH" },
  "item_map": { "namespace": "wh_category_to_item", "on_unmapped": "DLQ" }
}
```

### Inline Dictionaries
Simple key-value pairs stored directly in the JSON contract.

```json
"inline": {
  "priority": { "map": { "high": "1", "low": "3" }, "default": "2", "on_unmapped": "USE_DEFAULT" }
}
```

### `on_unmapped` Strategies (**Required** on every dictionary)

> **Invariant:** Every dictionary declaration must include an `on_unmapped` strategy. The DSL engine must reject contracts with missing `on_unmapped` at validation time, not at runtime. Undefined behaviour on unmapped values is how empty commands reach the Ledger.

| Strategy | Behavior |
| --- | --- |
| `DLQ` | Stop processing, log error, move payload to DLQ for manual review |
| `PASS_THROUGH` | Use the original raw value (risky but useful for campaign team fallback) |
| `USE_DEFAULT` | Use a predefined `default` value from the config |
| `REJECT` | Throw a hard 400 error back to the source system |

## Processing Pipelines

A pipeline is an **ordered array** of operations. Each operation passes its output to the next step.

### Supported Operations

| Op | Parameters | Behavior |
| --- | --- | --- |
| `cast` | `type`: `INT, FLOAT, STR, BOOL` | Convert data types |
| `multiply` | `factor_from` OR `value` | Multiply by fixed number or dictionary metadata value |
| `add` | `value_from` OR `value` | Mathematical addition |
| `parse_date` | `from`: e.g., `DD-MM-YYYY` | Convert string to Date Object |
| `format_date` | `to`: e.g., `YYYY-MM-DD` | Output Date Object as string |
| `regex` | `pattern`, `replacement` | Advanced string manipulation |
| `case` | `to`: `UPPER` or `LOWER` | Normalize string casing |

## Output Template

Every field in the template can be defined in one of three ways:

1. **Direct Path:** `{"path": "$.source.field"}`
2. **Dictionary Lookup:** `{"path": "$.source.field", "dictionary": "external:name"}`
3. **Pipeline Processing:** `{"path": "$.source.field", "pipeline": "name"}`

### The Iterator (Array Processing)

- `path`: The JSONPath to the array (e.g., `$.items[*]`)
- `fields`: A sub-template applied to every object in that array

## Full Schema Example

```json
{
  "contract_info": { "id": "string", "version": "string", "status": "ACTIVE|DRAFT", "source_system": "string" },
  "ingress": { "trigger_path": "JsonPath", "trigger_value": "any" },
  "destination": { "url": "https://api.internal/ledger/v1/commands", "method": "POST" },
  "dry_run": { "supported": true, "inject_path": "$.metadata.is_dry_run" },
  "dictionaries": {
    "external": { "name": { "namespace": "string", "on_unmapped": "DLQ|PASS_THROUGH|REJECT" } },
    "inline": { "name": { "map": { "key": "value" }, "default": "any", "on_unmapped": "USE_DEFAULT|DLQ" } }
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

## Multi-Command Output (One Payload → Multiple Commands)

A single incoming payload can produce **multiple** Ledger commands when:
- Multiple `output_template` entries match via `condition` blocks (e.g., receipts and issues in the same form)
- The `iterator` processes an array where each element generates a separate command

### Atomicity Rule

The payload is the **atomic unit** of processing:
- **Mapping phase:** If any line or template fails mapping (unmapped crosswalk, pipeline error), the **entire payload** goes to DLQ. No partial mapping is forwarded.
- **Forwarding phase:** Each command is POSTed to the Ledger individually and logged in `adapter_egress_logs`.
- **Replay:** The entire payload is reprocessed. The Ledger's idempotency guard deduplicates commands that were already forwarded successfully.

### Per-Command `source_event_id` Derivation

To ensure idempotent replay, each command generated from a single payload must have a **unique, deterministic** `source_event_id`:

```
{payload_source_event_id}:{template_index}:{iterator_index}
```

- `payload_source_event_id` — the incoming payload's identity (e.g., `submission.uid`)
- `template_index` — which `output_template` entry matched (0-based)
- `iterator_index` — which array element produced this command (0 if no iterator)

This ensures that replaying a payload regenerates the **exact same set of `source_event_id` values**, and the Ledger's idempotency guard naturally deduplicates already-processed commands.

> **Invariant:** Every command leaving the Adapter must carry a unique, deterministic `source_event_id`. If two commands share the same `source_event_id`, the Ledger will treat the second as a duplicate and discard it.

## Design Rationale

1. **Pre-Processing Pipeline:** Handles typos (`ACT-80`, `act80`, `act_80`) via `[TRIM, UPPERCASE, REMOVE_SPECIAL_CHARS]` — all become `ACT80`.
2. **External Dictionaries:** Ministry adds 50 clinics → bulk-upload DB rows. JSON contract never changes.
3. **Conditional Routing:** One source form can map to both Receipts and Issues via `condition` blocks.
4. **Static Injection:** Adapter doesn't know what `STOCK_COUNT` means. It only injects configured key-value pairs.
5. **Date Normalization:** Converts messy field dates (`22-02-2026`, `02/22/26`) to ISO-8601 `YYYY-MM-DD`.

## Related Docs

- **Working examples:** See [Test Fixtures](test-fixtures/)
- **Contract lifecycle:** See [Mapping Contract Lifecycle](mapping-contract-lifecycle.md)
- **Atomicity & replay:** See [DLQ and Replay](dlq-and-replay.md)
