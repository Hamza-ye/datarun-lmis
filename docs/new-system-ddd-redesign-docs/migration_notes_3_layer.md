# Advanced Guide for 3-Layer Alembic Migration

The proposed changes in engine.py include significant state and constraints manipulations. When generating the Alembic migration, the following manual adjustments might be required for the automatically generated script.

## 1. InboxStatus Enum Migration
Postgres handles Enums strictly. We are dropping `ERROR` and `RETRY` taking their place `DESTINATION_REJECTED` and `RETRY_EGRESS`.
```python
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    # 1. Update Enum values in Postgres
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE inbox_status ADD VALUE 'DESTINATION_REJECTED'")
        op.execute("ALTER TYPE inbox_status ADD VALUE 'RETRY_EGRESS'")
    
    # 2. Migrate existing data (Optional depending on active DLQ state)
    op.execute("UPDATE adapter_inbox SET status = 'DESTINATION_REJECTED' WHERE status = 'ERROR'")
    op.execute("UPDATE adapter_inbox SET status = 'RETRY_EGRESS' WHERE status = 'RETRY'")
```

## 2. Check Constraints
Make sure the CheckConstraint is captured by the autogenerator. If not, explicitly add:
```python
    op.create_check_constraint(
        "chk_mapped_state_requirements",
        "adapter_inbox",
        "(status NOT IN ('MAPPED', 'FORWARDED', 'RETRY_EGRESS', 'DESTINATION_REJECTED')) OR (mapping_id IS NOT NULL AND mapping_version IS NOT NULL AND mapped_payload IS NOT NULL)"
    )
```

## 3. ContractStatus Enum
Creating the new enum type for `contract_status` may fail on downgrade or overwrite if handled improperly by autogenerate.
```python
    contract_status_enum = sa.Enum('DRAFT', 'REVIEW', 'APPROVED', 'ACTIVE', 'DEPRECATED', 'ARCHIVED', 'REJECTED', name='contract_status')
    contract_status_enum.create(op.get_bind())
```

## 4. Renaming Tables
Alembic might try to `drop_table('adapter_logs')` and `create_table('adapter_egress_logs')`. If you have active telemetry there that you don't want to lose, manually rename the table and add the new columns in the upgrade script instead:
```python
    op.rename_table('adapter_logs', 'adapter_egress_logs')
    op.add_column('adapter_egress_logs', sa.Column('retry_count', sa.BigInteger(), server_default='0'))
    op.add_column('adapter_egress_logs', sa.Column('delivery_time_ms', sa.BigInteger(), nullable=True))
```

This ensures the transition to the 3-Layer architecture is deterministic and data-safe.
