"""add fleet vehicle register

Revision ID: f7a8b9c0d1e2
Revises: f6e7a8b9c0d1
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "f6e7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fleet_vehicle_register",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("registration_number", sa.String(length=50), nullable=False),
        sa.Column("make", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("registration_number", name="uq_fleet_vehicle_register_registration"),
    )
    op.create_index(op.f("ix_fleet_vehicle_register_id"), "fleet_vehicle_register", ["id"], unique=False)
    op.create_index(
        op.f("ix_fleet_vehicle_register_registration_number"),
        "fleet_vehicle_register",
        ["registration_number"],
        unique=True,
    )

    op.add_column("fleet_hire_vehicle", sa.Column("hire_start_time", sa.String(length=20), nullable=True))

    vehicle_register = sa.table(
        "fleet_vehicle_register",
        sa.column("registration_number", sa.String),
        sa.column("make", sa.String),
        sa.column("model", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        vehicle_register,
        [
            {"registration_number": "WX17VHA", "make": "TOYOTA", "model": "AURIS ICON TSS HYBRID", "is_active": False},
            {"registration_number": "F150FORD", "make": "FORD", "model": "F150", "is_active": False},
            {"registration_number": "AB12CDE", "make": "VOLKSWAGEN", "model": "PASSAT SE BUSINESS", "is_active": True},
            {"registration_number": "HJ19KLM", "make": "MERCEDES-BENZ", "model": "E220 AMG LINE", "is_active": False},
            {"registration_number": "PK68ZZZ", "make": "BMW", "model": "520D M SPORT", "is_active": True},
            {"registration_number": "LN21TAX", "make": "SKODA", "model": "SUPERB SE L", "is_active": False},
            {"registration_number": "YT20CAB", "make": "KIA", "model": "NIRO 2 HYBRID", "is_active": False},
        ],
    )


def downgrade() -> None:
    op.drop_column("fleet_hire_vehicle", "hire_start_time")
    op.drop_index(op.f("ix_fleet_vehicle_register_registration_number"), table_name="fleet_vehicle_register")
    op.drop_index(op.f("ix_fleet_vehicle_register_id"), table_name="fleet_vehicle_register")
    op.drop_table("fleet_vehicle_register")
