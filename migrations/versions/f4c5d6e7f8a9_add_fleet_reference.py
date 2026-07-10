"""add fleet hire reference

Revision ID: f4c5d6e7f8a9
Revises: f3c4d5e6f7a8
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4c5d6e7f8a9"
down_revision: Union[str, None] = "f3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fleet_hire", sa.Column("fleet_reference", sa.String(length=50), nullable=True))
    op.execute(
        """
        UPDATE fleet_hire
        SET fleet_reference = 'FLT-'
            || to_char(COALESCE(file_opened_at, created_at, now()), 'YYYYMM')
            || '-'
            || lpad(id::text, 3, '0')
        WHERE fleet_reference IS NULL
        """
    )
    op.create_index(op.f("ix_fleet_hire_fleet_reference"), "fleet_hire", ["fleet_reference"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_fleet_hire_fleet_reference"), table_name="fleet_hire")
    op.drop_column("fleet_hire", "fleet_reference")
