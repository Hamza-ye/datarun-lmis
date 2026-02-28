import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import uuid
from httpx import Response
from unittest.mock import patch

from app.adapter.models.engine import AdapterInbox, InboxStatus, MappingContract, ContractStatus, AdapterEgressLogs
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
        "processing_pipelines": {},
        "output_template": [
            {
                "envelope": {
                    "source_event_id": {"path": "id"},
                    "timestamp": {"path": "created_at"}
                },
                "static_injection": {},
                "global_fields": {},
                "iterator": {
                    "path": "items",
                    "fields": {}
                }
            }
        ]
    }

@pytest.mark.asyncio
@patch('httpx.AsyncClient.request')
async def test_layer3_egress_success(mock_request, db_session: AsyncSession, mock_contract_dsl):
    mock_request.return_value = Response(200, json={"status": "ok"})
    
    # Setup Contract
    contract_id = f"test_contract_{uuid.uuid4()}"
    contract = MappingContract(
        id=contract_id,
        version="v1",
        status=ContractStatus.ACTIVE,
        dsl_config=mock_contract_dsl
    )
    db_session.add(contract)
    
    # Setup pre-MAPPED inbox 
    mapped_data = [{"transformed": "yes", "total_qty": 50}]
    inbox = AdapterInbox(
        source_system="test_system",
        mapping_id=contract_id,
        mapping_version="v1",
        payload={"qty": 5},
        mapped_payload=mapped_data,
        status=InboxStatus.MAPPED
    )
    db_session.add(inbox)
    await db_session.commit()
    
    # ------------------
    # Execute Layer 3
    # ------------------
    processed_count = await AdapterWorker.process_egress_batch(batch_size=10, session=db_session)
    assert processed_count == 1
    
    # Wait slightly to ensure fire-and-forget background task finishes inserting the log
    import asyncio
    await asyncio.sleep(0.1)
    
    # Assert Http Call
    mock_request.assert_called_once()
    args, kwargs = mock_request.call_args
    assert kwargs['url'] == "http://example-ledger.test/ingest"
    assert kwargs['json'] == mapped_data[0] # Extracted directly from mapped_payload
    
    await db_session.refresh(inbox)
    assert inbox.status == InboxStatus.FORWARDED
    
    # Assert Egress Log was fully isolated
    # Since insert_egress_log_async runs in a fire-and-forget background task with a new session,
    # we need to politely poll the DB in the test to avoid race conditions.
    import asyncio
    log_entry = None
    for _ in range(10):
        stmt = select(AdapterEgressLogs).where(AdapterEgressLogs.inbox_id == inbox.id)
        result = await db_session.execute(stmt)
        log_entry = result.scalars().first()
        if log_entry:
            break
        await asyncio.sleep(0.1)
        
    assert log_entry is not None, "Egress Log was not inserted"
    assert log_entry.response_status == "200"


@pytest.mark.asyncio
@patch('httpx.AsyncClient.request')
async def test_layer3_egress_domain_rejection(mock_request, db_session: AsyncSession, mock_contract_dsl):
    # Simulate Ledger rejecting payload schema rules (HTTP 422)
    mock_request.return_value = Response(422, json={"error": "Schema Invalid"})
    
    contract_id = f"test_contract_{uuid.uuid4()}"
    contract = MappingContract(
        id=contract_id, version="v1", status=ContractStatus.ACTIVE, dsl_config=mock_contract_dsl
    )
    db_session.add(contract)
    
    inbox = AdapterInbox(
        source_system="test_system",
        mapping_id=contract_id, mapping_version="v1",
        payload={}, mapped_payload=[{"bad": "data"}],
        status=InboxStatus.MAPPED
    )
    db_session.add(inbox)
    await db_session.commit()
    
    # Execute Layer 3
    processed_count = await AdapterWorker.process_egress_batch(batch_size=1, session=db_session)
    assert processed_count == 1
    
    await db_session.refresh(inbox)
    # Must immediately go to DESTINATION_REJECTED. Not DLQ.
    assert inbox.status == InboxStatus.DESTINATION_REJECTED
    assert "422" in inbox.error_message


@pytest.mark.asyncio
@patch('httpx.AsyncClient.request')
async def test_layer3_egress_transport_retry(mock_request, db_session: AsyncSession, mock_contract_dsl):
    import httpx
    # Simulate Network Timeout
    mock_request.side_effect = httpx.TimeoutException("Read timeout")
    
    contract_id = f"test_contract_{uuid.uuid4()}"
    contract = MappingContract(
        id=contract_id, version="v1", status=ContractStatus.ACTIVE, dsl_config=mock_contract_dsl
    )
    db_session.add(contract)
    
    inbox = AdapterInbox(
        source_system="test_system",
        mapping_id=contract_id, mapping_version="v1",
        payload={}, mapped_payload=[{"good": "data"}],
        status=InboxStatus.MAPPED 
    )
    db_session.add(inbox)
    await db_session.commit()
    
    # Execute Layer 3
    await AdapterWorker.process_egress_batch(batch_size=1, session=db_session)
    
    await db_session.refresh(inbox)
    # Must go back squarely to RETRY_EGRESS
    assert inbox.status == InboxStatus.RETRY_EGRESS
