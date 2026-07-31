"""add dual badge fields to borough

Revision ID: e4f2219d4ae5
Revises: 4e4958ab243e
Create Date: 2026-07-31 03:24:59.679152

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4f2219d4ae5'
down_revision: Union[str, None] = '4e4958ab243e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent (columns may already exist from an out-of-band ALTER).
    op.execute(
        "ALTER TABLE borough ADD COLUMN IF NOT EXISTS taxi_type_id_2 integer "
        "REFERENCES taxi_types(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE borough ADD COLUMN IF NOT EXISTS client_badge_number_2 varchar(200)")
    op.execute("ALTER TABLE borough ADD COLUMN IF NOT EXISTS badge_expiration_date_2 date")
    op.execute("ALTER TABLE borough ADD COLUMN IF NOT EXISTS dual_badge boolean DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE borough DROP COLUMN IF EXISTS taxi_type_id_2")
    op.execute("ALTER TABLE borough DROP COLUMN IF EXISTS client_badge_number_2")
    op.execute("ALTER TABLE borough DROP COLUMN IF EXISTS badge_expiration_date_2")
    op.execute("ALTER TABLE borough DROP COLUMN IF EXISTS dual_badge")
