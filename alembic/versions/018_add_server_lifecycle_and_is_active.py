"""Add additive server lifecycle_status and is_active fields

Revision ID: 018
Revises: 017
Create Date: 2026-03-27
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "servers",
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="online"),
    )
    op.add_column(
        "servers",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.execute(
        """
        UPDATE servers
        SET lifecycle_status = CASE status
            WHEN 'ONLINE' THEN 'online'
            WHEN 'OFFLINE' THEN 'offline'
            WHEN 'MAINTENANCE' THEN 'degraded'
            WHEN 'ERROR' THEN 'failed'
            ELSE 'offline'
        END
        """
    )


def downgrade():
    op.drop_column("servers", "is_active")
    op.drop_column("servers", "lifecycle_status")
