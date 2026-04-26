"""stage1 update hardening

Revision ID: 019_stage1_update_hardening
Revises: 018
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "019_stage1_update_hardening"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("update_history", sa.Column("channel", sa.String(length=16), nullable=True))
    op.add_column("update_history", sa.Column("progress_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("update_history", sa.Column("staging_path", sa.Text(), nullable=True))
    op.add_column("update_history", sa.Column("package_path", sa.Text(), nullable=True))
    op.add_column("update_history", sa.Column("previous_release_path", sa.Text(), nullable=True))
    op.add_column("update_history", sa.Column("db_backup_path", sa.Text(), nullable=True))
    op.add_column("update_history", sa.Column("db_backup_sha256", sa.String(length=64), nullable=True))
    op.add_column("update_history", sa.Column("db_backup_size", sa.BigInteger(), nullable=True))
    op.add_column("update_history", sa.Column("db_backup_valid", sa.Boolean(), nullable=True))
    op.add_column("update_history", sa.Column("last_step", sa.String(length=64), nullable=True))
    op.add_column("update_history", sa.Column("manifest_sha256", sa.String(length=64), nullable=True))
    op.add_column("update_history", sa.Column("package_sha256", sa.String(length=64), nullable=True))
    op.add_column("update_history", sa.Column("package_size", sa.BigInteger(), nullable=True))
    op.add_column("update_history", sa.Column("requires_migration", sa.Boolean(), nullable=True))
    op.add_column("update_history", sa.Column("requires_restart", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("update_history", "requires_restart")
    op.drop_column("update_history", "requires_migration")
    op.drop_column("update_history", "package_size")
    op.drop_column("update_history", "package_sha256")
    op.drop_column("update_history", "manifest_sha256")
    op.drop_column("update_history", "last_step")
    op.drop_column("update_history", "db_backup_valid")
    op.drop_column("update_history", "db_backup_size")
    op.drop_column("update_history", "db_backup_sha256")
    op.drop_column("update_history", "db_backup_path")
    op.drop_column("update_history", "previous_release_path")
    op.drop_column("update_history", "package_path")
    op.drop_column("update_history", "staging_path")
    op.drop_column("update_history", "progress_heartbeat_at")
    op.drop_column("update_history", "channel")
