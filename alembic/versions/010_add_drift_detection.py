"""add drift detection columns to servers

Revision ID: 010
Revises: 009
Create Date: 2026-03-15
"""
from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision: str = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = {c['name'] for c in inspect(bind).get_columns('servers')}

    if 'drift_detected' not in cols:
        op.add_column('servers', sa.Column('drift_detected', sa.Boolean, nullable=False,
                                           server_default='false'))
    if 'drift_details' not in cols:
        op.add_column('servers', sa.Column('drift_details', sa.Text, nullable=True))
    if 'drift_detected_at' not in cols:
        op.add_column('servers', sa.Column('drift_detected_at', sa.DateTime(timezone=True),
                                           nullable=True))
    if 'last_reconcile_at' not in cols:
        op.add_column('servers', sa.Column('last_reconcile_at', sa.DateTime(timezone=True),
                                           nullable=True))


def downgrade():
    op.drop_column('servers', 'last_reconcile_at')
    op.drop_column('servers', 'drift_detected_at')
    op.drop_column('servers', 'drift_details')
    op.drop_column('servers', 'drift_detected')
