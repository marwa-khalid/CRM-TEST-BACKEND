# ums tables
# Revision ID: 7061118c828f
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '7061118c828f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1) Create tenants WITHOUT FKs to users (just the columns)
    op.create_table(
        'tenants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_tenants_name'), 'tenants', ['name'], unique=True)
    op.create_index(op.f('ix_tenants_created_by'), 'tenants', ['created_by'], unique=False)
    op.create_index(op.f('ix_tenants_updated_by'), 'tenants', ['updated_by'], unique=False)

    # 2) Create users (can safely reference tenants + self)
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_name', sa.String(), nullable=False),
        sa.Column('password', sa.String(), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=True),
        sa.Column('last_name', sa.String(length=100), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),  # self-FK is fine
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_user_name'), 'users', ['user_name'], unique=True)
    op.create_index(op.f('ix_users_created_by'), 'users', ['created_by'], unique=False)
    op.create_index(op.f('ix_users_updated_by'), 'users', ['updated_by'], unique=False)

    # 3) Now add the tenants → users FKs to close the loop
    op.create_foreign_key(
        'fk_tenants_created_by_users',
        source_table='tenants', referent_table='users',
        local_cols=['created_by'], remote_cols=['id'],
        ondelete='SET NULL'  # optional but recommended
    )
    op.create_foreign_key(
        'fk_tenants_updated_by_users',
        source_table='tenants', referent_table='users',
        local_cols=['updated_by'], remote_cols=['id'],
        ondelete='SET NULL'
    )

def downgrade() -> None:
    # drop FKs we added explicitly
    op.drop_constraint('fk_tenants_updated_by_users', 'tenants', type_='foreignkey')
    op.drop_constraint('fk_tenants_created_by_users', 'tenants', type_='foreignkey')

    # drop users then tenants (reverse order)
    op.drop_index(op.f('ix_users_updated_by'), table_name='users')
    op.drop_index(op.f('ix_users_created_by'), table_name='users')
    op.drop_index(op.f('ix_users_user_name'), table_name='users')
    op.drop_table('users')

    op.drop_index(op.f('ix_tenants_updated_by'), table_name='tenants')
    op.drop_index(op.f('ix_tenants_created_by'), table_name='tenants')
    op.drop_index(op.f('ix_tenants_name'), table_name='tenants')
    op.drop_table('tenants')
