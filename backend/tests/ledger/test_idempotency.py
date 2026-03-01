from datetime import datetime, timezone

import pytest

from app.ledger.domain.idempotency.service import IdempotencyService
from app.ledger.schemas.command import LedgerCommand, TransactionType


def get_dummy_command(source_id: str, version: int = 1) -> LedgerCommand:
    return LedgerCommand(
        source_event_id=source_id,
        version_timestamp=version,
        transaction_type=TransactionType.ISSUE,
        node_id="CLINIC-1",
        item_id="PARAM-01",
        quantity=50,
        occurred_at=datetime.now(timezone.utc)
    )

@pytest.mark.asyncio
async def test_new_command_is_processed(db_session):
    """A completely new command should be accepted and flagged as PROCEED"""
    cmd = get_dummy_command("event-new-1")
    result = await IdempotencyService.check_or_register_command(db_session, cmd)
    assert result.action == "PROCEED"

@pytest.mark.asyncio
async def test_duplicate_command_is_ignored(db_session):
    """A payload that has already been registered with the same version should be IGNORED"""
    cmd = get_dummy_command("event-dup-2")
    
    # First attempt
    res1 = await IdempotencyService.check_or_register_command(db_session, cmd)
    assert res1.action == "PROCEED"
    
    # Second attempt
    res2 = await IdempotencyService.check_or_register_command(db_session, cmd)
    assert res2.action == "IGNORE"

@pytest.mark.asyncio
async def test_newer_version_triggers_reversal(db_session):
    """An edited form coming from the client with a higher version timestamp should trigger a REVERSAL signal"""
    cmd_v1 = get_dummy_command("event-edit-3", version=1)
    res1 = await IdempotencyService.check_or_register_command(db_session, cmd_v1)
    assert res1.action == "PROCEED"
    
    # Simulate editing the form (version bump)
    cmd_v2 = get_dummy_command("event-edit-3", version=2)
    res2 = await IdempotencyService.check_or_register_command(db_session, cmd_v2)
    assert res2.action == "REVERSE_AND_PROCEED"
    
@pytest.mark.asyncio
async def test_older_version_ignored(db_session):
    """If a delayed networking packet arrives containing an older version than we currently have, IGNORE it"""
    cmd_v2 = get_dummy_command("event-delay-4", version=2)
    await IdempotencyService.check_or_register_command(db_session, cmd_v2)
    
    # Delayed v1 packet arrives late
    cmd_v1 = get_dummy_command("event-delay-4", version=1)
    res2 = await IdempotencyService.check_or_register_command(db_session, cmd_v1)
    assert res2.action == "IGNORE"
