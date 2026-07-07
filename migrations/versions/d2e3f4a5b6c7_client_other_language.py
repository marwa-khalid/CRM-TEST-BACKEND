"""add other_language free-text column to client_details

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-07-03

Stores the custom language typed by the user when "Other" is selected as the
client's preferred language on the Client Details screen.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_details",
        sa.Column("other_language", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("client_details", "other_language")
