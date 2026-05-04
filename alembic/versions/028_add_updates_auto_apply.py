"""Add updates_auto_apply system config — controls whether the panel
automatically applies updates from its configured channel.

Default behaviour is split:
  - Fresh install (empty client/server tables) → 'true'   (opt-out)
  - Upgrade from previous version (has data)   → 'false'  (opt-in)

The split is so existing customers don't get surprised by the panel
self-updating right after they upgrade to this release. New customers
who never saw the toggle get the modern auto-update default.

Revision ID: 028_updates_auto_apply
Revises: 027_add_agent_service_name
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa

revision = "028_updates_auto_apply"
down_revision = "027_add_agent_service_name"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    # Heuristic: if there's already operator data on this box, treat as
    # an upgrade (default OFF). Otherwise this is a fresh install (default ON).
    has_data = conn.execute(sa.text(
        "SELECT EXISTS(SELECT 1 FROM clients) "
        "OR EXISTS(SELECT 1 FROM servers WHERE id > 1)"
    )).scalar()
    default_value = 'false' if has_data else 'true'
    conn.execute(
        sa.text(
            "INSERT INTO system_config (key, value, value_type, description) "
            "VALUES ('updates_auto_apply', :v, 'bool', "
            "'Auto-apply updates from the configured channel') "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {'v': default_value},
    )


def downgrade():
    op.get_bind().execute(sa.text(
        "DELETE FROM system_config WHERE key = 'updates_auto_apply'"
    ))
