"""subscription_plans.pricing_tiers JSON column

Revision ID: 045_pricing_tiers
Revises: 044_pm_paylio
Create Date: 2026-06-06

Adds a `pricing_tiers` JSON column to `subscription_plans` so an
operator can define arbitrary (duration_days, price_usd, label) tuples
per plan instead of being limited to the hard-coded monthly /
quarterly / yearly trio.

Backward-compatible: when the column is NULL (or empty list), the
existing monthly/quarterly/yearly logic still runs. New plans created
through the admin can opt-in to richer tier ladders (2-month, 6-month,
2-year, multi-device tiers, trial periods, etc).
"""

from alembic import op
import sqlalchemy as sa


revision = "045_pricing_tiers"
down_revision = "044_pm_paylio"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # JSONB is searchable + indexable; safer than plain JSON.
        op.add_column(
            "subscription_plans",
            sa.Column("pricing_tiers", sa.dialects.postgresql.JSONB, nullable=True),
        )
    else:
        # SQLite + others: fall back to TEXT/JSON.
        op.add_column(
            "subscription_plans",
            sa.Column("pricing_tiers", sa.JSON, nullable=True),
        )


def downgrade():
    op.drop_column("subscription_plans", "pricing_tiers")
