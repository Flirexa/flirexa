"""per-user promo redemption tracking

Revision ID: 047_promo_redempt
Revises: 046_platform_vis
Create Date: 2026-06-15

Adds a `promo_redemptions` table so a promo code can be redeemed at most once
per portal user. Before this, `/promo CODE` only checked the global
`promo_codes.used_count`, so a `days`-type code (which directly extends the
subscription) could be re-run by the same user N times for N× free days, and a
`percent` code could be spammed to exhaust a limited code's global budget.

Purely additive — a new table with a UNIQUE(promo_code_id, client_user_id)
constraint. No change to existing tables/rows, so existing installs behave
exactly as before until the new bot logic starts recording redemptions.
"""
from alembic import op
import sqlalchemy as sa


revision = "047_promo_redempt"
down_revision = "046_platform_vis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promo_redemptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "promo_code_id",
            sa.Integer(),
            sa.ForeignKey("promo_codes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_user_id",
            sa.Integer(),
            sa.ForeignKey("client_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "redeemed_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "promo_code_id", "client_user_id", name="uq_promo_redemption_user"
        ),
    )
    op.create_index(
        "ix_promo_redemptions_user", "promo_redemptions", ["client_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_promo_redemptions_user", table_name="promo_redemptions")
    op.drop_table("promo_redemptions")
