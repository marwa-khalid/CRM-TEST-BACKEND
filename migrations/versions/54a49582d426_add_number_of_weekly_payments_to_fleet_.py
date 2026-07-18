"""add number_of_weekly_payments to fleet_hire_vehicle

Revision ID: 54a49582d426
Revises: fe4f5a6b7c89
Create Date: 2026-07-18 16:47:09.456090

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '54a49582d426'
down_revision: Union[str, None] = 'fe4f5a6b7c89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Per-vehicle weekly-payment count (previously only a hire-level value existed).
    op.add_column(
        "fleet_hire_vehicle",
        sa.Column("number_of_weekly_payments", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fleet_hire_vehicle", "number_of_weekly_payments")
