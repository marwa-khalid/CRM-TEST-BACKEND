"""add fleet_hire_payment_transaction table (split / part payments per week)

Each weekly schedule row can now hold multiple dated payments. Existing rows that
already have a paid_amount are backfilled as a single transaction so their history
is not empty after the upgrade.

Revision ID: fa0c1d2e3f45
Revises: f9b0c1d2e3f4
Create Date: 2026-07-15
"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "fa0c1d2e3f45"
down_revision: Union[str, None] = "f9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fleet_hire_payment_transaction",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("fleet_hire_payment.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("amount", sa.String(length=50), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("payment_time", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )

    # Backfill: turn each already-recorded weekly paid_amount into one transaction.
    payments = sa.table(
        "fleet_hire_payment",
        sa.column("id", sa.Integer),
        sa.column("paid_amount", sa.String),
        sa.column("payment_date", sa.Date),
        sa.column("payment_time", sa.String),
        sa.column("notes", sa.Text),
    )
    transactions = sa.table(
        "fleet_hire_payment_transaction",
        sa.column("payment_id", sa.Integer),
        sa.column("amount", sa.String),
        sa.column("payment_date", sa.Date),
        sa.column("payment_time", sa.String),
        sa.column("notes", sa.Text),
    )
    conn = op.get_bind()
    rows = conn.execute(
        sa.select(
            payments.c.id,
            payments.c.paid_amount,
            payments.c.payment_date,
            payments.c.payment_time,
            payments.c.notes,
        )
    ).fetchall()

    to_insert = []
    for row in rows:
        raw = (row.paid_amount or "").strip()
        if not raw:
            continue
        try:
            value = float(re.sub(r"[^0-9.\-]", "", raw) or 0)
        except ValueError:
            value = 0.0
        if value <= 0:
            continue
        to_insert.append(
            {
                "payment_id": row.id,
                "amount": raw,
                "payment_date": row.payment_date,
                "payment_time": row.payment_time,
                "notes": row.notes,
            }
        )
    if to_insert:
        op.bulk_insert(transactions, to_insert)


def downgrade() -> None:
    op.drop_table("fleet_hire_payment_transaction")
