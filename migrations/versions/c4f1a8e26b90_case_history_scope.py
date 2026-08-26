"""case_history polymorphic scope (claims + fleet)

Adds a generic scope so the same table backs Claims History and the Fleet History
(fleet hires + VM CAMS / VM Skyline vehicles): scope_type ('claim' | 'fleet_hire' |
'vm_cams' | 'vm_skyline') + scope_id. claim_id becomes nullable (fleet rows leave it
NULL). Existing rows are backfilled to scope_type='claim', scope_id=claim_id.

Revision ID: c4f1a8e26b90
Revises: b3e7c1d92a45
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c4f1a8e26b90'
down_revision: Union[str, None] = 'b3e7c1d92a45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE case_history ADD COLUMN IF NOT EXISTS scope_type varchar(20) NOT NULL DEFAULT 'claim'")
    op.execute("ALTER TABLE case_history ADD COLUMN IF NOT EXISTS scope_id integer")
    op.execute("ALTER TABLE case_history ALTER COLUMN claim_id DROP NOT NULL")
    # Backfill existing (claim) rows so the scope columns are populated.
    op.execute("UPDATE case_history SET scope_type = 'claim' WHERE scope_type IS NULL")
    op.execute("UPDATE case_history SET scope_id = claim_id WHERE scope_id IS NULL AND claim_id IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_history_scope_type ON case_history (scope_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_history_scope_id ON case_history (scope_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_case_history_scope_id")
    op.execute("DROP INDEX IF EXISTS ix_case_history_scope_type")
    op.execute("ALTER TABLE case_history DROP COLUMN IF EXISTS scope_id")
    op.execute("ALTER TABLE case_history DROP COLUMN IF EXISTS scope_type")
