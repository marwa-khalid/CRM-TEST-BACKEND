"""plating charges per vehicle

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-16

Adds client_vehicle_id to plating_additional_charges so plating is stored
per hire vehicle instead of once per claim.
"""
from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plating_additional_charges",
        sa.Column("client_vehicle_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_plating_additional_charges_client_vehicle_id",
        "plating_additional_charges",
        ["client_vehicle_id"],
    )
    op.create_foreign_key(
        "fk_plating_client_vehicle",
        "plating_additional_charges",
        "client_vehicles",
        ["client_vehicle_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_plating_client_vehicle", "plating_additional_charges", type_="foreignkey")
    op.drop_index("ix_plating_additional_charges_client_vehicle_id", table_name="plating_additional_charges")
    op.drop_column("plating_additional_charges", "client_vehicle_id")
