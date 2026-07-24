"""add fleet_vehicle_document (V5C upload history)

Revision ID: d5c8a1f9e246
Revises: c4a8e2f6b130
"""
from alembic import op
import sqlalchemy as sa

revision = "d5c8a1f9e246"
down_revision = "c4a8e2f6b130"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_vehicle_document",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("vehicle_record_id", sa.Integer(), nullable=False, index=True),
        sa.Column("doc_type", sa.String(length=50), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("s3_key", sa.String(length=500), nullable=True),
        sa.Column("file_url", sa.Text(), nullable=True),
        sa.Column("storage_backend", sa.String(length=50), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["vehicle_record_id"], ["fleet_vehicle_record.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("fleet_vehicle_document")
