"""add authority_id to fleet_vehicle_document (per-authority certificates)

Revision ID: e7b2d4a6f158
Revises: d5c8a1f9e246
"""
from alembic import op
import sqlalchemy as sa

revision = "e7b2d4a6f158"
down_revision = "d5c8a1f9e246"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fleet_vehicle_document", sa.Column("authority_id", sa.Integer(), nullable=True))
    op.create_index("ix_fleet_vehicle_document_authority_id", "fleet_vehicle_document", ["authority_id"])


def downgrade() -> None:
    op.drop_index("ix_fleet_vehicle_document_authority_id", table_name="fleet_vehicle_document")
    op.drop_column("fleet_vehicle_document", "authority_id")
