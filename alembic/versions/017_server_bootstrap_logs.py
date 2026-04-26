"""Add server_bootstrap_logs table for persistent bootstrap task tracking

Revision ID: 017
Revises: 016
Create Date: 2026-03-26

Adds server_bootstrap_logs table:
  - task_id    VARCHAR(64)  — unique bootstrap task identifier (UUID from frontend)
  - server_id  INT FK       — associated server (nullable, SET NULL on delete)
  - status     VARCHAR(16)  — running / complete / failed / interrupted
  - logs       TEXT         — newline-joined log lines
  - error      TEXT         — error message if status=failed
  - created_at TIMESTAMPTZ
  - completed_at TIMESTAMPTZ
"""
from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "server_bootstrap_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("servers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("logs", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index("ix_sbl_task_id", "server_bootstrap_logs", ["task_id"])
    op.create_index("ix_sbl_server_id", "server_bootstrap_logs", ["server_id"])


def downgrade():
    op.drop_index("ix_sbl_server_id", table_name="server_bootstrap_logs")
    op.drop_index("ix_sbl_task_id", table_name="server_bootstrap_logs")
    op.drop_table("server_bootstrap_logs")
