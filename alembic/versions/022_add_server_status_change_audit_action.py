"""add SERVER_STATUS_CHANGE and missing uppercase audit action enum values

Revision ID: 022_fix_audit_action_enum
Revises: 021_admin_user_permissions
Create Date: 2026-04-05

Note: SQLAlchemy Enum(AuditAction) stores enum member NAMES (uppercase),
not values. The original enum was created with uppercase names.
Later migrations (002) added lowercase values (backup_create) which
would fail if those actions are ever used. This migration adds the
correct uppercase variants for all enum members that were missing.
"""

from alembic import op

revision = '022_fix_audit_action_enum'
down_revision = '021_admin_user_permissions'
branch_labels = None
depends_on = None


def upgrade():
    # Add uppercase name variants (what SQLAlchemy actually stores)
    for value in ('SERVER_STATUS_CHANGE', 'BACKUP_CREATE', 'BACKUP_RESTORE', 'BACKUP_DELETE'):
        op.execute(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{value}'")


def downgrade():
    # PostgreSQL does not support removing enum values
    pass
