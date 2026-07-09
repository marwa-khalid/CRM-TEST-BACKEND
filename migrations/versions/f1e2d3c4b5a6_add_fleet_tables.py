"""add fleet tables

Revision ID: f1e2d3c4b5a6
Revises: d5e6f7a8b9c0
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1e2d3c4b5a6'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fleet_hire',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('file_opened_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('file_closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('insurance_type', sa.String(length=100), nullable=True),
        sa.Column('rental_advisor', sa.String(length=200), nullable=True),
        sa.Column('current_position', sa.String(length=100), nullable=True),
        sa.Column('bank_name', sa.String(length=200), nullable=True),
        sa.Column('account_name', sa.String(length=200), nullable=True),
        sa.Column('sort_code', sa.String(length=20), nullable=True),
        sa.Column('account_number', sa.String(length=50), nullable=True),
        sa.Column('driver_name', sa.String(length=200), nullable=True),
        sa.Column('driver_address', sa.Text(), nullable=True),
        sa.Column('driver_postcode', sa.String(length=20), nullable=True),
        sa.Column('driver_email', sa.String(length=200), nullable=True),
        sa.Column('driver_telephone', sa.String(length=50), nullable=True),
        sa.Column('driver_mobile', sa.String(length=50), nullable=True),
        sa.Column('driving_licence_number', sa.String(length=100), nullable=True),
        sa.Column('national_insurance_number', sa.String(length=50), nullable=True),
        sa.Column('date_of_birth', sa.Date(), nullable=True),
        sa.Column('driving_licence_start', sa.Date(), nullable=True),
        sa.Column('driving_licence_end', sa.Date(), nullable=True),
        sa.Column('where_found', sa.String(length=100), nullable=True),
        sa.Column('privacy_notice_explained', sa.String(length=10), nullable=True),
        sa.Column('privacy_notice_date', sa.Date(), nullable=True),
        sa.Column('privacy_notice_method', sa.String(length=50), nullable=True),
        sa.Column('lawful_basis', sa.String(length=50), nullable=True),
        sa.Column('email_consent', sa.String(length=20), nullable=True),
        sa.Column('email_consent_date', sa.Date(), nullable=True),
        sa.Column('email_consent_method', sa.String(length=50), nullable=True),
        sa.Column('sms_consent', sa.String(length=20), nullable=True),
        sa.Column('phone_consent', sa.String(length=20), nullable=True),
        sa.Column('postal_consent', sa.String(length=20), nullable=True),
        sa.Column('reason_for_withdrawal', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_fleet_hire_created_by', use_alter=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_fleet_hire_updated_by', use_alter=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fleet_hire_id'), 'fleet_hire', ['id'], unique=False)
    op.create_index(op.f('ix_fleet_hire_tenant_id'), 'fleet_hire', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_fleet_hire_created_by'), 'fleet_hire', ['created_by'], unique=False)
    op.create_index(op.f('ix_fleet_hire_updated_by'), 'fleet_hire', ['updated_by'], unique=False)

    op.create_table(
        'fleet_hire_document',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('hire_id', sa.Integer(), nullable=False),
        sa.Column('doc_type', sa.String(length=50), nullable=False),
        sa.Column('filename', sa.String(length=300), nullable=True),
        sa.Column('s3_key', sa.String(length=500), nullable=True),
        sa.Column('file_url', sa.Text(), nullable=True),
        sa.Column('storage_backend', sa.String(length=50), nullable=True),
        sa.Column('received_on', sa.Date(), nullable=True),
        sa.Column('extracted_address', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['hire_id'], ['fleet_hire.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fleet_hire_document_id'), 'fleet_hire_document', ['id'], unique=False)
    op.create_index(op.f('ix_fleet_hire_document_hire_id'), 'fleet_hire_document', ['hire_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_fleet_hire_document_hire_id'), table_name='fleet_hire_document')
    op.drop_index(op.f('ix_fleet_hire_document_id'), table_name='fleet_hire_document')
    op.drop_table('fleet_hire_document')
    op.drop_index(op.f('ix_fleet_hire_updated_by'), table_name='fleet_hire')
    op.drop_index(op.f('ix_fleet_hire_created_by'), table_name='fleet_hire')
    op.drop_index(op.f('ix_fleet_hire_tenant_id'), table_name='fleet_hire')
    op.drop_index(op.f('ix_fleet_hire_id'), table_name='fleet_hire')
    op.drop_table('fleet_hire')
