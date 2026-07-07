"""add agreed_admin to comparison_settlements

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa


revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("comparison_settlements", sa.Column("agreed_admin", sa.Numeric(10, 2), nullable=True))


def downgrade():
    op.drop_column("comparison_settlements", "agreed_admin")
