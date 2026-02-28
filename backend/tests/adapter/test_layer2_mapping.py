import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import uuid

from app.adapter.models.engine import AdapterInbox, InboxStatus, MappingContract, ContractStatus
from app.adapter.worker import AdapterWorker

@pytest.fixture
def mock_contract_dsl():
    return {
        "contract_info": {
            "id": "hf_receipt_902",
            "version": "v1",
            "status": "ACTIVE",
            "source_system": "datarun-lmis"
        },
        "ingress": {
            "trigger_path": "body.event_type",
            "trigger_value": "RECEIPT"
        },
        "destination": {
            "method": "POST",
            "url": "http://example-ledger.test/ingest"
        },
        "dictionaries": {
            "external": {
                "node_map": {
                    "namespace": "hf_to_dhis2",
                    "on_unmapped": "DLQ"
                }
            }
        },
        "processing_pipelines": {
            "basic_pass": [
                {
                    "op": "multiply",
                    "type": "math",
                    "value": 10
                }
            ]
        },
        "output_template": [
            {
                "envelope": {
                    "source_event_id": {"path": "id"},
                    "timestamp": {"path": "created_at"}
                },
                "static_injection": {},
                "global_fields": {},
                "iterator": {
                    "path": "$.items[*]",
                    "fields": {
                        "amount": {"path": "amount", "pipeline": "basic_pass"},
                        "code": {"path": "product_code"}
                    }
                }
            }
        ]
    }

@pytest.mark.asyncio
async def test_layer2_mapping_success(db_session: AsyncSession, mock_contract_dsl):
    # Setup Contract
    contract_id = f"test_contract_{uuid.uuid4()}"
    contract = MappingContract(
        id=contract_id,
        version="v1",
        status=ContractStatus.ACTIVE,
        dsl_config=mock_contract_dsl
    )
    db_session.add(contract)
    
    # Setup Inbox (RECEIVED)
    inbox = AdapterInbox(
        source_system="test_system",
        mapping_id=contract_id,
        mapping_version="v1",
        payload={
             "id": "event_123",
             "created_at": "2024-01-01T00:00:00Z",
             "qty": 5,
             "items": [
                 {"amount": 5, "product_code": "A1"}
             ]
        },
        status=InboxStatus.RECEIVED
    )
    db_session.add(inbox)
    await db_session.commit()
    
    # ------------------
    # Execute Layer 2
    # ------------------
    processed_count = await AdapterWorker.process_mapping_batch(batch_size=10, session=db_session)
    assert processed_count == 1
    
    # Assert DB State
    await db_session.refresh(inbox)
    assert inbox.status == InboxStatus.MAPPED, f"Expected MAPPED, got {inbox.status}: {inbox.error_message}"
    assert inbox.mapped_payload is not None
    assert inbox.mapped_payload[0]["amount"] == 50

@pytest.mark.asyncio
async def test_layer2_mapping_invalid_contract_dlq(db_session: AsyncSession):
    # Setup Inbox (RECEIVED) with fake contract
    inbox = AdapterInbox(
        source_system="test_system",
        mapping_id="DOES_NOT_EXIST",
        mapping_version="v99",
        payload={"qty": 5},
        status=InboxStatus.RECEIVED
    )
    db_session.add(inbox)
    await db_session.commit()
    
    # Execute Layer 2
    processed_count = await AdapterWorker.process_mapping_batch(batch_size=10, session=db_session)
    assert processed_count == 1
    
    # Assert DB State - Must go to DLQ
    await db_session.refresh(inbox)
    assert inbox.status == InboxStatus.DLQ
    assert "not found" in inbox.error_message
    assert inbox.mapped_payload is None
