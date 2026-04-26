"""consolidate runtime schema migrations

Replaces all runtime ALTER TABLE statements from connection.py _run_migrations().
All operations are idempotent — safe to run on databases at any state.

Revision ID: 002
Revises: 001
Create Date: 2026-03-08
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect, text
import sqlalchemy as sa


revision: str = '002'
down_revision: Union[str, Sequence[str], None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    """Check if column exists in table (idempotent helper)."""
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return True  # Table doesn't exist, skip
    columns = [c['name'] for c in insp.get_columns(table)]
    return column in columns


def upgrade() -> None:
    # -- servers: SSH and agent management columns --
    if not _has_column('servers', 'ssh_host'):
        op.add_column('servers', sa.Column('ssh_host', sa.String(255)))
    if not _has_column('servers', 'ssh_port'):
        op.add_column('servers', sa.Column('ssh_port', sa.Integer, server_default='22'))
    if not _has_column('servers', 'ssh_user'):
        op.add_column('servers', sa.Column('ssh_user', sa.String(50), server_default='root'))
    if not _has_column('servers', 'ssh_password'):
        op.add_column('servers', sa.Column('ssh_password', sa.Text))
    if not _has_column('servers', 'agent_mode'):
        op.add_column('servers', sa.Column('agent_mode', sa.String(10), server_default='ssh'))
    if not _has_column('servers', 'agent_url'):
        op.add_column('servers', sa.Column('agent_url', sa.String(255)))
    if not _has_column('servers', 'agent_api_key'):
        op.add_column('servers', sa.Column('agent_api_key', sa.Text))
    if not _has_column('servers', 'max_bandwidth_mbps'):
        op.add_column('servers', sa.Column('max_bandwidth_mbps', sa.Integer))

    # -- clients: make private_key nullable, add auto bandwidth columns --
    bind = op.get_bind()
    insp = inspect(bind)
    if 'clients' in insp.get_table_names():
        try:
            op.alter_column('clients', 'private_key', nullable=True)
        except Exception:
            pass  # Already nullable

    if not _has_column('clients', 'auto_bandwidth_limit'):
        op.add_column('clients', sa.Column('auto_bandwidth_limit', sa.Integer))
    if not _has_column('clients', 'auto_bandwidth_rule_id'):
        op.add_column('clients', sa.Column('auto_bandwidth_rule_id', sa.Integer))

    # -- traffic_rules: per-client rule binding --
    if not _has_column('traffic_rules', 'client_id'):
        op.add_column('traffic_rules', sa.Column(
            'client_id', sa.Integer,
            sa.ForeignKey('clients.id', ondelete='CASCADE')
        ))

    # -- client_portal_subscriptions: notification dedup, auto-renew --
    if not _has_column('client_portal_subscriptions', 'notification_sent_at'):
        op.add_column('client_portal_subscriptions', sa.Column(
            'notification_sent_at', sa.JSON, server_default='{}'
        ))
    if not _has_column('client_portal_subscriptions', 'auto_renew_failures'):
        op.add_column('client_portal_subscriptions', sa.Column(
            'auto_renew_failures', sa.Integer, server_default='0'
        ))

    # -- client_users: subscription token, password reset token --
    if not _has_column('client_users', 'subscription_token'):
        op.add_column('client_users', sa.Column(
            'subscription_token', sa.String(64), unique=True
        ))
    if not _has_column('client_users', 'subscription_token_created_at'):
        op.add_column('client_users', sa.Column(
            'subscription_token_created_at', sa.DateTime
        ))
    if not _has_column('client_users', 'password_reset_token'):
        op.add_column('client_users', sa.Column(
            'password_reset_token', sa.String(255)
        ))
    if not _has_column('client_users', 'password_reset_token_created_at'):
        op.add_column('client_users', sa.Column(
            'password_reset_token_created_at', sa.DateTime
        ))

    # -- AuditAction enum: add backup values --
    conn = op.get_bind()
    try:
        conn.execute(text("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'backup_create'"))
        conn.execute(text("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'backup_restore'"))
    except Exception:
        pass  # Values already exist or enum not present


def downgrade() -> None:
    """Downgrade is intentionally limited — dropping columns risks data loss.
    In practice, downgrade from this consolidation migration is not expected.
    """
    pass
