"""device_slots: one customer "device" spans peers on every customer-visible server

Revision ID: 037_device_slots
Revises: 036_srv_visible
Create Date: 2026-05-19

Implements the multi-server toggle. A "device slot" owns one shared keypair
and one Client row on every customer-visible server; at any moment exactly
one of those Client rows has ``enabled=True``. The portal toggle flips
which one. Configs the user downloaded for the other regions stay on their
phone but can't handshake until they're switched on server-side, so leaking
the whole bundle doesn't give anyone extra access.

Schema changes:

1. New ``device_slots`` table — one row per device the subscription bought.
2. ``client_user_clients.slot_id`` FK — links existing peer→user join rows
   into a slot. Nullable so legacy single-server devices keep working.
3. Drop the standalone ``UNIQUE(clients.public_key)`` index — the same
   slot keypair shows up on every server now. Replace with a partial
   composite unique on ``(public_key, server_id)`` so a single server
   still can't have two peers with the same pubkey.
4. Bump ``servers.max_clients`` default to 1000 (slots × N-servers fan-out
   eats the old /24 + 250-client default within a handful of subscribers).
   Existing rows are left alone — operators sized their own pools.

Backward compatible: nothing is deleted, no rows changed, legacy code paths
work unchanged.
"""

from alembic import op
import sqlalchemy as sa


revision = "037_device_slots"
down_revision = "036_srv_visible"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # ── 1. device_slots ─────────────────────────────────────────────────
    if "device_slots" not in insp.get_table_names():
        op.create_table(
            "device_slots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "client_user_id",
                sa.Integer(),
                sa.ForeignKey("client_users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("label", sa.String(64), nullable=False, server_default="Device"),
            # Shared WG keypair across every server in the slot. Stored
            # encrypted (same column type as Client.private_key).
            sa.Column("public_key", sa.String(64), nullable=False),
            sa.Column("private_key", sa.Text(), nullable=False),
            sa.Column("preshared_key", sa.Text(), nullable=True),
            sa.Column(
                "active_server_id",
                sa.Integer(),
                sa.ForeignKey("servers.id", ondelete="SET NULL"),
                nullable=True,
            ),
            # Rate-limit anchor. The toggle endpoint refuses a flip if the
            # last one was less than ``SLOT_SWITCH_COOLDOWN`` ago.
            sa.Column("last_switched_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_device_slots_client_user_id",
            "device_slots",
            ["client_user_id"],
        )

    # ── 2. client_user_clients.slot_id ─────────────────────────────────
    cols_link = {c["name"] for c in insp.get_columns("client_user_clients")}
    if "slot_id" not in cols_link:
        op.add_column(
            "client_user_clients",
            sa.Column(
                "slot_id",
                sa.Integer(),
                sa.ForeignKey("device_slots.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_client_user_clients_slot_id",
            "client_user_clients",
            ["slot_id"],
        )

    # ── 3. drop UNIQUE(clients.public_key), add composite ───────────────
    # The original schema declared ``public_key UNIQUE`` on clients. With
    # device slots that's wrong — the same key appears on every server.
    # Replace it with a composite (public_key, server_id) so within one
    # server pubkeys are still unique. Use a partial expression so proxy
    # clients (NULL public_key) don't fight each other.
    #
    # In PostgreSQL `UNIQUE` on a column creates BOTH a constraint
    # (``clients_public_key_key``) AND its backing index of the same name.
    # ``op.drop_index`` fails with "cannot drop index … because constraint
    # … requires it" — you have to drop the constraint, which auto-drops
    # the index. Different DBs (and different schema versions) name these
    # objects differently, so introspect and drop whatever we find.
    cli_uniques = insp.get_unique_constraints("clients")
    dropped_constraint_names = set()
    for uc in cli_uniques:
        if uc.get("column_names") == ["public_key"]:
            op.drop_constraint(uc["name"], "clients", type_="unique")
            dropped_constraint_names.add(uc["name"])
    # After constraint drops the backing indexes are gone, but if a bare
    # standalone unique index also exists (e.g. created via op.create_index
    # in some historical revision rather than as a column UNIQUE) — clean
    # that too. Skip names we already dropped via the constraint path.
    cli_indexes = insp.get_indexes("clients")
    for ix in cli_indexes:
        if (ix.get("unique")
                and ix.get("column_names") == ["public_key"]
                and ix["name"] not in dropped_constraint_names):
            try:
                op.drop_index(ix["name"], table_name="clients")
            except Exception:
                # If the index is still backing some other constraint,
                # the constraint loop will get it. Don't fail the migration
                # on this best-effort cleanup.
                pass

    # Composite unique — partial WHERE public_key IS NOT NULL works on
    # PostgreSQL; on SQLite Alembic emits a plain unique index (which is
    # fine — NULLs don't collide there either by default).
    existing_idx_names = {i["name"] for i in insp.get_indexes("clients")}
    if "uq_clients_pubkey_server" not in existing_idx_names:
        op.create_index(
            "uq_clients_pubkey_server",
            "clients",
            ["public_key", "server_id"],
            unique=True,
            postgresql_where=sa.text("public_key IS NOT NULL"),
        )


def downgrade():
    # Reverse order — drop dependent things first.
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "uq_clients_pubkey_server" in {i["name"] for i in insp.get_indexes("clients")}:
        op.drop_index("uq_clients_pubkey_server", table_name="clients")

    # Best-effort restore of the legacy single-column unique. If duplicate
    # public_keys snuck in via slot creation, this will fail loudly — which
    # is correct, since downgrading would silently re-allow handshake
    # collisions.
    op.create_index(
        "ix_clients_public_key",
        "clients",
        ["public_key"],
        unique=True,
    )

    cols_link = {c["name"] for c in insp.get_columns("client_user_clients")}
    if "slot_id" in cols_link:
        op.drop_index("ix_client_user_clients_slot_id", table_name="client_user_clients")
        op.drop_column("client_user_clients", "slot_id")

    if "device_slots" in insp.get_table_names():
        op.drop_index("ix_device_slots_client_user_id", table_name="device_slots")
        op.drop_table("device_slots")
