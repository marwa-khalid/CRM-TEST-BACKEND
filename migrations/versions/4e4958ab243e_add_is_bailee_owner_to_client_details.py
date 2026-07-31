"""add is_bailee_owner to client_details

Revision ID: 4e4958ab243e
Revises: f1a3c7d2b904
Create Date: 2026-07-30 21:11:43.611210

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e4958ab243e'
down_revision: Union[str, None] = 'f1a3c7d2b904'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: the column may already exist on environments where it was
    # added out-of-band. IF NOT EXISTS keeps this safe to run anywhere.
    op.execute(
        "ALTER TABLE client_details "
        "ADD COLUMN IF NOT EXISTS is_bailee_owner boolean DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE client_details DROP COLUMN IF EXISTS is_bailee_owner")
