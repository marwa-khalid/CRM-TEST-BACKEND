"""add fleet_hire_audit table (GDPR audit log)

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2b3c4d5e6f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fleet_hire_audit",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("hire_id", sa.Integer(), sa.ForeignKey("fleet_hire.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user", sa.String(length=200), nullable=True),
        sa.Column("field_changed", sa.String(length=100), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("fleet_hire_audit")
