"""Add proxy protocol support: server_category, Hysteria2, TUIC fields

Revision ID: 013
Revises: 012
Create Date: 2026-03-24

Changes:
  servers:
    - server_category  VARCHAR(20) NOT NULL DEFAULT 'vpn'
    - proxy_domain     VARCHAR(255) nullable
    - proxy_tls_mode   VARCHAR(20)  nullable  (self_signed | acme | manual)
    - proxy_cert_path  VARCHAR(255) nullable
    - proxy_key_path   VARCHAR(255) nullable
    - proxy_config_path VARCHAR(255) nullable
    - proxy_service_name VARCHAR(100) nullable
    - proxy_obfs_password VARCHAR(255) nullable  (Hysteria2 OBFS)
  clients:
    - proxy_password  TEXT nullable (encrypted at ORM layer)
    - proxy_uuid      VARCHAR(36) nullable (TUIC UUID auth)
    - ip_index → nullable (proxy clients have no VPN IP)
    - ipv4     → nullable (proxy clients have no VPN IP)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    # ── servers table ─────────────────────────────────────────────────────────

    existing_server_cols = {c['name'] for c in inspector.get_columns('servers')}

    if 'server_category' not in existing_server_cols:
        op.add_column('servers', sa.Column(
            'server_category', sa.String(20), nullable=False, server_default='vpn'
        ))
        # Back-fill from server_type
        conn.execute(text(
            "UPDATE servers SET server_category = 'vpn' "
            "WHERE server_type IN ('wireguard', 'amneziawg')"
        ))

    for col_name, col_def in [
        ('proxy_domain',         sa.String(255)),
        ('proxy_tls_mode',       sa.String(20)),
        ('proxy_cert_path',      sa.String(255)),
        ('proxy_key_path',       sa.String(255)),
        ('proxy_config_path',    sa.String(255)),
        ('proxy_service_name',   sa.String(100)),
        ('proxy_obfs_password',  sa.String(255)),
    ]:
        if col_name not in existing_server_cols:
            op.add_column('servers', sa.Column(col_name, col_def, nullable=True))

    # ── clients table ─────────────────────────────────────────────────────────

    existing_client_cols = {c['name'] for c in inspector.get_columns('clients')}

    if 'proxy_password' not in existing_client_cols:
        op.add_column('clients', sa.Column('proxy_password', sa.Text(), nullable=True))

    if 'proxy_uuid' not in existing_client_cols:
        op.add_column('clients', sa.Column('proxy_uuid', sa.String(36), nullable=True))

    # Make ip_index nullable so proxy clients (no VPN IP) can exist
    op.alter_column('clients', 'ip_index',
                    existing_type=sa.Integer(),
                    nullable=True)

    # Make ipv4 nullable for the same reason
    op.alter_column('clients', 'ipv4',
                    existing_type=sa.String(20),
                    nullable=True)


def downgrade():
    # Restore NOT NULL (only safe if no proxy clients exist)
    op.alter_column('clients', 'ipv4',
                    existing_type=sa.String(20),
                    nullable=False)
    op.alter_column('clients', 'ip_index',
                    existing_type=sa.Integer(),
                    nullable=False)

    for col in ('proxy_uuid', 'proxy_password'):
        op.drop_column('clients', col)

    for col in ('proxy_obfs_password', 'proxy_service_name', 'proxy_config_path',
                'proxy_key_path', 'proxy_cert_path', 'proxy_tls_mode',
                'proxy_domain', 'server_category'):
        op.drop_column('servers', col)
