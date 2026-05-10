"""device_limit_events — audit trail for device-limit decisions

Revision ID: 031_device_events
Revises: 030_share_tokens
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa


revision = "031_device_events"
down_revision = "030_share_tokens"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "device_limit_events" in insp.get_table_names():
        # Idempotent — earlier partial run created the table but didn't
        # update alembic_version. Don't blow up.
        return
    op.create_table(
        "device_limit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(64), nullable=True),
        sa.Column("max_devices", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_devices", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )


def downgrade():
    op.drop_table("device_limit_events")
