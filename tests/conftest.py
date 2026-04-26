"""
Shared test fixtures for SpongeBot tests
Uses SQLite in-memory database and mocked WireGuard commands
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Force SQLite before any imports that read DATABASE_URL
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_ENABLED"] = "false"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.models import Base, Server, Client, ClientStatus


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create a fresh database session for each test"""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def mock_wg_manager():
    """Create a mocked WireGuard manager"""
    wg = MagicMock()
    wg.generate_keypair.return_value = (
        "mFakePrivateKeyBase64EncodedXXXXXXXXXXXX=",
        "mFakePublicKeyBase64EncodedXXXXXXXXXXXXX=",
    )
    wg.generate_preshared_key.return_value = (
        "mFakePresharedKeyBase64EncodedXXXXXXXXXX="
    )
    wg.add_peer.return_value = True
    wg.remove_peer.return_value = True
    wg.get_all_peers.return_value = {}
    wg.get_peer_transfer.return_value = {}
    wg.get_peer_latest_handshake.return_value = {}
    wg.start_interface.return_value = True
    wg.stop_interface.return_value = True
    wg.save_config.return_value = True
    return wg


@pytest.fixture
def sample_server(db_session):
    """Create a sample server in the database"""
    server = Server(
        name="wg0",
        interface="wg0",
        endpoint="203.0.113.1:57473",
        listen_port=57473,
        public_key="TestServerPublicKeyBase64XXXXXXXXXXXXXXXXX=",
        private_key="TestServerPrivateKeyBase64XXXXXXXXXXXXXXXX=",
        address_pool_ipv4="10.66.66.0/24",
        address_pool_ipv6="fd42:42:42::/64",
        dns="1.1.1.1,8.8.8.8",
        max_clients=250,
        config_path="/etc/wireguard/wg0.conf",
    )
    db_session.add(server)
    db_session.commit()
    db_session.refresh(server)
    return server


@pytest.fixture
def sample_client(db_session, sample_server):
    """Create a sample client in the database"""
    client = Client(
        name="TestClient",
        server_id=sample_server.id,
        public_key="TestClientPublicKeyBase64XXXXXXXXXXXXXXXXX=",
        private_key="TestClientPrivateKeyBase64XXXXXXXXXXXXXXXX=",
        preshared_key="TestPresharedKeyBase64XXXXXXXXXXXXXXXXXXX=",
        ipv4="10.66.66.2",
        ipv6="fd42:42:42::2",
        ip_index=2,
        enabled=True,
        status=ClientStatus.ACTIVE,
    )
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    return client
