"""plating: drop client_vehicle fk (vehicle dimension is the hire vehicle)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-16

The payment-screen vehicle cards track the HIRE (provided) vehicle, not the
claimant's client vehicle, so plating's client_vehicle_id holds a
hire_vehicle_provides id. Drop the client_vehicles FK (keep the plain column).
"""
from alembic import op


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("fk_plating_client_vehicle", "plating_additional_charges", type_="foreignkey")


def downgrade() -> None:
    op.create_foreign_key(
        "fk_plating_client_vehicle",
        "plating_additional_charges",
        "client_vehicles",
        ["client_vehicle_id"],
        ["id"],
        ondelete="CASCADE",
    )
