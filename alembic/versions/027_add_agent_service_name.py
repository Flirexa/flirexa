"""Add agent_service_name to servers — supports per-interface multi-agent installs

Revision ID: 027_add_agent_service_name
Revises: 026_add_ipv4_only
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa

revision = "027_add_agent_service_name"
down_revision = "026_add_ipv4_only"
branch_labels = None
depends_on = None


def upgrade():
    # NULL = legacy single-instance install (vpnmanager-agent.service).
    # Existing rows stay NULL — uninstall code uses that as a sentinel and
    # falls back to the legacy unit name. New installs get filled in by
    # server_manager.install_agent after a successful bootstrap.
    op.add_column(
        "servers",
        sa.Column(
            "agent_service_name",
            sa.String(length=64),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("servers", "agent_service_name")
