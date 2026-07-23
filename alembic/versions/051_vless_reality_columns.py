"""add VLESS-Reality columns to servers

Revision ID: 051_vless_reality
Revises: 050_admin_superadmin_backfill
"""
from alembic import op
import sqlalchemy as sa

revision = "051_vless_reality"
down_revision = "050_admin_superadmin_backfill"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("servers") as b:
        b.add_column(sa.Column("proxy_reality_private_key", sa.String(120), nullable=True))
        b.add_column(sa.Column("proxy_reality_public_key", sa.String(120), nullable=True))
        b.add_column(sa.Column("proxy_reality_short_id", sa.String(32), nullable=True))


def downgrade():
    with op.batch_alter_table("servers") as b:
        b.drop_column("proxy_reality_short_id")
        b.drop_column("proxy_reality_public_key")
        b.drop_column("proxy_reality_private_key")
