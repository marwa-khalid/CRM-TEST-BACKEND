"""engineer_companies master list (+ seed from Engr CSV)

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


# (company_name, address) — address is the two CSV address columns joined.
SEED = [
    ("Tec Engineers", "Repton House, Bretby Business Park"),
    ("IA Assesors Ltd", "6 Main Road, Hawkwell"),
    ("T7iple Se7en Assesso7s", ""),
    ("Sprint Assessors", "1 Cherrytree Crescent, Salford Priors"),
    ("Laird Assessors", "Whitfield Buildings, 188-200 Pensby Road"),
    ("Acorn Assessors Limited", "Acorn House, Bar Lane"),
    ("Adams Assesors", "39a Market Street, Stourbridge"),
    ("Test Engineer", "Test"),
    ("Hindle & Co Assessors Ltd", "99 Wellington Street, Stockport"),
    ("Western Assesors", "9 Church Gardens, Cockett"),
    ("Central Midland Assessors", "79 Imperial Rise, Coleshill"),
    ("Ace estimating ltd", "131 Roseberry Gardens, Upminster"),
]


def upgrade():
    op.create_table(
        "engineer_companies",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("postcode", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.Column("is_deleted", sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )

    engineer_companies = sa.table(
        "engineer_companies",
        sa.column("company_name", sa.String),
        sa.column("address", sa.String),
    )
    op.bulk_insert(
        engineer_companies,
        [{"company_name": n, "address": (a or None)} for n, a in SEED],
    )


def downgrade():
    op.drop_table("engineer_companies")
