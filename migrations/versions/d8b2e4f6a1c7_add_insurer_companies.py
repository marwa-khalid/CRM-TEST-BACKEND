"""add insurer_companies master table

Master list of client insurer / broker companies (name + address) that backs the
Company Name autocomplete on the Client Insurer & Broker screen — the insurer
equivalent of the existing `companies` (referrer) and `engineer_companies` tables.
Columns mirror `engineer_companies` exactly (Base + AuditByMixin shape).

Revision ID: d8b2e4f6a1c7
Revises: c7a1f2b3d4e5
Create Date: 2026-08-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd8b2e4f6a1c7'
down_revision: Union[str, None] = 'c7a1f2b3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS insurer_companies (
            id SERIAL PRIMARY KEY,
            company_name varchar(200),
            address varchar(300),
            postcode varchar(20),
            is_active boolean DEFAULT true,
            is_deleted boolean DEFAULT false,
            created_at timestamptz DEFAULT now(),
            updated_at timestamptz DEFAULT now(),
            created_by integer,
            updated_by integer
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_insurer_companies_id ON insurer_companies (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_insurer_companies_created_by ON insurer_companies (created_by)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_insurer_companies_updated_by ON insurer_companies (updated_by)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_insurer_companies_updated_by")
    op.execute("DROP INDEX IF EXISTS ix_insurer_companies_created_by")
    op.execute("DROP INDEX IF EXISTS ix_insurer_companies_id")
    op.execute("DROP TABLE IF EXISTS insurer_companies")
