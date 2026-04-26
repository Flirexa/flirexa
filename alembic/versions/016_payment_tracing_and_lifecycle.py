"""Add payment pipeline tracing fields

Revision ID: 016
Revises: 015_proxy_auth_password
Create Date: 2026-03-26

Adds to client_portal_payments:
  - trace_id        VARCHAR(64)  — human-readable pipeline trace identifier
  - pipeline_log    TEXT         — JSON array of pipeline step records
  - pipeline_status VARCHAR(20)  — "ok" | "inconsistent"
"""
from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if "client_portal_payments" not in insp.get_table_names():
        return

    columns = {c["name"] for c in insp.get_columns("client_portal_payments")}
    indexes = {idx["name"] for idx in insp.get_indexes("client_portal_payments")}

    with op.batch_alter_table("client_portal_payments", schema=None) as batch_op:
        if "trace_id" not in columns:
            batch_op.add_column(
                sa.Column("trace_id", sa.String(64), nullable=True)
            )
        if "pipeline_log" not in columns:
            batch_op.add_column(
                sa.Column("pipeline_log", sa.Text(), nullable=True)
            )
        if "pipeline_status" not in columns:
            batch_op.add_column(
                sa.Column("pipeline_status", sa.String(20), nullable=True, server_default="ok")
            )
        if "ix_cpp_trace_id" not in indexes:
            batch_op.create_index("ix_cpp_trace_id", ["trace_id"])


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if "client_portal_payments" not in insp.get_table_names():
        return

    columns = {c["name"] for c in insp.get_columns("client_portal_payments")}
    indexes = {idx["name"] for idx in insp.get_indexes("client_portal_payments")}

    with op.batch_alter_table("client_portal_payments", schema=None) as batch_op:
        if "ix_cpp_trace_id" in indexes:
            batch_op.drop_index("ix_cpp_trace_id")
        if "pipeline_status" in columns:
            batch_op.drop_column("pipeline_status")
        if "pipeline_log" in columns:
            batch_op.drop_column("pipeline_log")
        if "trace_id" in columns:
            batch_op.drop_column("trace_id")
