"""add update_history table

Revision ID: 009
Revises: 008
Create Date: 2026-03-14
"""
from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision: str = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = inspect(bind).get_table_names()
    if 'update_history' not in tables:
        op.create_table(
            'update_history',
            sa.Column('id',               sa.Integer,  primary_key=True, autoincrement=True),
            sa.Column('from_version',     sa.String(32), nullable=False),
            sa.Column('to_version',       sa.String(32), nullable=False),
            sa.Column('update_type',      sa.String(16), nullable=True),
            sa.Column('status',           sa.String(32), nullable=False, default='pending'),
            sa.Column('started_at',       sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('completed_at',     sa.DateTime(timezone=True), nullable=True),
            sa.Column('duration_seconds', sa.Float,    nullable=True),
            sa.Column('started_by',       sa.String(128), nullable=False, default='admin'),
            sa.Column('rollback_available', sa.Boolean, nullable=False, default=False),
            sa.Column('backup_path',      sa.Text,     nullable=True),
            sa.Column('is_rollback',      sa.Boolean,  nullable=False, default=False),
            sa.Column('rollback_of_id',   sa.Integer,  sa.ForeignKey('update_history.id'), nullable=True),
            sa.Column('error_message',    sa.Text,     nullable=True),
            sa.Column('log',              sa.Text,     nullable=True),
            sa.Column('manifest_json',    sa.Text,     nullable=True),
        )
        op.create_index('ix_uh_status_started', 'update_history', ['status', 'started_at'])


def downgrade():
    op.drop_index('ix_uh_status_started', 'update_history')
    op.drop_table('update_history')
