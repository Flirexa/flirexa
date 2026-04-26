"""add features column to subscription_plans

Revision ID: 011
Revises: 010
Create Date: 2026-03-16
"""
from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision: str = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Check if the table exists first (it's created by client_portal_main.py, may not exist yet)
    tables = inspect(bind).get_table_names()
    if 'subscription_plans' not in tables:
        return  # Table will be created with the column by Base.metadata.create_all()
    cols = {c['name'] for c in inspect(bind).get_columns('subscription_plans')}
    if 'features' not in cols:
        op.add_column('subscription_plans', sa.Column('features', sa.JSON, nullable=True))


def downgrade():
    op.drop_column('subscription_plans', 'features')
