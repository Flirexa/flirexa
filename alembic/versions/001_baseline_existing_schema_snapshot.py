"""baseline: existing schema snapshot

This is a no-op migration that marks the starting point for Alembic.
All existing tables were created by SQLAlchemy's create_all() and
runtime _run_migrations() in connection.py.

For existing databases: run `alembic stamp 001` to mark as current.
For fresh installs: create_all() handles table creation, then stamp 001.

Revision ID: 001
Revises:
Create Date: 2026-03-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: baseline snapshot of existing schema."""
    pass


def downgrade() -> None:
    """No-op: cannot downgrade from baseline."""
    pass
