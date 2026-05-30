"""servers: for_app_only / auto-hide tracking + fcm_tokens table

Revision ID: 042_app_features_batch
Revises: 041_device_slot_device_id
Create Date: 2026-05-30

Bundles four panel-side features requested by operators (2026-05-28):

1. ``servers.for_app_only`` — when True, the server is shown only to
   requests identified as the mobile/desktop app (X-Client-App header
   or Acme VPNVPN/* UA). Web portal users and subscription URL
   fetchers don't see it. Default False (existing rows behave as
   before).
2. ``servers.last_good_health_at`` — DATETIME timestamp updated by the
   health checker on every successful poll. Drives auto-hide.
3. ``servers.force_visible`` — admin override for auto-hide. When True,
   the server stays visible even if the last good health is older than
   the threshold. Default False (auto-hide enabled).
4. ``fcm_tokens`` — per-installation FCM device tokens for push
   notifications. One user can have many (one per install). The
   ``device_id`` field mirrors ``device_slots.device_id`` so the same
   X-Device-Id from the app maps a slot to its FCM token.

Downgrade strips columns and the table; rows are not migrated.
"""

from alembic import op
import sqlalchemy as sa


revision = "042_app_features_batch"
down_revision = "041_device_slot_device_id"
branch_labels = None
depends_on = None


def upgrade():
    # 1-3. servers extensions
    op.add_column(
        "servers",
        sa.Column(
            "for_app_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "servers",
        sa.Column("last_good_health_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "servers",
        sa.Column(
            "force_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # 4. fcm_tokens table — one row per (user, installation) pair.
    op.create_table(
        "fcm_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("client_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "device_id", name="uq_fcm_user_device"),
    )
    op.create_index("ix_fcm_tokens_user_id", "fcm_tokens", ["user_id"], unique=False)
    op.create_index("ix_fcm_tokens_device_id", "fcm_tokens", ["device_id"], unique=False)


def downgrade():
    op.drop_index("ix_fcm_tokens_device_id", table_name="fcm_tokens")
    op.drop_index("ix_fcm_tokens_user_id", table_name="fcm_tokens")
    op.drop_table("fcm_tokens")
    op.drop_column("servers", "force_visible")
    op.drop_column("servers", "last_good_health_at")
    op.drop_column("servers", "for_app_only")
