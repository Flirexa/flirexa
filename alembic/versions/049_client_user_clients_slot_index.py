"""index client_user_clients.slot_id

Revision ID: 049_cuc_slot_idx
Revises: 048_client_segments
Create Date: 2026-06-22

Adds an index on ``client_user_clients.slot_id``. This link table is the
busiest in the schema — ``slot_id IN (...)`` is filtered on nearly every
authenticated customer request (``/devices``, ``/subscription``, slot heal /
peer lookups) — yet ``slot_id`` had no index. The only existing index was the
``UNIQUE(client_user_id, client_id)`` constraint, which can prefix-serve
``client_user_id`` lookups but does nothing for ``slot_id`` filters, so those
were full scans of the table.

Purely additive (a new index). No data change; safe to run on a live DB — the
table is small relative to the peer tables and the create is brief.
"""
from alembic import op
import sqlalchemy as sa


revision = "049_cuc_slot_idx"
down_revision = "048_client_segments"
branch_labels = None
depends_on = None

_INDEX = "ix_cuc_slot_id"
_TABLE = "client_user_clients"


def _has_index(bind) -> bool:
    insp = sa.inspect(bind)
    if _TABLE not in insp.get_table_names():
        return True  # nothing to index (fresh/odd schema) — treat as done
    return any(ix["name"] == _INDEX for ix in insp.get_indexes(_TABLE))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_index(bind):
        op.create_index(_INDEX, _TABLE, ["slot_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if _TABLE in insp.get_table_names() and any(
        ix["name"] == _INDEX for ix in insp.get_indexes(_TABLE)
    ):
        op.drop_index(_INDEX, table_name=_TABLE)
