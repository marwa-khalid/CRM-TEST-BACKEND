"""add payment mode to fleet payment transactions

Revision ID: fb1d2e3f4a56
Revises: fa0c1d2e3f45
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "fb1d2e3f4a56"
down_revision: Union[str, None] = "fa0c1d2e3f45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "fleet_hire_payment_transaction",
        sa.Column("payment_mode", sa.String(length=50), nullable=True),
    )
    op.execute(
        "UPDATE fleet_hire_payment_transaction "
        "SET payment_mode = 'cash' "
        "WHERE payment_mode IS NULL"
    )


def downgrade() -> None:
    op.drop_column("fleet_hire_payment_transaction", "payment_mode")
