"""add fleet_hire_vehicle table (multi-vehicle / swap)

Revision ID: f3c4d5e6f7b9
Revises: f2b3c4d5e6f7
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f3c4d5e6f7b9"
down_revision: Union[str, None] = "f2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fleet_hire_vehicle",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("hire_id", sa.Integer(), sa.ForeignKey("fleet_hire.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("vehicle_cost_per_week", sa.String(length=50), nullable=True),
        sa.Column("deposit", sa.String(length=50), nullable=True),
        sa.Column("borough", sa.String(length=100), nullable=True),
        sa.Column("registration_number", sa.String(length=50), nullable=True),
        sa.Column("make", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("transmission", sa.String(length=50), nullable=True),
        sa.Column("hire_status", sa.String(length=20), nullable=True),
        sa.Column("swap_car", sa.String(length=10), nullable=True),
        sa.Column("swap_reason", sa.String(length=100), nullable=True),
        sa.Column("swap_reason_text", sa.Text(), nullable=True),
        sa.Column("hire_start_date", sa.Date(), nullable=True),
        sa.Column("hire_end_date", sa.Date(), nullable=True),
        sa.Column("total_hire_period", sa.String(length=100), nullable=True),
        sa.Column("hire_insurance_type", sa.String(length=100), nullable=True),
        sa.Column("insurance_date_received", sa.Date(), nullable=True),
        sa.Column("policy_start_date", sa.Date(), nullable=True),
        sa.Column("policy_end_date", sa.Date(), nullable=True),
        sa.Column("cross_hire_provider_name", sa.String(length=200), nullable=True),
        sa.Column("cross_hire_contact_details", sa.String(length=200), nullable=True),
        sa.Column("cross_hire_rate", sa.String(length=50), nullable=True),
        sa.Column("mileage_start", sa.String(length=50), nullable=True),
        sa.Column("mileage_end", sa.String(length=50), nullable=True),
        sa.Column("checkout_date", sa.Date(), nullable=True),
        sa.Column("checkout_time", sa.String(length=10), nullable=True),
        sa.Column("checkout_cleanliness", sa.String(length=50), nullable=True),
        sa.Column("damage_charges", sa.String(length=50), nullable=True),
        sa.Column("damage_notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("fleet_hire_vehicle")
