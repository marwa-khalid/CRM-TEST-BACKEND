"""make case_activity_notes.claim_id nullable (fleet/VM history notes)

Fleet-hire and Vehicle-Management history records aren't claims, so notes attached
to them are stored with claim_id NULL (keyed only by activity_ref). The FK to
claims.id stays — it simply permits NULL.

Revision ID: a7f3c9d21e08
Revises: e6c3b1f74a92
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7f3c9d21e08'
down_revision: Union[str, None] = 'e6c3b1f74a92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'case_activity_notes', 'claim_id',
        existing_type=sa.Integer(), nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'case_activity_notes', 'claim_id',
        existing_type=sa.Integer(), nullable=False,
    )
