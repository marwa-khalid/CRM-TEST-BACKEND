"""add plate/MOT reminder stamps to fleet_vehicle_licensing_authority

Revision ID: c4a8e2f6b130
Revises: b6f0c3a2d947
"""
from alembic import op
import sqlalchemy as sa

revision = "c4a8e2f6b130"
down_revision = "b6f0c3a2d947"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fleet_vehicle_licensing_authority",
                  sa.Column("plating_reminder_sent_on", sa.Date(), nullable=True))
    op.add_column("fleet_vehicle_licensing_authority",
                  sa.Column("mot_reminder_sent_on", sa.Date(), nullable=True))
    op.create_index("ix_fleet_la_plating_expiry", "fleet_vehicle_licensing_authority",
                    ["plating_expiry_date"])
    op.create_index("ix_fleet_la_mot_expiry", "fleet_vehicle_licensing_authority",
                    ["mot_expiry_date"])


def downgrade() -> None:
    op.drop_index("ix_fleet_la_mot_expiry", table_name="fleet_vehicle_licensing_authority")
    op.drop_index("ix_fleet_la_plating_expiry", table_name="fleet_vehicle_licensing_authority")
    op.drop_column("fleet_vehicle_licensing_authority", "mot_reminder_sent_on")
    op.drop_column("fleet_vehicle_licensing_authority", "plating_reminder_sent_on")
