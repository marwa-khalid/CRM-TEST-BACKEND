"""add fleet_vehicle_service (Service Summary Log)

Revision ID: f2d5a8c9e314
Revises: e1c4f7b8d203
"""
from alembic import op
import sqlalchemy as sa

revision = "f2d5a8c9e314"
down_revision = "e1c4f7b8d203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_vehicle_service",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("vehicle_record_id", sa.Integer(), nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("garage_name", sa.String(length=200), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("postcode", sa.String(length=20), nullable=True),
        sa.Column("contact_number", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("service_booked_date", sa.Date(), nullable=True),
        sa.Column("service_booked_time", sa.String(length=20), nullable=True),
        sa.Column("serviced_at_mileage", sa.String(length=20), nullable=True),
        sa.Column("serviced_on", sa.Date(), nullable=True),
        sa.Column("next_service_due_at", sa.String(length=20), nullable=True),
        sa.Column("case_reference", sa.String(length=100), nullable=True),
        sa.Column("invoice_name", sa.String(length=255), nullable=True),
        sa.Column("invoice_key", sa.String(length=500), nullable=True),
        sa.Column("invoice_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("is_deleted", sa.Boolean(), nullable=True, server_default="false"),
        sa.ForeignKeyConstraint(["vehicle_record_id"], ["fleet_vehicle_record.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("fleet_vehicle_service")
