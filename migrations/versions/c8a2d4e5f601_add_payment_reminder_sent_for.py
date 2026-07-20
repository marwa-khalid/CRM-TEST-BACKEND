"""add payment_reminder_sent_for to fleet_hire

Revision ID: c8a2d4e5f601
Revises: b7f1c2d3e4a5
"""
from alembic import op
import sqlalchemy as sa

revision = "c8a2d4e5f601"
down_revision = "b7f1c2d3e4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fleet_hire", sa.Column("payment_reminder_sent_for", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("fleet_hire", "payment_reminder_sent_for")
