"""add_abi_bhr_charges

Revision ID: 69720ad9bac5
Revises: efad080249e7
Create Date: 2026-05-28 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '69720ad9bac5'
down_revision: Union[str, None] = 'efad080249e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'abi_bhr_charges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.Integer(), nullable=False),
        sa.Column('payment_pack_raised_date', sa.Date(), nullable=True),
        sa.Column('payment_pack_sent_date', sa.Date(), nullable=True),
        sa.Column('invoice_number', sa.String(length=100), nullable=True),
        sa.Column('date_hire_paid', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('is_deleted', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'],
                                name='fk_abi_bhr_charges_created_by', use_alter=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'],
                                name='fk_abi_bhr_charges_updated_by', use_alter=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_abi_bhr_charges_id', 'abi_bhr_charges', ['id'], unique=False)
    op.create_index('ix_abi_bhr_charges_claim_id', 'abi_bhr_charges', ['claim_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_abi_bhr_charges_claim_id', table_name='abi_bhr_charges')
    op.drop_index('ix_abi_bhr_charges_id', table_name='abi_bhr_charges')
    op.drop_table('abi_bhr_charges')
