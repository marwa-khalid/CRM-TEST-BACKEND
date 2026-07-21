"""add road fund licence fields to fleet_vehicle_record

Revision ID: a3e7b1d4c825
Revises: f2d5a8c9e314
"""
from alembic import op
import sqlalchemy as sa

revision = "a3e7b1d4c825"
down_revision = "f2d5a8c9e314"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fleet_vehicle_record", sa.Column("road_tax_renewed_on", sa.Date(), nullable=True))
    op.add_column("fleet_vehicle_record", sa.Column("road_tax_expiry_date", sa.Date(), nullable=True))
    op.add_column("fleet_vehicle_record", sa.Column("road_tax_reminder_sent_on", sa.Date(), nullable=True))
    op.create_index(
        "ix_fleet_vehicle_record_road_tax_expiry_date",
        "fleet_vehicle_record", ["road_tax_expiry_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_fleet_vehicle_record_road_tax_expiry_date", table_name="fleet_vehicle_record")
    op.drop_column("fleet_vehicle_record", "road_tax_reminder_sent_on")
    op.drop_column("fleet_vehicle_record", "road_tax_expiry_date")
    op.drop_column("fleet_vehicle_record", "road_tax_renewed_on")
