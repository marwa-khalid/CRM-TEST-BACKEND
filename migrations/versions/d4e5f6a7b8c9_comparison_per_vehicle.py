"""comparison_settlements: per-vehicle agreed hire (hire_vehicle_id)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-16

When a claim has 2+ hire vehicles, the agreed HIRE figures (days/rate) are stored
per hire vehicle so each payment-screen card keeps its own values. The column
holds a hire_vehicle_provides id (no FK, mirroring plating). Existing rows stay
NULL = claim-level, so single-vehicle claims keep loading exactly as before.
Storage/recovery/engineer/plating/repair remain claim-level (counted once).
"""
from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "comparison_settlements",
        sa.Column("hire_vehicle_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_comparison_settlements_hire_vehicle_id",
        "comparison_settlements",
        ["hire_vehicle_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_comparison_settlements_hire_vehicle_id",
        table_name="comparison_settlements",
    )
    op.drop_column("comparison_settlements", "hire_vehicle_id")
