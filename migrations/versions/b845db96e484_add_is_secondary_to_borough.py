"""add is_secondary to borough

Revision ID: b845db96e484
Revises: e4f2219d4ae5
Create Date: 2026-07-31 03:34:02.251318

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b845db96e484'
down_revision: Union[str, None] = 'e4f2219d4ae5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE borough ADD COLUMN IF NOT EXISTS is_secondary boolean DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE borough DROP COLUMN IF EXISTS is_secondary")
