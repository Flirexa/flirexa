"""add permissions column to admin_users

Revision ID: 021_admin_user_permissions
Revises: 020_expand_update_status_enum
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa

revision = '021_admin_user_permissions'
down_revision = '020_expand_update_status_enum'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('admin_users', sa.Column('permissions', sa.Text(), nullable=True))
    # Default: NULL means no restrictions (admin level) / empty list means no permissions (manager)
    # Also ensure is_active column exists (may be missing on older installs)
    try:
        op.add_column('admin_users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    except Exception:
        pass  # column may already exist


def downgrade():
    op.drop_column('admin_users', 'permissions')
