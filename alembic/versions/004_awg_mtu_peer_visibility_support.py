"""awg_mtu and supports_peer_visibility on servers

Revision ID: 004
Revises: 003
Create Date: 2026-03-14
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa


revision: str = '004'
down_revision: Union[str, Sequence[str], None] = '003'
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
    # awg_mtu — nullable integer (None = use default: 1280 for AWG, 1420 for WG)
    if not _has_column('servers', 'awg_mtu'):
        op.add_column('servers', sa.Column('awg_mtu', sa.Integer(), nullable=True))

    # supports_peer_visibility — boolean, default True
    if not _has_column('servers', 'supports_peer_visibility'):
        op.add_column('servers', sa.Column(
            'supports_peer_visibility', sa.Boolean(), nullable=False, server_default='true'
        ))


def downgrade() -> None:
    op.drop_column('servers', 'awg_mtu')
    op.drop_column('servers', 'supports_peer_visibility')
