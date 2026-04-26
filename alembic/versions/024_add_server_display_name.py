"""Add display_name to servers for client portal display

Revision ID: 024_add_server_display_name
Revises: 023_backfill_corp_sites_features
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa

revision = "024_add_server_display_name"
down_revision = "023_backfill_corp_sites_features"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "servers",
        sa.Column("display_name", sa.String(length=100), nullable=True),
    )


def downgrade():
    op.drop_column("servers", "display_name")
