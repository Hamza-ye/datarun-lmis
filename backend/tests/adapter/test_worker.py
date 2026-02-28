import pytest
from sqlalchemy.future import select

from app.adapter.models.engine import AdapterInbox, InboxStatus, MappingContract, ContractStatus
from app.adapter.worker import AdapterWorker
from unittest.mock import patch
import httpx

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
        "trigger_value": "True"
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
        },
        "external": {}
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
                "node_id": {"path": "$.facility"}
            },
            "iterator": {
                "path": "$.items[*]",
                "fields": {
                    "item_id": {"path": "$.item_code"},
                    "quantity": {"path": "$.qty"}
                }
            }
        }
    ]
}

@pytest.mark.asyncio
@patch('httpx.AsyncClient.request')
async def test_worker_process_batch_happy_path(mock_request, db_session):
    mock_request.return_value = httpx.Response(202, text="OK")
    
    # Setup test contract
    contract = MappingContract(
        id="worker_test_contract",
        version="1.0.0",
        status=ContractStatus.ACTIVE,
        dsl_config=DUMMY_DSL
    )
    
    inbox_valid = AdapterInbox(
        source_system="test_system",
        mapping_id="worker_test_contract",
        mapping_version="1.0.0",
        payload={
            "id": "evt_101",
            "occurred_at": "2026-02-23T00:00:00Z",
            "facility": "NODE-1",
            "type": "adjustment",
            "test_flag": "True",
            "items": [
                {"item_code": "ITEM-1", "qty": 50}
            ]
        },
        status=InboxStatus.RECEIVED
    )
    
    db_session.add(contract)
    db_session.add(inbox_valid)
    await db_session.commit()
    
    valid_id = inbox_valid.id
    
    # 1. Execute the background batch processor WITH explicit session
    processed_count = await AdapterWorker.process_batch(batch_size=10, session=db_session)
    
    assert processed_count == 1
    
    # 2. Assert Valid Item Forwarded
    stmt_valid = select(AdapterInbox).where(AdapterInbox.id == valid_id)
    result_valid = await db_session.execute(stmt_valid)
    valid_record = result_valid.scalars().first()
    
    assert valid_record.status == InboxStatus.FORWARDED

@pytest.mark.asyncio
async def test_worker_process_batch_dlq(db_session):
    # Setup test contract
    contract = MappingContract(
        id="worker_test_contract",
        version="1.0.0",
        status=ContractStatus.ACTIVE,
        dsl_config=DUMMY_DSL
    )
    
    inbox_bad = AdapterInbox(
        source_system="test_system",
        mapping_id="worker_test_contract",
        mapping_version="1.0.0",
        payload={
            "test_flag": "True",
            # We omit the 'id' which is explicitly required by the DSL envelope.
            # This causes the Engine to fail extraction/validation and route the payload to DLQ/Error.
            "items": [
                {"qty": 10}
            ]
        },
        status=InboxStatus.RECEIVED
    )
    
    db_session.add(contract)
    db_session.add(inbox_bad)
    await db_session.commit()
    
    bad_id = inbox_bad.id

    await AdapterWorker.process_batch(batch_size=10, session=db_session)
    
    # Check if the bad item threw an Exception and went to DLQ
    stmt_bad = select(AdapterInbox).where(AdapterInbox.id == bad_id)
    result_bad = await db_session.execute(stmt_bad)
    bad_record = result_bad.scalars().first()
    
    # Without qty/facility/etc the mapper raises a KeyError/ValueError
    assert bad_record.status in [InboxStatus.DESTINATION_REJECTED, InboxStatus.DLQ]
    assert bad_record.error_message is not None
    assert len(bad_record.error_message) > 0
