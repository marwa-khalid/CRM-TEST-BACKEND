"""add INCOMING_EMAIL to casehistoryactiontype

Incoming Email (IE) is a distinct Case History action type from Send Email (SE):
dragged-in .eml/.msg imports and received Outlook emails are logged as IE, while
emails we send (incl. the engineer instruct letter) stay SE.

Revision ID: b3e7c1d92a45
Revises: f7d2a9c41e83
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b3e7c1d92a45'
down_revision: Union[str, None] = 'f7d2a9c41e83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE is idempotent with IF NOT EXISTS (Postgres 12+) and
    # cannot live inside a DO/plpgsql block, so it's issued directly. The enum's
    # labels are the CaseHistoryActionType member names, hence the uppercase label.
    op.execute("ALTER TYPE casehistoryactiontype ADD VALUE IF NOT EXISTS 'INCOMING_EMAIL'")


def downgrade() -> None:
    # Postgres cannot drop a single enum label; leaving the value in place is
    # harmless (no rows reference it after a rollback of the feature).
    pass
