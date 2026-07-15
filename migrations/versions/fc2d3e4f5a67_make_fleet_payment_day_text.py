"""make fleet payment day text

Revision ID: fc2d3e4f5a67
Revises: fb1d2e3f4a56
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "fc2d3e4f5a67"
down_revision: Union[str, None] = "fb1d2e3f4a56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "fleet_hire",
        "payment_day",
        existing_type=sa.Date(),
        type_=sa.String(length=50),
        existing_nullable=True,
        postgresql_using="payment_day::text",
    )


def downgrade() -> None:
    op.alter_column(
        "fleet_hire",
        "payment_day",
        existing_type=sa.String(length=50),
        type_=sa.Date(),
        existing_nullable=True,
        postgresql_using="payment_day::date",
    )
