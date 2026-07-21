"""add fleet_vehicle_record (Fleet vehicle asset wizard)

Revision ID: d9b3e6a7c012
Revises: c8a2d4e5f601
"""
from alembic import op
import sqlalchemy as sa

revision = "d9b3e6a7c012"
down_revision = "c8a2d4e5f601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_vehicle_record",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True, index=True),
        sa.Column("obtained_for_purpose", sa.String(length=100), nullable=True),
        sa.Column("contract_type", sa.String(length=100), nullable=True),
        sa.Column("company_owned_or_leased", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("cross_hired_to_us", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("registration_number", sa.String(length=50), nullable=True, index=True),
        sa.Column("make", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("manufacturer", sa.String(length=100), nullable=True),
        sa.Column("variant", sa.String(length=150), nullable=True),
        sa.Column("number_of_doors", sa.String(length=10), nullable=True),
        sa.Column("number_of_seats", sa.String(length=10), nullable=True),
        sa.Column("body_type", sa.String(length=100), nullable=True),
        sa.Column("fuel_type", sa.String(length=50), nullable=True),
        sa.Column("transmission", sa.String(length=50), nullable=True),
        sa.Column("engine_size_cc", sa.String(length=20), nullable=True),
        sa.Column("v5c_document_reference", sa.String(length=50), nullable=True),
        sa.Column("chassis_number", sa.String(length=50), nullable=True),
        sa.Column("date_of_first_registration", sa.Date(), nullable=True),
        sa.Column("date_delivered", sa.Date(), nullable=True),
        sa.Column("vehicle_status", sa.String(length=50), nullable=True),
        sa.Column("depot_branch", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=True, server_default="false"),
    )


def downgrade() -> None:
    op.drop_table("fleet_vehicle_record")
