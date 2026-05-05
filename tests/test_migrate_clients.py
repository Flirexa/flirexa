"""
Tests for the Migrate Clients endpoint, especially the dual-active
copy mode introduced in v1.5.59 (Herbert's DNS-propagation case).

We're checking three flavours of `POST /api/v1/servers/{src}/migrate-clients`:
  • move (default): clients re-pointed to dst, removed from src WG, added to dst WG
  • move (kernel-only): remove_from_old=False — DB still moves, src WG keeps peers
  • copy (dual-active): keep_on_source=True — DB stays on src, peers added to dst,
                        src WG keeps peers; remove_from_old is forced off

WG managers are MagicMocked so we can record exactly which `add_peer` /
`remove_peer` calls fire on which side.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import create_app
from src.api.routes.system import get_db
from src.api.middleware.auth import get_current_admin
from src.database.models import Base, Server, Client


@pytest.fixture
def app_with_two_servers():
    """App + DB with two WG servers and three clients on the source."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    app = create_app(debug=True)

    def override_get_db():
        db = TestSession()
        try: yield db
        finally: db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = lambda: {
        "user_id": 1, "username": "testadmin", "is_superadmin": True
    }

    # Seed: src + dst on different subnets so the IP-conflict pre-flight passes
    db = TestSession()
    src = Server(
        name="src", interface="wg0", endpoint="203.0.113.1:51820", listen_port=51820,
        public_key="SrcPubKeyBase64XXXXXXXXXXXXXXXXXXXXXXXXXX=",
        private_key="SrcPrivKeyBase64XXXXXXXXXXXXXXXXXXXXXXXXX=",
        address_pool_ipv4="10.0.1.0/24", dns="1.1.1.1", max_clients=250,
        config_path="/etc/wireguard/wg0.conf",
        server_type="wireguard",
    )
    dst = Server(
        name="dst", interface="wg1", endpoint="203.0.113.2:51821", listen_port=51821,
        public_key="DstPubKeyBase64XXXXXXXXXXXXXXXXXXXXXXXXXX=",
        private_key="DstPrivKeyBase64XXXXXXXXXXXXXXXXXXXXXXXXX=",
        address_pool_ipv4="10.0.2.0/24", dns="1.1.1.1", max_clients=250,
        config_path="/etc/wireguard/wg1.conf",
        server_type="wireguard",
    )
    db.add_all([src, dst])
    db.commit()

    # 3 clients on src
    for i in range(3):
        c = Client(
            name=f"alice{i}",
            server_id=src.id,
            public_key=f"ClientPub{i:040d}=",
            private_key=f"ClientPriv{i:040d}=",
            ipv4=f"10.0.1.{10+i}",
            ip_index=10 + i,
            enabled=True,
        )
        db.add(c)
    db.commit()
    src_id, dst_id = src.id, dst.id
    db.close()

    yield app, TestSession, src_id, dst_id

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _patch_wg_managers():
    """Patch ClientManager._get_wg to return a MagicMock per server.

    Returns a dict keyed by server.id mapping to the MagicMock so the test
    can assert exactly which add_peer/remove_peer calls fired on which side.
    """
    managers = {}
    def fake_get_wg(self, server):
        m = managers.setdefault(server.id, MagicMock(name=f"wg-{server.name}"))
        return m
    return managers, patch("src.core.client_manager.ClientManager._get_wg", new=fake_get_wg)


def test_migrate_default_move(app_with_two_servers):
    """Plain migrate: DB re-points, peer removed from src, added to dst.
    The fixture seeds src/dst with different keypairs, so we pass
    force_different_keys=True to bypass the safety guard tested separately."""
    app, TestSession, src_id, dst_id = app_with_two_servers
    managers, patcher = _patch_wg_managers()
    with patcher, TestClient(app) as client:
        r = client.post(f"/api/v1/servers/{src_id}/migrate-clients", json={
            "target_server_id": dst_id,
            "sync_to_remote": True,
            "remove_from_old": True,
            "keep_on_source": False,
            "force_different_keys": True,
        })
    assert r.status_code == 200, r.text
    assert r.json()["moved"] == 3

    # DB check — all clients now on dst
    db = TestSession()
    try:
        assert db.query(Client).filter(Client.server_id == src_id).count() == 0
        assert db.query(Client).filter(Client.server_id == dst_id).count() == 3
    finally: db.close()

    # WG calls — src.remove_peer × 3, dst.add_peer × 3
    assert managers[src_id].remove_peer.call_count == 3
    assert managers[dst_id].add_peer.call_count == 3


def test_migrate_keep_on_source_dual_active(app_with_two_servers):
    """Dual-active copy: DB stays on src, peers added to dst, src untouched."""
    app, TestSession, src_id, dst_id = app_with_two_servers
    managers, patcher = _patch_wg_managers()
    with patcher, TestClient(app) as client:
        r = client.post(f"/api/v1/servers/{src_id}/migrate-clients", json={
            "target_server_id": dst_id,
            "sync_to_remote": True,
            # remove_from_old True is set in payload but the backend MUST force
            # it off when keep_on_source=True; we test that here.
            "remove_from_old": True,
            "keep_on_source": True,
            "force_different_keys": True,
        })
    assert r.status_code == 200, r.text
    assert r.json()["moved"] == 3

    # DB check — all clients STILL on src
    db = TestSession()
    try:
        assert db.query(Client).filter(Client.server_id == src_id).count() == 3
        assert db.query(Client).filter(Client.server_id == dst_id).count() == 0
    finally: db.close()

    # WG calls — dst.add_peer × 3 (peers copied to dst).
    # src.remove_peer NEVER called (forced off by keep_on_source).
    assert managers[dst_id].add_peer.call_count == 3
    # src manager shouldn't even be created (or if it is, no remove calls)
    if src_id in managers:
        assert managers[src_id].remove_peer.call_count == 0


def test_migrate_kernel_only_remove_off(app_with_two_servers):
    """remove_from_old=False without keep_on_source: DB still moves, src WG kept."""
    app, TestSession, src_id, dst_id = app_with_two_servers
    managers, patcher = _patch_wg_managers()
    with patcher, TestClient(app) as client:
        r = client.post(f"/api/v1/servers/{src_id}/migrate-clients", json={
            "target_server_id": dst_id,
            "sync_to_remote": True,
            "remove_from_old": False,   # keep peers on src kernel
            "keep_on_source": False,    # but DO move the DB association
            "force_different_keys": True,
        })
    assert r.status_code == 200, r.text
    assert r.json()["moved"] == 3

    # DB check — clients moved to dst
    db = TestSession()
    try:
        assert db.query(Client).filter(Client.server_id == src_id).count() == 0
        assert db.query(Client).filter(Client.server_id == dst_id).count() == 3
    finally: db.close()

    # WG calls — only dst.add_peer × 3, no src.remove_peer
    assert managers[dst_id].add_peer.call_count == 3
    if src_id in managers:
        assert managers[src_id].remove_peer.call_count == 0


def test_migrate_refuses_different_keypair(app_with_two_servers):
    """Migrate refuses with HTTP 400 if src and dst have different keypairs.
    Operator-safety: prevents accidental migrate to wrong-server pick."""
    app, TestSession, src_id, dst_id = app_with_two_servers
    managers, patcher = _patch_wg_managers()
    with patcher, TestClient(app) as client:
        r = client.post(f"/api/v1/servers/{src_id}/migrate-clients", json={
            "target_server_id": dst_id,
            # default force_different_keys=False
        })
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["detail"]["error"] == "keypair_mismatch"
    # Nothing should have been touched
    db = TestSession()
    try:
        # All 3 still on src, none on dst
        assert db.query(Client).filter(Client.server_id == src_id).count() == 3
        assert db.query(Client).filter(Client.server_id == dst_id).count() == 0
    finally: db.close()
    # No add_peer / remove_peer calls
    if src_id in managers: assert managers[src_id].remove_peer.call_count == 0
    if dst_id in managers: assert managers[dst_id].add_peer.call_count == 0


def test_migrate_force_different_keys_bypasses_guard(app_with_two_servers):
    """force_different_keys=True bypasses the keypair-match safety guard."""
    app, TestSession, src_id, dst_id = app_with_two_servers
    managers, patcher = _patch_wg_managers()
    with patcher, TestClient(app) as client:
        r = client.post(f"/api/v1/servers/{src_id}/migrate-clients", json={
            "target_server_id": dst_id,
            "force_different_keys": True,
        })
    assert r.status_code == 200, r.text
    assert r.json()["moved"] == 3


def test_migrate_subset_with_keep_on_source(app_with_two_servers):
    """Selective + dual-active: only chosen clients get peers on dst, none move in DB."""
    app, TestSession, src_id, dst_id = app_with_two_servers
    db = TestSession()
    try:
        chosen = db.query(Client).filter(Client.server_id == src_id).order_by(Client.id).limit(2).all()
        chosen_ids = [c.id for c in chosen]
    finally: db.close()

    managers, patcher = _patch_wg_managers()
    with patcher, TestClient(app) as client:
        r = client.post(f"/api/v1/servers/{src_id}/migrate-clients", json={
            "target_server_id": dst_id,
            "sync_to_remote": True,
            "keep_on_source": True,
            "client_ids": chosen_ids,
            "force_different_keys": True,
        })
    assert r.status_code == 200, r.text
    assert r.json()["moved"] == 2

    # All 3 still on src
    db = TestSession()
    try:
        assert db.query(Client).filter(Client.server_id == src_id).count() == 3
        assert db.query(Client).filter(Client.server_id == dst_id).count() == 0
    finally: db.close()

    assert managers[dst_id].add_peer.call_count == 2
