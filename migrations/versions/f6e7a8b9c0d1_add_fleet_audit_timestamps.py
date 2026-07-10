"""add created_at/updated_at to fleet_hire_vehicle + fleet_hire_payment

Both tables use AuditStampMixin (created_at/updated_at) but their create
migrations omitted the timestamp columns.

Revision ID: f6e7a8b9c0d1
Revises: f5d6e7f8a9b0
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6e7a8b9c0d1"
down_revision: Union[str, None] = "f5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("fleet_hire_vehicle", "fleet_hire_payment")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True))
        op.add_column(table, sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "updated_at")
        op.drop_column(table, "created_at")
