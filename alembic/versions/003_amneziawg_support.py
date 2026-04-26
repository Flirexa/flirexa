"""amneziawg support — server_type, awg obfuscation params, peer_visibility

Revision ID: 003
Revises: 002
Create Date: 2026-03-14
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa


revision: str = '003'
down_revision: Union[str, Sequence[str], None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return True
    columns = [c['name'] for c in insp.get_columns(table)]
    return column in columns


def upgrade() -> None:
    # servers: server_type
    if not _has_column('servers', 'server_type'):
        op.add_column('servers', sa.Column(
            'server_type', sa.String(20), nullable=False, server_default='wireguard'
        ))

    # servers: awg obfuscation params
    for col in ['awg_jc', 'awg_jmin', 'awg_jmax', 'awg_s1', 'awg_s2',
                'awg_h1', 'awg_h2', 'awg_h3', 'awg_h4']:
        if not _has_column('servers', col):
            op.add_column('servers', sa.Column(col, sa.Integer(), nullable=True))

    # clients: peer_visibility
    if not _has_column('clients', 'peer_visibility'):
        op.add_column('clients', sa.Column(
            'peer_visibility', sa.Boolean(), nullable=False, server_default='false'
        ))


def downgrade() -> None:
    # Remove in reverse order
    for col in ['awg_h4', 'awg_h3', 'awg_h2', 'awg_h1',
                'awg_s2', 'awg_s1', 'awg_jmax', 'awg_jmin', 'awg_jc', 'server_type']:
        op.drop_column('servers', col)
    op.drop_column('clients', 'peer_visibility')
