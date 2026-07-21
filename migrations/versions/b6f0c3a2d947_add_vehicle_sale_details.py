"""add vehicle sale details to fleet_vehicle_record

Revision ID: b6f0c3a2d947
Revises: a3e7b1d4c825
"""
from alembic import op
import sqlalchemy as sa

revision = "b6f0c3a2d947"
down_revision = "a3e7b1d4c825"
branch_labels = None
depends_on = None

COLUMNS = [
    ("purchaser_name", sa.String(length=200)),
    ("purchaser_address", sa.Text()),
    ("purchaser_postcode", sa.String(length=20)),
    ("purchaser_telephone", sa.String(length=50)),
    ("purchaser_email", sa.String(length=200)),
    ("vehicle_sold_on", sa.Date()),
    ("sold_for_inc_vat", sa.String(length=50)),
    ("sold_for_exc_vat", sa.String(length=50)),
]


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.add_column("fleet_vehicle_record", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("fleet_vehicle_record", name)
