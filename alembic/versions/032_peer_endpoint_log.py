"""peer_endpoint_log — endpoint observations for advisory key-sharing detection

Revision ID: 032_peer_endpoints
Revises: 031_device_events
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa


revision = "032_peer_endpoints"
down_revision = "031_device_events"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "peer_endpoint_log" in insp.get_table_names():
        return  # idempotent
    op.create_table(
        "peer_endpoint_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("client_id", sa.Integer(), nullable=False, index=True),
        sa.Column("server_id", sa.Integer(), nullable=False),
        sa.Column("endpoint_ip", sa.String(64), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )
    # Composite index for the "distinct endpoints in last N hours" query
    op.create_index(
        "ix_peer_endpoint_log_client_observed",
        "peer_endpoint_log",
        ["client_id", "observed_at"],
    )


def downgrade():
    op.drop_index("ix_peer_endpoint_log_client_observed", table_name="peer_endpoint_log")
    op.drop_table("peer_endpoint_log")
