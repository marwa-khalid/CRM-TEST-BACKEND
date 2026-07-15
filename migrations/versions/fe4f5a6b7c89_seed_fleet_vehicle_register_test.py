"""seed 15 test vehicles into fleet_vehicle_register

Adds a batch of test vehicles (distinct from the original 7 seeds) so the Hire
Vehicle Details registration dropdown has plenty to pick from. All start inactive.

Revision ID: fe4f5a6b7c89
Revises: fd3e4f5a6b78
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "fe4f5a6b7c89"
down_revision: Union[str, None] = "fd3e4f5a6b78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VEHICLES = [
    ("LM18ABC", "VAUXHALL", "ASTRA SRI", "Manual"),
    ("RK19DEF", "FORD", "FOCUS TITANIUM", "Manual"),
    ("SN20GHJ", "NISSAN", "QASHQAI ACENTA", "Automatic"),
    ("VE21KLN", "HYUNDAI", "TUCSON SE", "Automatic"),
    ("WB22MNP", "KIA", "SPORTAGE 2", "Manual"),
    ("YD23PQR", "TOYOTA", "COROLLA DESIGN", "Automatic"),
    ("BC18STU", "VOLKSWAGEN", "GOLF MATCH", "Manual"),
    ("GH19VWX", "AUDI", "A3 SPORT", "Automatic"),
    ("JK20XYZ", "BMW", "1 SERIES SE", "Automatic"),
    ("LP21ABD", "MERCEDES-BENZ", "A200 SPORT", "Automatic"),
    ("MR22CFG", "PEUGEOT", "3008 ALLURE", "Automatic"),
    ("NT23HJK", "RENAULT", "CLIO ICONIC", "Manual"),
    ("PV18LMN", "SKODA", "OCTAVIA SE", "Manual"),
    ("RW19PRS", "SEAT", "LEON FR", "Manual"),
    ("TZ20TUV", "HONDA", "CIVIC EX", "Automatic"),
]


def upgrade() -> None:
    vehicle_register = sa.table(
        "fleet_vehicle_register",
        sa.column("registration_number", sa.String),
        sa.column("make", sa.String),
        sa.column("model", sa.String),
        sa.column("transmission", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        vehicle_register,
        [
            {"registration_number": reg, "make": make, "model": model, "transmission": transmission, "is_active": False}
            for reg, make, model, transmission in _VEHICLES
        ],
    )


def downgrade() -> None:
    regs = tuple(v[0] for v in _VEHICLES)
    op.execute(
        sa.text("DELETE FROM fleet_vehicle_register WHERE registration_number IN :regs").bindparams(
            sa.bindparam("regs", value=regs, expanding=True)
        )
    )
