"""add IMPORTED_FILE to casehistoryactiontype

Imported File (IF) — a document/file uploaded against a case or VM vehicle
(V5C, MOT certificate, plate receipt, service invoice, correspondence …),
logged to History and previewable. Distinct from SE / IE (emails).

Revision ID: d5a9f2c17e64
Revises: c4f1a8e26b90
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd5a9f2c17e64'
down_revision: Union[str, None] = 'c4f1a8e26b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE casehistoryactiontype ADD VALUE IF NOT EXISTS 'IMPORTED_FILE'")


def downgrade() -> None:
    # Postgres cannot drop a single enum label; leaving it is harmless.
    pass
