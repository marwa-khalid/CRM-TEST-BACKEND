"""calendar_events table (Calendar module — Phase 1)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True, index=True),
        sa.Column("start_time", sa.String(length=5), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("end_time", sa.String(length=5), nullable=True),
        sa.Column("assigned_users", sa.Text(), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("reminder", sa.String(length=20), nullable=True),
        sa.Column("recurrence_rule", sa.String(length=20), nullable=True),
        sa.Column("attachment_path", sa.Text(), nullable=True),
        sa.Column("attachment_name", sa.String(length=300), nullable=True),
        sa.Column("claim_id", sa.Integer(), sa.ForeignKey("claims.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("claim_reference", sa.String(length=100), nullable=True),
        sa.Column("case_reference", sa.String(length=100), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True, index=True),
        sa.Column("vehicle_registration", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_ref_id", sa.Integer(), nullable=True, index=True),
        # BaseModel / AuditByMixin columns
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("is_deleted", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True, index=True),
        sa.Column("updated_by", sa.Integer(), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table("calendar_events")
