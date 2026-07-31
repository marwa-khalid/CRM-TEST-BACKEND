"""add module to tasks and calendar_events

Scopes tasks + calendar events to the app that owns them (skyline / vehicles /
claims) so Skyline and Vehicle Management have independent task lists, calendars
and notification feeds.

Revision ID: c7a1f2b3d4e5
Revises: b845db96e484
Create Date: 2026-08-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c7a1f2b3d4e5'
down_revision: Union[str, None] = 'b845db96e484'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS module varchar(30)")
    op.execute("ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS module varchar(30)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tasks_module ON tasks (module)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_calendar_events_module ON calendar_events (module)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tasks_module")
    op.execute("DROP INDEX IF EXISTS ix_calendar_events_module")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS module")
    op.execute("ALTER TABLE calendar_events DROP COLUMN IF EXISTS module")
