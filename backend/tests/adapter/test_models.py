import pytest
from sqlalchemy.exc import IntegrityError
from app.adapter.models.engine import AdapterInbox, InboxStatus, MappingContract, ContractStatus

@pytest.mark.asyncio
async def test_inbox_mapped_constraint_missing_payload(db_session):
    """
    Test that the database enforces the CheckConstraint:
    If status is MAPPED, we MUST have mapping_id, mapping_version, and mapped_payload.
    """
    inbox_invalid = AdapterInbox(
        source_system="test_system",
        payload={"raw": "data"},
        status=InboxStatus.MAPPED,
        mapping_id="test_contract",
        mapping_version="1.0"
        # mapped_payload is purposefully missing
    )
    
    db_session.add(inbox_invalid)
    with pytest.raises(IntegrityError) as excinfo:
        await db_session.commit()
    
    assert "chk_mapped_state_requirements" in str(excinfo.value)
    await db_session.rollback()

@pytest.mark.asyncio
async def test_inbox_mapped_constraint_success(db_session):
    """
    Test that the database allows the MAPPED state when all required fields are present.
    """
    inbox_valid = AdapterInbox(
        source_system="test_system",
        payload={"raw": "data"},
        status=InboxStatus.MAPPED,
        mapping_id="test_contract",
        mapping_version="1.0",
        mapped_payload={"mapped": "data"}
    )
    
    db_session.add(inbox_valid)
    await db_session.commit()
    
    assert inbox_valid.id is not None
    assert inbox_valid.mapped_payload == {"mapped": "data"}

@pytest.mark.asyncio
async def test_mapping_contract_fields(db_session):
    """
    Test that the new ContractStatus enum and testing fields persist correctly.
    """
    contract = MappingContract(
        id="test_schema",
        version="1.0",
        status=ContractStatus.DRAFT,
        dsl_config={"some": "rule"},
        sample_in={"messy": "payload"},
        expected_out={"clean": "command"},
        test_result_metadata={"passed": True}
    )
    db_session.add(contract)
    await db_session.commit()
    
    assert contract.status == ContractStatus.DRAFT
    assert contract.sample_in == {"messy": "payload"}
    assert contract.test_result_metadata == {"passed": True}
