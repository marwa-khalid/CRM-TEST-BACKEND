"""add screen_completion JSONB column to claims

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-03

Stores a per-screen "all fields filled" map so the claim sidebar's green checks
can be loaded in a single request instead of probing each screen.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("screen_completion", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("claims", "screen_completion")
