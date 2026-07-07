"""add task_notes + task_history tables

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa


revision = "f9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def _base_cols():
    return [
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    ]


def upgrade():
    op.create_table(
        "task_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        *_base_cols(),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_notes_id"), "task_notes", ["id"], unique=False)
    op.create_index(op.f("ix_task_notes_task_id"), "task_notes", ["task_id"], unique=False)

    op.create_table(
        "task_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        *_base_cols(),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_history_id"), "task_history", ["id"], unique=False)
    op.create_index(op.f("ix_task_history_task_id"), "task_history", ["task_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_task_history_task_id"), table_name="task_history")
    op.drop_index(op.f("ix_task_history_id"), table_name="task_history")
    op.drop_table("task_history")
    op.drop_index(op.f("ix_task_notes_task_id"), table_name="task_notes")
    op.drop_index(op.f("ix_task_notes_id"), table_name="task_notes")
    op.drop_table("task_notes")
