"""add split_tunnel_support to servers

Revision ID: 006
Revises: 005
Create Date: 2026-03-14
"""
from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision: str = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if 'servers' not in insp.get_table_names():
        return

    columns = {c['name'] for c in insp.get_columns('servers')}
    if 'split_tunnel_support' in columns:
        return

    op.add_column('servers', sa.Column(
        'split_tunnel_support', sa.Boolean(),
        nullable=False, server_default='false'
    ))


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if 'servers' not in insp.get_table_names():
        return

    columns = {c['name'] for c in insp.get_columns('servers')}
    if 'split_tunnel_support' not in columns:
        return

    op.drop_column('servers', 'split_tunnel_support')
