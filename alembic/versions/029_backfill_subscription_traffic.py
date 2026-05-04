"""Backfill NULL traffic counters on client_portal_subscriptions.

Older code paths created subscription rows via raw SQL or migration steps
that didn't set the BigInteger defaults, leaving `traffic_used_rx` /
`traffic_used_tx` as NULL. The python property `traffic_used_total_gb`
then crashed with `TypeError: unsupported operand type(s) for +:
'NoneType' and 'NoneType'`, which surfaced as a 500 on
`GET /api/v1/portal-users/{id}` and a "Server error, please try again"
toast in the panel's user-details modal.

The python property has been made None-safe in the same release, but
backfilling NULL → 0 here matches the column intent and prevents the
same crash from sneaking back in via any other code path that does
straight arithmetic on these columns.

Revision ID: 029_subs_traffic_zero
Revises: 028_updates_auto_apply
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa

revision = "029_subs_traffic_zero"
down_revision = "028_updates_auto_apply"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE client_portal_subscriptions "
        "SET traffic_used_rx = 0 WHERE traffic_used_rx IS NULL"
    ))
    conn.execute(sa.text(
        "UPDATE client_portal_subscriptions "
        "SET traffic_used_tx = 0 WHERE traffic_used_tx IS NULL"
    ))


def downgrade():
    # No reverse — we wouldn't want to introduce NULLs back.
    pass
