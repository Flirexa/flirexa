"""add persistent client-portal rate-limit counters

Revision ID: 052_portal_rate_limits
Revises: 051_vless_reality
"""
from alembic import op
import sqlalchemy as sa


revision = "052_portal_rate_limits"
down_revision = "051_vless_reality"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "portal_rate_limits",
        sa.Column("bucket_key", sa.String(length=128), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "request_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("bucket_key"),
    )
    op.create_index(
        "ix_portal_rate_limits_updated_at",
        "portal_rate_limits",
        ["updated_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_portal_rate_limits_updated_at",
        table_name="portal_rate_limits",
    )
    op.drop_table("portal_rate_limits")
