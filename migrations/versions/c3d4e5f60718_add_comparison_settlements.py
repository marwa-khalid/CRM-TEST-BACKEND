"""add_comparison_settlements

Revision ID: c3d4e5f60718
Revises: efad080249e7
Create Date: 2026-05-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f60718'
down_revision: Union[str, None] = '69720ad9bac5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'comparison_settlements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.Integer(), nullable=False),
        sa.Column('settlement_status', sa.String(200), nullable=True),
        sa.Column('abi_rate_band', sa.String(10), nullable=True),
        sa.Column('agreed_hire_days', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('agreed_hire_rate', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('agreed_storage_days', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('agreed_storage_rate', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('agreed_cdw_days', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('agreed_cdw_rate', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('agreed_additional_fees', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('agreed_penalties', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('vat_recovered', sa.Boolean(), nullable=True),
        sa.Column('reason_for_reduction', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('is_deleted', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'],
            name='fk_comparison_settlements_created_by', use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ['updated_by'], ['users.id'],
            name='fk_comparison_settlements_updated_by', use_alter=True,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_comparison_settlements_id', 'comparison_settlements', ['id'], unique=False)
    op.create_index('ix_comparison_settlements_claim_id', 'comparison_settlements', ['claim_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_comparison_settlements_claim_id', table_name='comparison_settlements')
    op.drop_index('ix_comparison_settlements_id', table_name='comparison_settlements')
    op.drop_table('comparison_settlements')
