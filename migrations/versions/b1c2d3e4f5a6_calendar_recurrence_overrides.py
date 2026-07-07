"""calendar: per-occurrence recurrence overrides

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = "b1c2d3e4f5a6"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendar_events", sa.Column("recurrence_overrides", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("calendar_events", "recurrence_overrides")
