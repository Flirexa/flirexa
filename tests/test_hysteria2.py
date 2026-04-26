import os
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_ENABLED"] = "false"
os.environ["SMTP_ENABLED"] = "false"
os.environ["LICENSE_CHECK_ENABLED"] = "false"

from src.api.routes.clients import download_client_config, get_client_config
from src.database.models import Base, Client, ClientStatus, Server
from src.core.hysteria2 import Hysteria2Manager


def test_discover_reads_password_auth_mode():
    mgr = Hysteria2Manager(
        ssh_host="1.2.3.4",
        ssh_password="secret",
    )
    mgr.is_installed = MagicMock(return_value=True)
    mgr._find_service_name = MagicMock(return_value="hysteria-server")
    mgr._extract_config_from_unit = MagicMock(return_value="/etc/hysteria/config.yaml")
    mgr._read_file = MagicMock(return_value="""
listen: :8443
tls:
  cert: /etc/hysteria/server.crt
  key: /etc/hysteria/server.key
auth:
  type: password
  password: shared-server-password
obfs:
  type: salamander
  salamander:
    password: obfs-secret
""")
    mgr.is_service_active = MagicMock(return_value=True)

    result = mgr.discover()

    assert result["found"] is True
    assert result["auth_type"] == "password"
    assert result["auth_password"] == "shared-server-password"
    assert result["obfs_password"] == "obfs-secret"
    assert result["existing_users"] == []


@pytest.mark.asyncio
async def test_proxy_client_config_endpoints_use_server_auth_password():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    server = Server(
        name="hy2-test",
        interface="proxy-hys0",
        endpoint="127.0.0.1:8443",
        listen_port=8443,
        public_key="0" * 44,
        private_key="0" * 44,
        address_pool_ipv4="10.66.66.0/24",
        dns="1.1.1.1",
        max_clients=250,
        server_type="hysteria2",
        server_category="proxy",
        proxy_tls_mode="self_signed",
        proxy_config_path="/etc/hysteria/config.yaml",
        proxy_service_name="hysteria-server",
        proxy_obfs_password="obfs-secret",
        proxy_auth_password="server-shared-password",
    )
    db.add(server)
    db.commit()
    db.refresh(server)

    client = Client(
        name="Alice Phone",
        server_id=server.id,
        public_key=None,
        private_key=None,
        preshared_key=None,
        ip_index=None,
        ipv4=None,
        ipv6=None,
        enabled=True,
        status=ClientStatus.ACTIVE,
        proxy_password="client-specific-password",
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    client_id = client.id
    data = await get_client_config(client_id, db)
    assert data["protocol"] == "hysteria2"
    assert data["uri"].startswith("hysteria2://server-shared-password@127.0.0.1:8443/")
    assert "auth: server-shared-password" in data["config_text"]
    assert "client-specific-password" not in data["config_text"]

    download = await download_client_config(client_id, db)
    assert download.headers["content-disposition"] == "attachment; filename=Alice Phone.yaml"
    assert "auth: server-shared-password" in download.body.decode()
    assert "client-specific-password" not in download.body.decode()

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
