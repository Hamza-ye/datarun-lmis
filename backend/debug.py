import asyncio

from app.adapter.engine.mapper import MapperEngine
from app.adapter.schemas.dsl import MappingContractDSL

DUMMY_DSL = {
    "contract_info": {
        "id": "worker_test_contract",
        "version": "1.0.0",
        "status": "ACTIVE",
        "source_system": "test_system"
    },
    "ingress": {
        "description": "Any test payload",
        "trigger_path": "$.test_flag",
        "trigger_value": True
    },
    "destination": {
        "url": "http://localhost:8000/api/ledger/commands",
        "method": "POST"
    },
    "dictionaries": {
        "inline": {
            "type_map": {
                "map": {"adjustment": "ADJUSTMENT"},
                "default": "RECEIPT",
                "on_unmapped": "USE_DEFAULT"
            }
        }
    },
    "processing_pipelines": {},
    "output_template": [
        {
            "envelope": {
                "source_event_id": {"path": "$.id"},
                "timestamp": {"path": "$.occurred_at"}
            },
            "static_injection": {
                "command_type": "RECEIPT"
            },
            "global_fields": {
                "node_id": {"path": "$.facility"},
                "transaction_type": {"path": "$.type", "dictionary": "inline:type_map"}
            },
            "iterator": {
                "path": "$.items",
                "fields": {
                    "item_id": {"path": "$.item_code"},
                    "quantity": {"path": "$.qty"}
                }
            }
        }
    ]
}

payload = {
    "id": "evt_101",
    "occurred_at": "2026-02-23T00:00:00Z",
    "facility": "NODE-1",
    "type": "adjustment",
    "test_flag": True,
    "items": [
        {"item_code": "ITEM-1", "qty": 50}
    ]
}

class DummySession:
    async def execute(self, stmt):
        class Result:
            def scalars(self):
                class Scalars:
                    def first(self):
                        return None
                return Scalars()
        return Result()

async def debug():
    try:
        dsl = MappingContractDSL(**DUMMY_DSL)
        print("DSL parsed successfully.")
        
        cmds = await MapperEngine.run(DummySession(), payload, dsl)
        print(f"Engine Success: {cmds}")
    except Exception:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug())
