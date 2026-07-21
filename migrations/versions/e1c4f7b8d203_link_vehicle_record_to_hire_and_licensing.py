"""link vehicle record to hire + add licensing authority table

Revision ID: e1c4f7b8d203
Revises: d9b3e6a7c012
"""
from alembic import op
import sqlalchemy as sa

revision = "e1c4f7b8d203"
down_revision = "d9b3e6a7c012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fleet_vehicle_record", sa.Column("hire_id", sa.Integer(), nullable=True))
    op.create_index("ix_fleet_vehicle_record_hire_id", "fleet_vehicle_record", ["hire_id"])
    op.create_foreign_key(
        "fk_fleet_vehicle_record_hire", "fleet_vehicle_record", "fleet_hire",
        ["hire_id"], ["id"], ondelete="CASCADE",
    )

    op.create_table(
        "fleet_vehicle_licensing_authority",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("vehicle_record_id", sa.Integer(), nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("licensing_authority", sa.String(length=200), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("postcode", sa.String(length=20), nullable=True),
        sa.Column("telephone", sa.String(length=50), nullable=True),
        sa.Column("contact_number", sa.String(length=50), nullable=True),
        sa.Column("email_address", sa.String(length=200), nullable=True),
        sa.Column("plate_number", sa.String(length=100), nullable=True),
        sa.Column("plating_start_date", sa.Date(), nullable=True),
        sa.Column("plating_expiry_date", sa.Date(), nullable=True),
        sa.Column("plating_booked_date", sa.Date(), nullable=True),
        sa.Column("plating_booked_time", sa.String(length=20), nullable=True),
        sa.Column("plating_attended_passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("plating_certificate_name", sa.String(length=255), nullable=True),
        sa.Column("plating_certificate_key", sa.String(length=500), nullable=True),
        sa.Column("plating_certificate_url", sa.Text(), nullable=True),
        sa.Column("mot_centre_name", sa.String(length=200), nullable=True),
        sa.Column("mot_address", sa.Text(), nullable=True),
        sa.Column("mot_postcode", sa.String(length=20), nullable=True),
        sa.Column("mot_telephone", sa.String(length=50), nullable=True),
        sa.Column("mot_email_address", sa.String(length=200), nullable=True),
        sa.Column("last_mot_date", sa.Date(), nullable=True),
        sa.Column("mot_expiry_date", sa.Date(), nullable=True),
        sa.Column("mot_booked_date", sa.Date(), nullable=True),
        sa.Column("mot_booked_time", sa.String(length=20), nullable=True),
        sa.Column("mot_attended_passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("mot_certificate_name", sa.String(length=255), nullable=True),
        sa.Column("mot_certificate_key", sa.String(length=500), nullable=True),
        sa.Column("mot_certificate_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("is_deleted", sa.Boolean(), nullable=True, server_default="false"),
        sa.ForeignKeyConstraint(["vehicle_record_id"], ["fleet_vehicle_record.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("fleet_vehicle_licensing_authority")
    op.drop_constraint("fk_fleet_vehicle_record_hire", "fleet_vehicle_record", type_="foreignkey")
    op.drop_index("ix_fleet_vehicle_record_hire_id", table_name="fleet_vehicle_record")
    op.drop_column("fleet_vehicle_record", "hire_id")
