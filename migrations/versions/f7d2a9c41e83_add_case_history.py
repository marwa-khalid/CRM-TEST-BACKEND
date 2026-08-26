"""add case_history table

Case History section — a chronological, user-recorded log of case communications
(letters, emails, calls), notes and diary entries. Distinct from the file-based
Case Activity feed (`history_activities`). Each supported action creates one row;
`payload` (jsonb) holds the type-specific detail. action_type is a postgres enum
whose labels are the CaseHistoryActionType member names.

Revision ID: f7d2a9c41e83
Revises: d8b2e4f6a1c7
Create Date: 2026-08-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f7d2a9c41e83'
down_revision: Union[str, None] = 'd8b2e4f6a1c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'casehistoryactiontype') THEN
                CREATE TYPE casehistoryactiontype AS ENUM (
                    'SEND_LETTER', 'SEND_EMAIL', 'INCOMING_CALL',
                    'OUTGOING_CALL', 'NOTE', 'DIARY'
                );
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS case_history (
            id SERIAL PRIMARY KEY,
            claim_id integer NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
            tenant_id integer REFERENCES tenants(id),
            action_type casehistoryactiontype NOT NULL,
            posted_at timestamptz DEFAULT now(),
            correspondent varchar(255),
            handler varchar(255),
            subject varchar(500),
            details text,
            payload jsonb,
            is_active boolean DEFAULT true,
            is_deleted boolean DEFAULT false,
            created_at timestamptz DEFAULT now(),
            updated_at timestamptz DEFAULT now(),
            created_by integer,
            updated_by integer
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_history_id ON case_history (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_history_claim_id ON case_history (claim_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_history_tenant_id ON case_history (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_history_action_type ON case_history (action_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_history_posted_at ON case_history (posted_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_history_created_by ON case_history (created_by)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_history_updated_by ON case_history (updated_by)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS case_history")
    op.execute("DROP TYPE IF EXISTS casehistoryactiontype")
