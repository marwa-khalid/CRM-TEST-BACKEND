"""scope fleet payments to hire vehicles

Revision ID: fd3e4f5a6b78
Revises: fc2d3e4f5a67
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "fd3e4f5a6b78"
down_revision: Union[str, None] = "fc2d3e4f5a67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fleet_hire_payment", sa.Column("vehicle_id", sa.Integer(), nullable=True))
    op.create_index("ix_fleet_hire_payment_vehicle_id", "fleet_hire_payment", ["vehicle_id"])
    op.create_foreign_key(
        "fk_fleet_hire_payment_vehicle_id",
        "fleet_hire_payment",
        "fleet_hire_vehicle",
        ["vehicle_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column("fleet_hire_vehicle", sa.Column("additional_charges", sa.String(length=100), nullable=True))
    op.add_column("fleet_hire_vehicle", sa.Column("additional_charges_reason", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE fleet_hire_payment AS payment
        SET vehicle_id = vehicle.id
        FROM (
            SELECT DISTINCT ON (hire_id) id, hire_id
            FROM fleet_hire_vehicle
            ORDER BY hire_id, position NULLS LAST, id
        ) AS vehicle
        WHERE payment.hire_id = vehicle.hire_id
          AND payment.vehicle_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("fleet_hire_vehicle", "additional_charges_reason")
    op.drop_column("fleet_hire_vehicle", "additional_charges")
    op.drop_constraint("fk_fleet_hire_payment_vehicle_id", "fleet_hire_payment", type_="foreignkey")
    op.drop_index("ix_fleet_hire_payment_vehicle_id", table_name="fleet_hire_payment")
    op.drop_column("fleet_hire_payment", "vehicle_id")
