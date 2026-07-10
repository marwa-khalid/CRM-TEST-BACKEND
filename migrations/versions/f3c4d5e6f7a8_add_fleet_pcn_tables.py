"""add fleet PCN management tables

Revision ID: f3c4d5e6f7a8
Revises: f3c4d5e6f7b9
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3c4d5e6f7a8"
down_revision: Union[str, None] = "f3c4d5e6f7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fleet_pcn",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hire_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("council_name", sa.String(length=200), nullable=True),
        sa.Column("council_address", sa.Text(), nullable=True),
        sa.Column("council_postcode", sa.String(length=20), nullable=True),
        sa.Column("pcn_number", sa.String(length=100), nullable=True),
        sa.Column("offence_date", sa.Date(), nullable=True),
        sa.Column("pcn_status", sa.String(length=100), nullable=True),
        sa.Column("liability_transfer_status", sa.String(length=100), nullable=True),
        sa.Column("response_deadline", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["hire_id"], ["fleet_hire.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_fleet_pcn_created_by", use_alter=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name="fk_fleet_pcn_updated_by", use_alter=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fleet_pcn_id"), "fleet_pcn", ["id"], unique=False)
    op.create_index(op.f("ix_fleet_pcn_hire_id"), "fleet_pcn", ["hire_id"], unique=False)
    op.create_index(op.f("ix_fleet_pcn_tenant_id"), "fleet_pcn", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_fleet_pcn_created_by"), "fleet_pcn", ["created_by"], unique=False)
    op.create_index(op.f("ix_fleet_pcn_updated_by"), "fleet_pcn", ["updated_by"], unique=False)

    op.create_table(
        "fleet_pcn_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pcn_id", sa.Integer(), nullable=False),
        sa.Column("doc_type", sa.String(length=100), nullable=False),
        sa.Column("filename", sa.String(length=300), nullable=True),
        sa.Column("s3_key", sa.String(length=500), nullable=True),
        sa.Column("file_url", sa.Text(), nullable=True),
        sa.Column("storage_backend", sa.String(length=50), nullable=True),
        sa.Column("received_on", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["pcn_id"], ["fleet_pcn.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fleet_pcn_document_id"), "fleet_pcn_document", ["id"], unique=False)
    op.create_index(op.f("ix_fleet_pcn_document_pcn_id"), "fleet_pcn_document", ["pcn_id"], unique=False)

    op.create_table(
        "fleet_pcn_note",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pcn_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_by_name", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["pcn_id"], ["fleet_pcn.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fleet_pcn_note_id"), "fleet_pcn_note", ["id"], unique=False)
    op.create_index(op.f("ix_fleet_pcn_note_pcn_id"), "fleet_pcn_note", ["pcn_id"], unique=False)

    op.create_table(
        "fleet_pcn_reminder",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pcn_id", sa.Integer(), nullable=False),
        sa.Column("reminder_type", sa.String(length=100), nullable=False),
        sa.Column("reminder_date", sa.Date(), nullable=True),
        sa.Column("reminder_time", sa.String(length=10), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["pcn_id"], ["fleet_pcn.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pcn_id", "reminder_type", name="uq_fleet_pcn_reminder_type"),
    )
    op.create_index(op.f("ix_fleet_pcn_reminder_id"), "fleet_pcn_reminder", ["id"], unique=False)
    op.create_index(op.f("ix_fleet_pcn_reminder_pcn_id"), "fleet_pcn_reminder", ["pcn_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_fleet_pcn_reminder_pcn_id"), table_name="fleet_pcn_reminder")
    op.drop_index(op.f("ix_fleet_pcn_reminder_id"), table_name="fleet_pcn_reminder")
    op.drop_table("fleet_pcn_reminder")
    op.drop_index(op.f("ix_fleet_pcn_note_pcn_id"), table_name="fleet_pcn_note")
    op.drop_index(op.f("ix_fleet_pcn_note_id"), table_name="fleet_pcn_note")
    op.drop_table("fleet_pcn_note")
    op.drop_index(op.f("ix_fleet_pcn_document_pcn_id"), table_name="fleet_pcn_document")
    op.drop_index(op.f("ix_fleet_pcn_document_id"), table_name="fleet_pcn_document")
    op.drop_table("fleet_pcn_document")
    op.drop_index(op.f("ix_fleet_pcn_updated_by"), table_name="fleet_pcn")
    op.drop_index(op.f("ix_fleet_pcn_created_by"), table_name="fleet_pcn")
    op.drop_index(op.f("ix_fleet_pcn_tenant_id"), table_name="fleet_pcn")
    op.drop_index(op.f("ix_fleet_pcn_hire_id"), table_name="fleet_pcn")
    op.drop_index(op.f("ix_fleet_pcn_id"), table_name="fleet_pcn")
    op.drop_table("fleet_pcn")
