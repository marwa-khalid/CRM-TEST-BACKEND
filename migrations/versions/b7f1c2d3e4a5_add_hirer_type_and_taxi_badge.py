"""add hirer_type and taxi badge fields to fleet_hire

hirer_type ("taxi_driver" | "non_taxi_driver") is chosen on General Details and
unlocks the Taxi Badge step, whose OCR'd fields are stored alongside it.

Revision ID: b7f1c2d3e4a5
Revises: 54a49582d426
Create Date: 2026-07-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7f1c2d3e4a5"
down_revision: Union[str, None] = "54a49582d426"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fleet_hire", sa.Column("hirer_type", sa.String(length=50), nullable=True))
    op.add_column("fleet_hire", sa.Column("taxi_badge_number", sa.String(length=100), nullable=True))
    op.add_column("fleet_hire", sa.Column("taxi_badge_name", sa.String(length=200), nullable=True))
    op.add_column("fleet_hire", sa.Column("taxi_badge_expiry", sa.Date(), nullable=True))
    op.add_column("fleet_hire", sa.Column("taxi_badge_council", sa.String(length=200), nullable=True))
    op.add_column("fleet_hire", sa.Column("taxi_badge_type", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("fleet_hire", "taxi_badge_type")
    op.drop_column("fleet_hire", "taxi_badge_council")
    op.drop_column("fleet_hire", "taxi_badge_expiry")
    op.drop_column("fleet_hire", "taxi_badge_name")
    op.drop_column("fleet_hire", "taxi_badge_number")
    op.drop_column("fleet_hire", "hirer_type")
