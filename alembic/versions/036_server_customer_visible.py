"""servers.customer_visible — hide test servers from client portal

Revision ID: 036_srv_visible
Revises: 035_pm_upper
Create Date: 2026-05-18

`GET /client-portal/servers` listed every row in `servers`, so test boxes
and staging servers leaked into the customer's location picker the moment
an operator added them via the admin panel. Adding a `customer_visible`
boolean (default True so existing rows keep their current behaviour) lets
the admin gate which servers reach subscribers — flip from the Servers
card menu in the admin UI.
"""

from alembic import op
import sqlalchemy as sa


revision = "036_srv_visible"
down_revision = "035_pm_upper"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("servers")}
    if "customer_visible" not in cols:
        op.add_column(
            "servers",
            sa.Column(
                "customer_visible",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )


def downgrade():
    op.drop_column("servers", "customer_visible")
