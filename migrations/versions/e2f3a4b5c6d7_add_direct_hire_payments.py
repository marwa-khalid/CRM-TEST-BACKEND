"""add_direct_hire_payments

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-05-31 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'direct_hire_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.Integer(), nullable=False),
        sa.Column('date_settlement_received', sa.Date(), nullable=True),
        sa.Column('settlement_amount_received', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('is_deleted', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'],
            name='fk_direct_hire_payments_created_by', use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ['updated_by'], ['users.id'],
            name='fk_direct_hire_payments_updated_by', use_alter=True,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_direct_hire_payments_id', 'direct_hire_payments', ['id'], unique=False)
    op.create_index('ix_direct_hire_payments_claim_id', 'direct_hire_payments', ['claim_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_direct_hire_payments_claim_id', table_name='direct_hire_payments')
    op.drop_index('ix_direct_hire_payments_id', table_name='direct_hire_payments')
    op.drop_table('direct_hire_payments')
