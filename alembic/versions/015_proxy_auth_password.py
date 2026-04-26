"""add proxy_auth_password to servers

Revision ID: 015
Revises: 014
Create Date: 2026-03-24

Hysteria2 uses 'password' auth type (not 'userpass') for sing-box/Hiddify
compatibility. The server-level auth password is shared by all clients.
"""
from alembic import op
import sqlalchemy as sa

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    # Use raw SQL with IF NOT EXISTS — column may already exist if added manually
    op.execute(
        "ALTER TABLE servers ADD COLUMN IF NOT EXISTS proxy_auth_password VARCHAR(255)"
    )


def downgrade():
    op.drop_column('servers', 'proxy_auth_password')
