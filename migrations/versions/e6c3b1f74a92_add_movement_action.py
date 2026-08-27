"""add MOVEMENT to casehistoryactiontype

Movement (MO) — an on/off-hire vehicle movement on a fleet hire (vehicle placed
on hire / off-hired), auto-logged to History. Mirrors the "MO" rows in the legacy
Skyline system.

Revision ID: e6c3b1f74a92
Revises: d5a9f2c17e64
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e6c3b1f74a92'
down_revision: Union[str, None] = 'd5a9f2c17e64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE casehistoryactiontype ADD VALUE IF NOT EXISTS 'MOVEMENT'")


def downgrade() -> None:
    # Postgres cannot drop a single enum label; leaving it is harmless.
    pass
