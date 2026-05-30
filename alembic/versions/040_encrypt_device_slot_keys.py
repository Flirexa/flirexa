"""device_slots: re-encrypt private_key + preshared_key in place

Revision ID: 040_encrypt_slot_keys
Revises: 039_email_optional
Create Date: 2026-05-27

Before this migration `DeviceSlot.private_key` and `.preshared_key` were
plain `Text` columns — the slot's WireGuard secrets sat in the DB
unencrypted, even though the model comment claimed `EncryptedText`.

The model now uses `EncryptedText` for both fields. `EncryptedText`
transparently reads legacy plain-text rows, so the schema stays
`text`/`text` (no column-type change) — but we still want existing
rows re-written so a DB dump stops leaking raw secrets.

This migration loads every slot, runs each field through `EncryptedText`
on write (which is a regular UPDATE for SQLAlchemy — process_bind_param
encrypts), and commits. Idempotent: re-running on already-encrypted rows
leaves them in their encrypted-with-current-key form.

Downgrade is intentionally a no-op — going back would mean writing
plain text back, which is the bug we're fixing.
"""

from alembic import op
import sqlalchemy as sa


revision = "040_encrypt_slot_keys"
down_revision = "039_email_optional"
branch_labels = None
depends_on = None


def upgrade():
    # Load EncryptedText through the same path the app uses so the key
    # derivation matches at run time. Done inside the function body to
    # avoid alembic-stamping-without-running pulling in app code.
    from src.database.encrypted_type import EncryptedText

    bind = op.get_bind()

    slots_t = sa.Table(
        "device_slots",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("private_key", EncryptedText()),
        sa.Column("preshared_key", EncryptedText()),
    )

    rows = bind.execute(sa.select(
        slots_t.c.id, slots_t.c.private_key, slots_t.c.preshared_key,
    )).fetchall()

    for r in rows:
        # process_bind_param re-encrypts on UPDATE; legacy plain-text
        # rows become encrypted, already-encrypted rows are re-encrypted
        # with the current key (a no-op semantically).
        bind.execute(
            slots_t.update()
            .where(slots_t.c.id == r.id)
            .values(
                private_key=r.private_key,
                preshared_key=r.preshared_key,
            )
        )


def downgrade():
    # Intentional no-op — we don't want to re-introduce plain-text
    # secrets in the DB even on a rollback.
    pass
