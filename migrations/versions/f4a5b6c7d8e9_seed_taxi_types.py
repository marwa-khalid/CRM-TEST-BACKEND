"""seed taxi_types lookup (Hackney Carriage, Private Hire Vehicle)

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-03

The taxi_types lookup was never seeded (unlike fuel_types / transmissions), so the
Vehicle Details "Taxi Type" dropdown was empty. Seed the two standard UK taxi
licensing categories; admins can add/edit more via /setups/taxi-types.
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


_taxi_types = sa.table(
    "taxi_types",
    sa.column("label", sa.String),
    sa.column("sort_order", sa.Integer),
    sa.column("is_active", sa.Boolean),
    sa.column("is_deleted", sa.Boolean),
    sa.column("tenant_id", sa.Integer),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)

_LABELS = ["Hackney Carriage", "Private Hire Vehicle"]


def upgrade() -> None:
    now = datetime.utcnow()
    op.bulk_insert(
        _taxi_types,
        [
            {
                "label": label,
                "sort_order": i + 1,
                "is_active": True,
                "is_deleted": False,
                "tenant_id": None,
                "created_at": now,
                "updated_at": now,
            }
            for i, label in enumerate(_LABELS)
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM taxi_types WHERE label IN ('Hackney Carriage', 'Private Hire Vehicle')"
    )
