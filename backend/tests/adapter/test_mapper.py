import pytest
import json
from app.adapter.schemas.dsl import MappingContractDSL
from app.adapter.engine.mapper import MapperEngine
from app.adapter.models.engine import AdapterCrosswalk
from app.adapter.engine.pipeline_runner import PipelineRunner
from app.adapter.schemas.dsl import PipelineOp

# Basic wh_stocktake_901 Payload for Context Testing
MOCK_PAYLOAD = {
  "form": "QBVcGxiko2q",
  "uid": "event_uuid_101",
  "orgUnit": "WH_KAMPALA_01",
  "formData": {
    "invoice": {
      "DateOnly": "2026-03-01T12:00:00Z",
      "invoiceDetails": [
        {"wh_category": "MRDT25", "wh_quantity": "41"},
        {"wh_category": "ACT80", "wh_quantity": "99"}
      ]
    }
  }
}

MOCK_CONTRACT_DSL = {
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
        "node_id": { "path": "$.orgUnit", "dictionary": "external:node_map" }
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

def test_pipeline_runner_math():
    """Validates the basic casting and multiplication pipelining"""
    ops = [
        PipelineOp(op="cast", type="INTEGER"),
        PipelineOp(op="multiply", factor_from="dictionary.item_map.metadata.transform_factor")
    ]
    
    # Simulate an MRDT25 calculation (where context returns factor 25)
    ctx_25 = {"item_map": {"metadata": {"transform_factor": 25}}}
    
    # Pass in string '41' to simulate raw JSON format
    result1 = PipelineRunner.execute("41", ops, dictionary_lookup_result=ctx_25)
    
    assert result1 == 1025
    assert isinstance(result1, int)
    
    # Simulate an ACT80 calculation (where context has no factor, falls back to * 1)
    ctx_1 = {"item_map": {"metadata": {}}}
    result2 = PipelineRunner.execute("99", ops, dictionary_lookup_result=ctx_1)
    assert result2 == 99

@pytest.mark.asyncio
async def test_mapper_engine_full_run(db_session):
    """
    Simulates a full run of the Mapper Engine utilizing the JSON DSL and Database lookups.
    """
    
    # 1. Seed Dictionary
    db_session.add(AdapterCrosswalk(
        namespace="orgunit_to_node", source_value="WH_KAMPALA_01", internal_id="NK_01"
    ))
    db_session.add(AdapterCrosswalk(
        namespace="wh_category_to_item", source_value="MRDT25", internal_id="RDT_SHARED", metadata_json={"transform_factor": 25}
    ))
    db_session.add(AdapterCrosswalk(
        namespace="wh_category_to_item", source_value="ACT80", internal_id="ACT_SHARED"
    ))
    await db_session.flush()

    # 2. Run Engine
    contract = MappingContractDSL(**MOCK_CONTRACT_DSL)
    results = await MapperEngine.run(db_session, MOCK_PAYLOAD, contract)
    
    # 3. Assertions
    assert len(results) == 2
    
    # RDT Item (Transforms 41 -> 1025 Base Units)
    rdt_command = results[0]
    assert rdt_command["source_event_id"] == "event_uuid_101_0"
    assert rdt_command["transaction_type"] == "STOCK_COUNT"
    assert rdt_command["node_id"] == "NK_01"
    assert rdt_command["item_id"] == "RDT_SHARED"
    assert rdt_command["quantity"] == 1025  # The pipeline worked!
    
    # ACT Item (Transforms 99 -> 99 Base Units)
    act_command = results[1]
    assert act_command["source_event_id"] == "event_uuid_101_1"
    assert act_command["item_id"] == "ACT_SHARED"
    assert act_command["quantity"] == 99
    
@pytest.mark.asyncio
async def test_dlq_trigger_on_unmapped(db_session):
    """
    If a source value is not in the crosswalk and the DSL dictates DLQ,
    it should throw a DLQ Trigger exception to park the payload.
    """
    
    # Seed the Node mapping so it gets past the global extraction
    db_session.add(AdapterCrosswalk(
        namespace="orgunit_to_node", source_value="WH_KAMPALA_01", internal_id="NK_01"
    ))
    await db_session.flush()

    bad_payload = MOCK_PAYLOAD.copy()
    bad_payload["formData"]["invoice"]["invoiceDetails"] = [
        {"wh_category": "UNKNOWN_DRUG", "wh_quantity": "10"}
    ]
    
    contract = MappingContractDSL(**MOCK_CONTRACT_DSL)
    
    with pytest.raises(ValueError) as excinfo:
        await MapperEngine.run(db_session, bad_payload, contract)
        
    assert str(excinfo.value).startswith("DLQ_TRIGGER")
    assert "UNKNOWN_DRUG" in str(excinfo.value)
