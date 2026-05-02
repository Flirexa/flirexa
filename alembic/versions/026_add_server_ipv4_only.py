"""Add ipv4_only flag to servers — strip IPv6 from generated client configs

Revision ID: 026_add_ipv4_only
Revises: 025_awg_config_path
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa

revision = "026_add_ipv4_only"
down_revision = "025_awg_config_path"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "servers",
        sa.Column(
            "ipv4_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("servers", "ipv4_only")
