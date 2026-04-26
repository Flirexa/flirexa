"""encrypt wireguard private keys and preshared keys

Revision ID: 007
Revises: 006
Create Date: 2026-03-14
"""
from alembic import op
from sqlalchemy import text

revision: str = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    """Re-encrypt any existing plain-text WireGuard keys in-place.

    The EncryptedText TypeDecorator stores values as TEXT with an 'enc::' prefix.
    Legacy plain-text values are read transparently; this migration writes them
    back so all keys are encrypted at rest.
    """
    from src.database.encrypted_type import _fernet, _ENC_PREFIX

    bind = op.get_bind()

    # Encrypt Server.private_key
    rows = bind.execute(text("SELECT id, private_key FROM servers")).fetchall()
    for row in rows:
        val = row[1]
        if val and not val.startswith(_ENC_PREFIX):
            encrypted = _ENC_PREFIX + _fernet.encrypt(val.encode("utf-8")).decode("ascii")
            bind.execute(
                text("UPDATE servers SET private_key = :val WHERE id = :id"),
                {"val": encrypted, "id": row[0]},
            )

    # Encrypt Client.private_key and Client.preshared_key
    rows = bind.execute(text("SELECT id, private_key, preshared_key FROM clients")).fetchall()
    for row in rows:
        client_id, priv, psk = row[0], row[1], row[2]
        updates = {}
        if priv and not priv.startswith(_ENC_PREFIX):
            updates["private_key"] = _ENC_PREFIX + _fernet.encrypt(priv.encode("utf-8")).decode("ascii")
        if psk and not psk.startswith(_ENC_PREFIX):
            updates["preshared_key"] = _ENC_PREFIX + _fernet.encrypt(psk.encode("utf-8")).decode("ascii")
        if updates:
            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            updates["id"] = client_id
            bind.execute(
                text(f"UPDATE clients SET {set_clause} WHERE id = :id"),
                updates,
            )


def downgrade():
    # Keys are still stored as TEXT — we cannot reverse encryption safely.
    # Downgrade is a no-op; plain-text values remain readable via backward-compat logic.
    pass
