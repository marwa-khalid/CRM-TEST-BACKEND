"""add agreed repair/recovery/engineer/plating rates to comparison_settlements

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa


revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("comparison_settlements", sa.Column("agreed_repair_rate", sa.Numeric(10, 2), nullable=True))
    op.add_column("comparison_settlements", sa.Column("agreed_recovery_rate", sa.Numeric(10, 2), nullable=True))
    op.add_column("comparison_settlements", sa.Column("agreed_engineer_rate", sa.Numeric(10, 2), nullable=True))
    op.add_column("comparison_settlements", sa.Column("agreed_plating_rate", sa.Numeric(10, 2), nullable=True))


def downgrade():
    op.drop_column("comparison_settlements", "agreed_plating_rate")
    op.drop_column("comparison_settlements", "agreed_engineer_rate")
    op.drop_column("comparison_settlements", "agreed_recovery_rate")
    op.drop_column("comparison_settlements", "agreed_repair_rate")
