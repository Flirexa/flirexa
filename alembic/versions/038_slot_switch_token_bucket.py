"""device_slots: token-bucket rate limit on region switches

Revision ID: 038_slot_tokens
Revises: 037_device_slots
Create Date: 2026-05-21

Replaces the fixed 30s post-switch cooldown with a token-bucket. Each
slot starts with 5 tokens; each switch consumes 1; tokens refill at one
per ``SLOT_SWITCH_REFILL_SECONDS_PER_TOKEN`` (default 6s). Lets a
customer burst-test a few regions in a row, still blocks a click-spammer
or a bot once the bucket empties.

``last_switched_at`` is kept as the refill anchor — the route layer reads
``(now - last_switched_at) / refill_seconds`` to compute how many tokens
have refilled since the previous switch, clamps to bucket size, and
either consumes one or rejects with 429.
"""

from alembic import op
import sqlalchemy as sa


revision = "038_slot_tokens"
down_revision = "037_device_slots"
branch_labels = None
depends_on = None


def upgrade():
    # Default 5.0 so existing slots start with a full bucket the first
    # time a customer hits the toggle after the upgrade — no surprise
    # 429s right after a deploy.
    op.add_column(
        "device_slots",
        sa.Column(
            "switch_tokens",
            sa.Float(),
            nullable=False,
            server_default="5.0",
        ),
    )


def downgrade():
    op.drop_column("device_slots", "switch_tokens")
