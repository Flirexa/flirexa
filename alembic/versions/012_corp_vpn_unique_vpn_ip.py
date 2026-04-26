"""corporate VPN: unique (network_id, vpn_ip) + update default plan features

Revision ID: 012
Revises: 011
Create Date: 2026-03-17

Fixes:
  - Add UNIQUE constraint on (network_id, vpn_ip) in corporate_network_sites
    to prevent duplicate IPs from concurrent site-add requests.
  - Update subscription_plans features JSON to include corp_networks / corp_sites
    for plans that should have corporate VPN access (standard, premium, corp tiers).
"""
from alembic import op
from sqlalchemy import inspect, text
import sqlalchemy as sa

revision: str = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = inspect(bind).get_table_names()

    # 1. Add unique constraint on (network_id, vpn_ip)
    if 'corporate_network_sites' in tables:
        # Remove any existing duplicate vpn_ips (safety — should not exist)
        # before adding constraint (dedup by keeping the site with lower id)
        bind.execute(text("""
            DELETE FROM corporate_network_sites
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM corporate_network_sites
                GROUP BY network_id, vpn_ip
            )
        """))

        # Check if constraint already exists
        constraints = {c['name'] for c in inspect(bind).get_unique_constraints('corporate_network_sites')}
        if 'uq_corp_site_vpn_ip' not in constraints:
            op.create_unique_constraint(
                'uq_corp_site_vpn_ip',
                'corporate_network_sites',
                ['network_id', 'vpn_ip'],
            )

    # 2. Update default plan features for corp VPN access
    if 'subscription_plans' in tables:
        cols = {c['name'] for c in inspect(bind).get_columns('subscription_plans')}
        if 'features' in cols:
            # Only update plans that currently have NULL features (don't overwrite admin customisations)
            _plan_features = {
                # tier (lowercase)  : features JSON
                'standard':  '{"corp_networks": 1, "corp_sites": 5}',
                'pro':        '{"corp_networks": 3, "corp_sites": 20}',
                'premium':    '{"corp_networks": 3, "corp_sites": 20}',
                'business':   '{"corp_networks": 3, "corp_sites": 20}',
                'enterprise': '{"corp_networks": 10, "corp_sites": 100}',
                'corporation': '{"corp_networks": 5, "corp_sites": 30}',
                'corporate':  '{"corp_networks": 5, "corp_sites": 30}',
            }
            for tier, features_json in _plan_features.items():
                bind.execute(text("""
                    UPDATE subscription_plans
                    SET features = :features
                    WHERE LOWER(tier::text) = :tier AND (features IS NULL OR features::text = 'null')
                """), {'tier': tier, 'features': features_json})


def downgrade():
    bind = op.get_bind()
    tables = inspect(bind).get_table_names()
    if 'corporate_network_sites' in tables:
        op.drop_constraint('uq_corp_site_vpn_ip', 'corporate_network_sites', type_='unique')
