"""device_slots: add device_bound_at + device_last_seen_at for stale-bind auto-release

Revision ID: 043_device_slot_bind_timestamps
Revises: 042_app_features_batch
Create Date: 2026-05-31

Background: device slots could remain locked after the app lost its local
identifier or after an update. The original device-bind was binary — once
the slot's ``device_id``
was set, any other device id was hard-403'd forever, with no path
to recover other than the admin clicking Release. expo-secure-store
losing the cached UUID on Android (force-close mid-write,
keystore reset, OS app-data wipe) was enough to permanently brick
the slot until manual intervention.

Fix: stamp ``device_bound_at`` when a slot first binds and
``device_last_seen_at`` on every matched wg-quick fetch. The
``get_slot_config`` endpoint now silently rebinds when a mismatching
device_id arrives AND the old bind hasn't been seen in
``STALE_BIND_MINUTES`` (5 minutes — short enough that a real
two-customer-sharing-one-account scenario still bumps the heartbeat,
long enough that a force-close-reopen cycle clears cleanly).

Backfills are unnecessary; both columns default to NULL on existing
rows. Existing bound slots get treated as "bound but never seen" on
the first new request — the bind still enforces, the timestamp gets
set then.
"""

from alembic import op
import sqlalchemy as sa


revision = "043_device_slot_bind_timestamps"
down_revision = "042_app_features_batch"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "device_slots",
        sa.Column("device_bound_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "device_slots",
        sa.Column("device_last_seen_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column("device_slots", "device_last_seen_at")
    op.drop_column("device_slots", "device_bound_at")
