"""client.customer_email — admin-side per-customer device grouping

Revision ID: 033_customer_email
Revises: 032_peer_endpoints
Create Date: 2026-05-10

Operators that don't use the client portal still need a way to enforce
"this customer can have at most N devices". The portal's max_devices lives
on ClientPortalSubscription; admin-only flows have no such anchor — the
admin just adds peers in a flat list. Adding a free-text customer_email
to clients gives the admin a way to tag peers as belonging to the same
real-world customer; enforcement counts existing peers with the same
non-null customer_email when creating a new one.

Indexed because the enforcement query runs on every POST /clients.
"""

from alembic import op
import sqlalchemy as sa


revision = "033_customer_email"
down_revision = "032_peer_endpoints"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("clients")}
    if "customer_email" not in cols:
        op.add_column(
            "clients",
            sa.Column("customer_email", sa.String(255), nullable=True),
        )
    # Idempotent index — skip if already created (rerun-safe).
    existing_indexes = {ix["name"] for ix in insp.get_indexes("clients")}
    if "ix_clients_customer_email" not in existing_indexes:
        op.create_index(
            "ix_clients_customer_email",
            "clients",
            ["customer_email"],
        )


def downgrade():
    op.drop_index("ix_clients_customer_email", table_name="clients")
    op.drop_column("clients", "customer_email")
