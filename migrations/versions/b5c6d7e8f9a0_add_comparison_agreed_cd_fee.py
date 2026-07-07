"""add agreed_cd_fee to comparison_settlements

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa


revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("comparison_settlements", sa.Column("agreed_cd_fee", sa.Numeric(10, 2), nullable=True))


def downgrade():
    op.drop_column("comparison_settlements", "agreed_cd_fee")
