"""add_hire_payment_details

Revision ID: d1e2f3a4b5c6
Revises: c3d4e5f60718
Create Date: 2026-05-30 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c3d4e5f60718'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'hire_payment_details',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.Integer(), nullable=False),
        sa.Column('payment_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('received_date', sa.Date(), nullable=True),
        sa.Column('payment_reason', sa.Text(), nullable=True),
        sa.Column('payments_received_total', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('write_off_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('payment_outstanding_incl_vat', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('payment_outstanding_excl_vat', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('is_deleted', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'],
            name='fk_hire_payment_details_created_by', use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ['updated_by'], ['users.id'],
            name='fk_hire_payment_details_updated_by', use_alter=True,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_hire_payment_details_id', 'hire_payment_details', ['id'], unique=False)
    op.create_index('ix_hire_payment_details_claim_id', 'hire_payment_details', ['claim_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_hire_payment_details_claim_id', table_name='hire_payment_details')
    op.drop_index('ix_hire_payment_details_id', table_name='hire_payment_details')
    op.drop_table('hire_payment_details')
