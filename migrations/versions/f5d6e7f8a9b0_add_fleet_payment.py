"""add fleet payment details columns + fleet_hire_payment table (screen 7)

Revision ID: f5d6e7f8a9b0
Revises: f4c5d6e7f8a9
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f5d6e7f8a9b0"
down_revision: Union[str, None] = "f4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HIRE_COLUMNS = [
    ("payment_hire_start_date", sa.Date()),
    ("payment_hire_end_date", sa.Date()),
    ("vehicle_cost_per_day", sa.String(length=50)),
    ("number_of_weekly_payments", sa.String(length=20)),
    ("payment_day", sa.Date()),
    ("security_deposit", sa.String(length=50)),
    ("weekly_hire_payment", sa.String(length=50)),
    ("total_planned_hire_cost", sa.String(length=50)),
    ("initial_amount_due", sa.String(length=50)),
    ("payment_damage_charges", sa.String(length=50)),
    ("additional_charges", sa.String(length=100)),
]


def upgrade() -> None:
    for name, col_type in _HIRE_COLUMNS:
        op.add_column("fleet_hire", sa.Column(name, col_type, nullable=True))
    op.create_table(
        "fleet_hire_payment",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("hire_id", sa.Integer(), sa.ForeignKey("fleet_hire.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("week", sa.Integer(), nullable=True),
        sa.Column("due_amount", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("paid_amount", sa.String(length=50), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("fleet_hire_payment")
    for name, _ in reversed(_HIRE_COLUMNS):
        op.drop_column("fleet_hire", name)
