"""add fleet hire vehicle details columns (screen 5)

Revision ID: f1a2b3c4d5e6
Revises: f1e2d3c4b5a6
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "f1e2d3c4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = [
    ("vehicle_cost_per_week", sa.String(length=50)),
    ("deposit", sa.String(length=50)),
    ("borough", sa.String(length=100)),
    ("registration_number", sa.String(length=50)),
    ("make", sa.String(length=100)),
    ("model", sa.String(length=100)),
    ("transmission", sa.String(length=50)),
    ("hire_status", sa.String(length=20)),
    ("swap_car", sa.String(length=10)),
    ("swap_reason", sa.String(length=100)),
    ("swap_reason_text", sa.Text()),
    ("hire_start_date", sa.Date()),
    ("hire_end_date", sa.Date()),
    ("total_hire_period", sa.String(length=100)),
    ("hire_insurance_type", sa.String(length=100)),
    ("insurance_date_received", sa.Date()),
    ("policy_start_date", sa.Date()),
    ("policy_end_date", sa.Date()),
    ("cross_hire_provider_name", sa.String(length=200)),
    ("cross_hire_contact_details", sa.String(length=200)),
    ("cross_hire_rate", sa.String(length=50)),
]


def upgrade() -> None:
    for name, col_type in _COLUMNS:
        op.add_column("fleet_hire", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("fleet_hire", name)
