"""add service_id to fleet_vehicle_document (per-service-card invoices)

Revision ID: f1a3c7d2b904
Revises: e7b2d4a6f158
"""
from alembic import op
import sqlalchemy as sa

revision = "f1a3c7d2b904"
down_revision = "e7b2d4a6f158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fleet_vehicle_document", sa.Column("service_id", sa.Integer(), nullable=True))
    op.create_index("ix_fleet_vehicle_document_service_id", "fleet_vehicle_document", ["service_id"])


def downgrade() -> None:
    op.drop_index("ix_fleet_vehicle_document_service_id", table_name="fleet_vehicle_document")
    op.drop_column("fleet_vehicle_document", "service_id")
