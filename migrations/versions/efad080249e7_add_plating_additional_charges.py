"""add_plating_additional_charges

Revision ID: efad080249e7
Revises: ab0fc81c4968
Create Date: 2026-05-28 15:20:39.097836

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'efad080249e7'
down_revision: Union[str, None] = 'ab0fc81c4968'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'plating_additional_charges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.Integer(), nullable=False),
        sa.Column('private_hire_plating_fee', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('private_hire_mot_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('total_plating_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('automatic', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('estate', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('additional_premium', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('additional_driver_charges', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('is_deleted', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'],
                                name='fk_plating_additional_charges_created_by', use_alter=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'],
                                name='fk_plating_additional_charges_updated_by', use_alter=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_plating_additional_charges_id', 'plating_additional_charges', ['id'], unique=False)
    op.create_index('ix_plating_additional_charges_claim_id', 'plating_additional_charges', ['claim_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_plating_additional_charges_claim_id', table_name='plating_additional_charges')
    op.drop_index('ix_plating_additional_charges_id', table_name='plating_additional_charges')
    op.drop_table('plating_additional_charges')
