"""backfill corp_sites in subscription plan features

Revision ID: 023_backfill_corp_sites_features
Revises: 022_fix_audit_action_enum
Create Date: 2026-04-05

Fixes:
  - Existing plans could contain {"corp_networks": N} without "corp_sites".
  - Corporate VPN backend then fell back to a generic site cap, which made
    enterprise/corporate plans behave incorrectly.
"""

from alembic import op
from sqlalchemy import inspect, text

revision = "023_backfill_corp_sites_features"
down_revision = "022_fix_audit_action_enum"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = inspect(bind).get_table_names()
    if "subscription_plans" not in tables:
        return

    defaults = {
        "standard": '{"corp_sites": 5}',
        "pro": '{"corp_sites": 20}',
        "premium": '{"corp_sites": 20}',
        "business": '{"corp_sites": 20}',
        "enterprise": '{"corp_sites": 100}',
        "corporation": '{"corp_sites": 30}',
        "corporate": '{"corp_sites": 30}',
    }

    for tier, patch in defaults.items():
        bind.execute(
            text(
                """
                UPDATE subscription_plans
                SET features = (features::jsonb || CAST(:patch AS jsonb))
                WHERE LOWER(tier::text) = :tier
                  AND features IS NOT NULL
                  AND (features::jsonb ? 'corp_networks')
                  AND NOT (features::jsonb ? 'corp_sites')
                """
            ),
            {"tier": tier, "patch": patch},
        )


def downgrade():
    bind = op.get_bind()
    tables = inspect(bind).get_table_names()
    if "subscription_plans" not in tables:
        return

    bind.execute(
        text(
            """
            UPDATE subscription_plans
            SET features = (features::jsonb - 'corp_sites')
            WHERE features IS NOT NULL
              AND (features::jsonb ? 'corp_sites')
            """
        )
    )
