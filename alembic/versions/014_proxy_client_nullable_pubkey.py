"""Make Client.public_key nullable (proxy clients have no WG key)

Revision ID: 014
Revises: 013
Create Date: 2026-03-24

Proxy clients (Hysteria2, TUIC) do not have WireGuard public keys.
Previously a synthetic hex placeholder was stored to satisfy the NOT NULL
constraint.  This migration:
  1. Drops the NOT NULL constraint on clients.public_key
  2. Nullifies any existing proxy placeholder keys (identified by their
     server_category = 'proxy' join) so the DB reflects reality
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text, inspect

revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # Only alter if the column is currently NOT NULL
    inspector = inspect(bind)
    cols = {c["name"]: c for c in inspector.get_columns("clients")}
    pub_col = cols.get("public_key", {})

    if pub_col.get("nullable") is False:
        # Drop NOT NULL; keep the UNIQUE index intact
        op.alter_column("clients", "public_key", nullable=True,
                        existing_type=sa.String(44))

    # Null out synthetic proxy placeholder keys:
    # proxy clients joined via servers where server_category = 'proxy'.
    # The placeholder keys are hex strings that are exactly 44 chars and do NOT
    # look like valid base64 WireGuard keys (WG keys use base64 charset).
    # Safest: null all client keys whose server is a proxy server.
    bind.execute(text("""
        UPDATE clients c
           SET public_key = NULL
          FROM servers s
         WHERE c.server_id = s.id
           AND s.server_category = 'proxy'
           AND c.public_key IS NOT NULL
    """))


def downgrade():
    # Restore NOT NULL — requires that all rows have a non-null value.
    # Proxy clients will get a synthetic key back.
    bind = op.get_bind()
    import secrets
    # Re-fill NULL public_keys with unique hex placeholders
    rows = bind.execute(text("SELECT id FROM clients WHERE public_key IS NULL")).fetchall()
    for row in rows:
        placeholder = secrets.token_hex(22)
        bind.execute(
            text("UPDATE clients SET public_key = :k WHERE id = :id"),
            {"k": placeholder, "id": row[0]}
        )
    op.alter_column("clients", "public_key", nullable=False,
                    existing_type=sa.String(44))
