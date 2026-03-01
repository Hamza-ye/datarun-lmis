"""partition_adapter_logs

Revision ID: 24c811d21401
Revises: ad545822c140
Create Date: 2026-02-26 04:23:46.615938

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '24c811d21401'
down_revision: Union[str, Sequence[str], None] = 'ad545822c140'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table('adapter_logs')
    
    op.execute("""
    CREATE TABLE adapter_logs (
        id UUID NOT NULL,
        inbox_id UUID NOT NULL,
        destination_url VARCHAR NOT NULL,
        request_payload JSON NOT NULL,
        response_status VARCHAR NOT NULL,
        response_body VARCHAR,
        execution_time_ms BIGINT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
        PRIMARY KEY (id, created_at)
    ) PARTITION BY RANGE (created_at);
    """)
    
    op.execute("""
    CREATE OR REPLACE FUNCTION trg_adapter_logs_insert() RETURNS trigger AS $$
    DECLARE
        partition_date TEXT;
        partition_name TEXT;
        start_of_month TIMESTAMP;
        end_of_month TIMESTAMP;
    BEGIN
        start_of_month := date_trunc('month', NEW.created_at);
        end_of_month := start_of_month + interval '1 month';
        partition_date := to_char(start_of_month, 'YYYY_MM');
        partition_name := 'adapter_logs_' || partition_date;

        IF NOT EXISTS(SELECT 1 FROM pg_class WHERE relname = partition_name) THEN
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I PARTITION OF adapter_logs FOR VALUES FROM (%L) TO (%L);',
                partition_name, start_of_month, end_of_month
            );
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
    CREATE TRIGGER before_insert_adapter_logs
    BEFORE INSERT ON adapter_logs
    FOR EACH ROW EXECUTE FUNCTION trg_adapter_logs_insert();
    """)


def downgrade() -> None:
    """Downgrade schema."""
    pass
