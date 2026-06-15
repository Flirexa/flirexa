"""per-platform customer visibility on servers

Revision ID: 046_platform_vis
Revises: 045_pricing_tiers
Create Date: 2026-06-08

Adds two boolean columns to `servers`:

  - customer_visible_mobile    default TRUE
  - customer_visible_windows   default TRUE

Both default to TRUE so existing rows behave exactly as before — the
new toggles are opt-OUT. Operator (2026-06-08) wants to hide
bandwidth-heavy servers from desktop clients (where users consume an
order of magnitude more traffic than on mobile) without losing those
servers for the mobile audience, or vice versa.

The detection of which platform a customer-portal request belongs to
lives in `src/api/routes/client_portal.py` as `_is_windows_app` /
`_is_mobile_app`, layered on top of the existing
`_is_client_app_request` (X-Client-App header + User-Agent prefix).
"""
from alembic import op
import sqlalchemy as sa


revision = "046_platform_vis"
down_revision = "045_pricing_tiers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "servers",
        sa.Column(
            "customer_visible_mobile",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "servers",
        sa.Column(
            "customer_visible_windows",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("servers", "customer_visible_windows")
    op.drop_column("servers", "customer_visible_mobile")
