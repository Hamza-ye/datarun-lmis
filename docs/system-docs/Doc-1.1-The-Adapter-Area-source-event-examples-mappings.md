## Mapping Examples and source data samples
supply nodes can be of types MU WH, HF, TEAM (mobile teams during temporary periodic campaigns), MOBILE WH (temporary WHs during campaigns) as a supply node.

### [hf_receipt_902](./adapter-source-events-examples/hf_receipt_902_example.json)

* from is mapped by crosswalking that mapps `team` which is the team uid to the MU supply node uid, or fall back to incoming `team` it's a campaign team, it might be rejected by ledger if not presents there, adapter have no business in this except it logs what the ledger will say. 
* the incoming line events doesn't specify UOMs, but they are at the base unit.

**mapping sample:**
```json
{
  "contract_info": {
    "id": "hf_receipt_902",
    "version": "1.0",
    "status": "ACTIVE",
    "source_system": "commcare"
  },
  "ingress": {
    "trigger_path": "$.form",
    "trigger_value": "z0xxGWenaov"
  },
  "destination": {
    "url": "https://api.internal/ledger/v1/commands",
    "method": "POST"
  },
  "dictionaries": {
    "external": {
      "node_map": { 
        "namespace": "mu_team_to_node", 
        "on_unmapped": "PASS_THROUGH" 
      },
      "item_map": { 
        "namespace": "wh_category_to_item", 
        "on_unmapped": "DLQ" 
      }
    }
  },
  "processing_pipelines": {
    "calculate_base_quantity": [
      { "op": "cast", "type": "INTEGER" },
      { "op": "multiply", "factor_from": "dictionary.item_map.metadata.transform_factor" }
    ]
  },
  "output_template": [
    {
      "envelope": {
        "source_event_id": { "path": "$.uid" },
        "timestamp": { "path": "$.formData.invoice.DateOnly" }
      },
      "static_injection": { "command_type": "RECEIPT" },
      "global_fields": {
        "target_node": { "path": "$.team", "dictionary": "external:node_map" }
      },
      "iterator": {
        "path": "$.formData.invoice.invoiceDetails[*]",
        "fields": {
          "item_id": { "path": "$.wh_category", "dictionary": "external:item_map" },
          "quantity": { "path": "$.wh_quantity", "pipeline": "calculate_base_quantity" }
        }
      }
    }
  ]
}
```

---

### **[wh_stocktake_901](.//adapter-source-events-examples/wh_stocktake_901_example%20(for%20MU%20stocktakes).json)**

* the `orgunit` is the stocktake subject.
* the incoming line events doesn't specify UOMs, but they are at the base unit, except for RDT wich is in packs of 25 units.
This handles the periodic counts, specifically using the orgUnit as the subject node.
```json
{
  "contract_info": {
    "id": "wh_stocktake_901",
    "version": "1.0",
    "status": "ACTIVE",
    "source_system": "commcare"
  },
  "ingress": {
    "trigger_path": "$.form",
    "trigger_value": "QBVcGxiko2q"
  },
  "destination": {
    "url": "https://api.internal/ledger/v1/commands",
    "method": "POST"
  },
  "dictionaries": {
    "external": {
      "node_map": { "namespace": "orgunit_to_node", "on_unmapped": "DLQ" },
      "item_map": { "namespace": "wh_category_to_item", "on_unmapped": "DLQ" }
    }
  },
  "processing_pipelines": {
    "calculate_base_quantity": [
      { "op": "cast", "type": "INTEGER" },
      { "op": "multiply", "factor_from": "dictionary.item_map.metadata.transform_factor" }
    ]
  },
  "output_template": [
    {
      "envelope": {
        "source_event_id": { "path": "$.uid" },
        "timestamp": { "path": "$.formData.invoice.DateOnly" }
      },
      "static_injection": { "command_type": "STOCK_COUNT" },
      "global_fields": {
        "target_node": { "path": "$.orgUnit", "dictionary": "external:node_map" }
      },
      "iterator": {
        "path": "$.formData.invoice.invoiceDetails[*]",
        "fields": {
          "item_id": { "path": "$.wh_category", "dictionary": "external:item_map" },
          "quantity": { "path": "$.wh_quantity", "pipeline": "calculate_base_quantity" }
        }
      }
    }
  ]
}
```
