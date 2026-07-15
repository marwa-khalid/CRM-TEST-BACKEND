"""add fleet register transmission

Revision ID: f9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9b0c1d2e3f4"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fleet_vehicle_register", sa.Column("transmission", sa.String(length=50), nullable=True))
    vehicle_register = sa.table(
        "fleet_vehicle_register",
        sa.column("registration_number", sa.String),
        sa.column("transmission", sa.String),
    )
    transmissions = {
        "WX17VHA": "Automatic",
        "F150FORD": "Automatic",
        "AB12CDE": "Automatic",
        "HJ19KLM": "Automatic",
        "PK68ZZZ": "Automatic",
        "LN21TAX": "Manual",
        "YT20CAB": "Automatic",
    }
    for registration_number, transmission in transmissions.items():
        op.execute(
            vehicle_register
            .update()
            .where(vehicle_register.c.registration_number == registration_number)
            .values(transmission=transmission)
        )


def downgrade() -> None:
    op.drop_column("fleet_vehicle_register", "transmission")
