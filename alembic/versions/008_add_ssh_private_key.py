"""add ssh_private_key column to servers

Revision ID: 008
Revises: 007
Create Date: 2026-03-14
"""
from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision: str = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    """Add ssh_private_key column to servers table (encrypted TEXT, nullable)."""
    bind = op.get_bind()
    columns = [c['name'] for c in inspect(bind).get_columns('servers')]
    if 'ssh_private_key' not in columns:
        op.add_column('servers', sa.Column('ssh_private_key', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('servers', 'ssh_private_key')
