"""Migrate AmneziaWG config_path to /etc/amnezia/amneziawg/

Versions before 1.4.68 wrote the AmneziaWG config to /etc/amneziawg/<iface>.conf,
but awg-quick from ppa:amnezia/ppa actually looks at /etc/amnezia/amneziawg/<iface>.conf
(note the extra "amnezia/" segment). Existing rows with the old path can't be
started without manual fixup; this migration rewrites them in place.

Only touches rows under the legacy directory; rows pointing at custom paths
(e.g. Docker-mounted volumes like /opt/amneziawg/config/awg0.conf) are left
untouched.

Revision ID: 025_awg_config_path
Revises: 024_add_server_display_name
Create Date: 2026-04-29
"""

from alembic import op


revision = "025_awg_config_path"
down_revision = "024_add_server_display_name"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE servers
           SET config_path = REPLACE(config_path, '/etc/amneziawg/', '/etc/amnezia/amneziawg/')
         WHERE server_type = 'amneziawg'
           AND config_path LIKE '/etc/amneziawg/%'
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE servers
           SET config_path = REPLACE(config_path, '/etc/amnezia/amneziawg/', '/etc/amneziawg/')
         WHERE server_type = 'amneziawg'
           AND config_path LIKE '/etc/amnezia/amneziawg/%'
        """
    )
