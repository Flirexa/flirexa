"""device_slots: add device_id (Option B device-bind)

Revision ID: 041_device_slot_device_id
Revises: 040_encrypt_slot_keys
Create Date: 2026-05-28

Adds a nullable ``device_id`` column to ``device_slots``. NULL means
"unbound — first device to fetch wg-quick claims it". Once set, the
wg-quick endpoint (``GET /client-portal/devices/{slot_id}/config/{server_id}``)
rejects requests whose ``X-Device-Id`` header doesn't match. The
customer-facing release endpoint clears it so a user can re-bind from
a new phone.

We add an index because the column is queried in every wg-quick fetch
(`UPDATE device_slots SET device_id = :x WHERE id = :s AND device_id IS NULL`),
and we want the WHERE clause to use an index seek rather than a row
scan when slot tables grow.

Downgrade drops the index and the column. No data is migrated either
direction — existing rows simply start unbound, which is correct: any
phone that's already running with a slot will claim it on its next
connect (and from then on the bind enforces single-device).
"""

from alembic import op
import sqlalchemy as sa


revision = "041_device_slot_device_id"
down_revision = "040_encrypt_slot_keys"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "device_slots",
        sa.Column("device_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_device_slots_device_id",
        "device_slots",
        ["device_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_device_slots_device_id", table_name="device_slots")
    op.drop_column("device_slots", "device_id")
