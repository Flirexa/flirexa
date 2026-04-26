"""expand update status enum for stage1 lifecycle

Revision ID: 020_expand_update_status_enum
Revises: 019_stage1_update_hardening
Create Date: 2026-03-27
"""

from alembic import op


revision = "020_expand_update_status_enum"
down_revision = "019_stage1_update_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE updatestatus ADD VALUE IF NOT EXISTS 'DOWNLOADED'")
    op.execute("ALTER TYPE updatestatus ADD VALUE IF NOT EXISTS 'VERIFIED'")
    op.execute("ALTER TYPE updatestatus ADD VALUE IF NOT EXISTS 'READY_TO_APPLY'")
    op.execute("ALTER TYPE updatestatus ADD VALUE IF NOT EXISTS 'ROLLBACK_REQUIRED'")


def downgrade() -> None:
    # PostgreSQL enums cannot safely drop values in-place.
    pass
