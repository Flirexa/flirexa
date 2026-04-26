"""
Integration tests for critical API scenarios.

Covers: admin auth flow, server CRUD, client lifecycle,
delete-preview endpoints, health detail, backup API validation,
client portal registration/login flow.

Bridge reference: ARCHITECT_BRIDGE.md points 3 (critical scenarios)
and 5 (evidence of readiness).
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_ENABLED"] = "false"
os.environ["SMTP_ENABLED"] = "false"
os.environ["LICENSE_CHECK_ENABLED"] = "false"

from src.database.models import Base, Server, Client, ClientStatus, AdminUser
from src.database.connection import get_db
from src.api.main import create_app
from src.api.middleware.auth import get_current_admin, hash_password
from src.api.routes import client_portal as cp_module, admin_auth as aa_module
from src.modules.subscription.subscription_models import ClientUser


# ============================================================================
# FIXTURES
# ============================================================================

def _fake_admin():
    """Return a fake admin payload for dependency override."""
    return {"user_id": 1, "username": "testadmin", "is_superadmin": True}


@pytest.fixture(autouse=True)
def _clear_rate_limiters():
    """Reset rate limiters between tests to prevent 429s."""
    cp_module._auth_attempts.clear()
    cp_module._forgot_cooldowns.clear()
    aa_module._login_attempts.clear()
    yield
    cp_module._auth_attempts.clear()
    aa_module._login_attempts.clear()


@pytest.fixture
def app_with_db():
    """Create test app with in-memory SQLite, seeded data, and auth bypass."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    app = create_app(debug=True)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = _fake_admin

    # Seed server
    db = TestSession()
    server = Server(
        name="wg0",
        interface="wg0",
        endpoint="203.0.113.1:57473",
        listen_port=57473,
        public_key="TestServerPublicKeyBase64XXXXXXXXXXXXXXXXX=",
        private_key="TestServerPrivateKeyBase64XXXXXXXXXXXXXXXX=",
        address_pool_ipv4="10.66.66.0/24",
        dns="1.1.1.1",
        max_clients=250,
        config_path="/etc/wireguard/wg0.conf",
    )
    db.add(server)
    db.commit()
    db.close()

    yield app, TestSession, engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def app_with_real_auth():
    """Create test app WITH real auth (no admin override) for auth flow tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    app = create_app(debug=True)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # NO admin auth override — real JWT auth enforced

    yield app, TestSession, engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client(app_with_db):
    app, _, _ = app_with_db
    return TestClient(app)


@pytest.fixture
def auth_client(app_with_real_auth):
    app, _, _ = app_with_real_auth
    return TestClient(app)


@pytest.fixture
def db_for_test(app_with_db):
    _, TestSession, _ = app_with_db
    db = TestSession()
    yield db
    db.close()


def _seed_client(db, server_id=1, name="IntegClient", ip_index=2, enabled=True):
    """Helper to seed a client directly in DB."""
    c = Client(
        name=name,
        server_id=server_id,
        public_key=f"Pub{name}" + "x" * (44 - 3 - len(name)),
        private_key=f"Prv{name}" + "x" * (44 - 3 - len(name)),
        preshared_key=f"Psk{name}" + "x" * (44 - 3 - len(name)),
        ipv4=f"10.66.66.{ip_index}",
        ip_index=ip_index,
        enabled=enabled,
        status=ClientStatus.ACTIVE if enabled else ClientStatus.DISABLED,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ============================================================================
# 1. HEALTH ENDPOINT (detailed)
# ============================================================================

class TestHealthDetail:
    def test_health_basic(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "healthy"
        assert "version" in d
        assert "database" not in d

    def test_health_detail(self, client):
        r = client.get("/health?detail=true")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] in ("healthy", "degraded")
        assert "database" in d
        assert "background_tasks" in d
        assert "uptime_seconds" in d
        assert isinstance(d["uptime_seconds"], int)

    def test_request_id_header(self, client):
        r = client.get("/health")
        assert "x-request-id" in r.headers
        assert len(r.headers["x-request-id"]) == 8

    def test_request_id_passthrough(self, client):
        r = client.get("/health", headers={"X-Request-ID": "my-req-42"})
        assert r.headers["x-request-id"] == "my-req-42"

    def test_security_headers(self, client):
        r = client.get("/health")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"


# ============================================================================
# 2. ADMIN AUTH FLOW (uses real auth, no admin override)
# ============================================================================

class TestAdminAuthFlow:
    def test_setup_status_no_admins(self, auth_client):
        r = auth_client.get("/api/v1/auth/setup-status")
        assert r.status_code == 200
        assert r.json()["needs_setup"] is True

    def test_setup_creates_admin(self, auth_client):
        r = auth_client.post("/api/v1/auth/setup", json={
            "username": "admin",
            "password": "securepass123",
        })
        assert r.status_code == 201
        d = r.json()
        assert "access_token" in d
        assert "refresh_token" in d
        assert d["user"]["username"] == "admin"
        assert d["user"]["is_superadmin"] is True

    def test_setup_blocked_after_first(self, auth_client):
        auth_client.post("/api/v1/auth/setup", json={
            "username": "admin",
            "password": "securepass123",
        })
        r = auth_client.post("/api/v1/auth/setup", json={
            "username": "admin2",
            "password": "securepass456",
        })
        assert r.status_code == 403

    def test_login_success(self, auth_client):
        auth_client.post("/api/v1/auth/setup", json={
            "username": "admin",
            "password": "securepass123",
        })
        r = auth_client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "securepass123",
        })
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password(self, auth_client):
        auth_client.post("/api/v1/auth/setup", json={
            "username": "admin",
            "password": "securepass123",
        })
        r = auth_client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "wrongpassword",
        })
        assert r.status_code == 401

    def test_login_nonexistent_user(self, auth_client):
        r = auth_client.post("/api/v1/auth/login", json={
            "username": "nobody",
            "password": "whatever123",
        })
        assert r.status_code == 401

    def test_setup_rejects_short_password(self, auth_client):
        r = auth_client.post("/api/v1/auth/setup", json={
            "username": "admin",
            "password": "short",
        })
        assert r.status_code == 422

    def test_token_refresh(self, auth_client):
        setup_r = auth_client.post("/api/v1/auth/setup", json={
            "username": "admin",
            "password": "securepass123",
        })
        refresh_token = setup_r.json()["refresh_token"]
        r = auth_client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_me_endpoint(self, auth_client):
        setup_r = auth_client.post("/api/v1/auth/setup", json={
            "username": "admin",
            "password": "securepass123",
        })
        token = setup_r.json()["access_token"]
        r = auth_client.get("/api/v1/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert r.status_code == 200
        assert r.json()["username"] == "admin"

    def test_protected_route_requires_auth(self, auth_client):
        """Without token, admin routes return 401."""
        r = auth_client.get("/api/v1/servers")
        assert r.status_code == 401


# ============================================================================
# 3. SERVER CRUD & DELETE-PREVIEW (auth bypassed via fixture)
# ============================================================================

class TestServerCrud:
    def test_list_servers(self, client):
        r = client.get("/api/v1/servers")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 1
        assert len(d["items"]) == 1

    def test_get_server(self, client):
        r = client.get("/api/v1/servers/1")
        assert r.status_code == 200
        assert r.json()["name"] == "wg0"

    def test_get_server_404(self, client):
        r = client.get("/api/v1/servers/999")
        assert r.status_code == 404

    def test_delete_preview_no_clients(self, client):
        r = client.get("/api/v1/servers/1/delete-preview")
        assert r.status_code == 200
        d = r.json()
        assert d["server_name"] == "wg0"
        assert d["total_clients"] == 0
        assert d["requires_force"] is False

    def test_delete_preview_with_clients(self, client, db_for_test):
        _seed_client(db_for_test, name="Client1", ip_index=2)
        _seed_client(db_for_test, name="Client2", ip_index=3, enabled=False)

        r = client.get("/api/v1/servers/1/delete-preview")
        assert r.status_code == 200
        d = r.json()
        assert d["total_clients"] == 2
        assert d["enabled_clients"] == 1
        assert "Client1" in d["client_names"]
        assert "Client2" in d["client_names"]
        assert d["requires_force"] is True

    def test_delete_preview_404(self, client):
        r = client.get("/api/v1/servers/999/delete-preview")
        assert r.status_code == 404


# ============================================================================
# 4. CLIENT LIFECYCLE (create → get → disable → enable → preview → delete)
# ============================================================================

class TestClientLifecycle:

    @patch("src.core.wireguard.WireGuardManager.generate_keypair")
    @patch("src.core.wireguard.WireGuardManager.generate_preshared_key")
    @patch("src.core.wireguard.WireGuardManager.add_peer")
    @patch("src.core.wireguard.WireGuardManager.remove_peer")
    def test_full_lifecycle(self, mock_remove, mock_add, mock_psk, mock_keys, client):
        mock_keys.return_value = ("FakePrivKey" + "=" * 33, "FakePubKey" + "x" * 34)
        mock_psk.return_value = "FakePSK" + "x" * 37
        mock_add.return_value = True
        mock_remove.return_value = True

        # CREATE
        r = client.post("/api/v1/clients", json={
            "name": "LifecycleClient",
            "server_id": 1,
        })
        assert r.status_code == 201
        d = r.json()
        client_id = d["id"]
        assert d["name"] == "LifecycleClient"
        assert d["enabled"] is True
        assert "ipv4" in d

        # GET
        r = client.get(f"/api/v1/clients/{client_id}")
        assert r.status_code == 200
        assert r.json()["name"] == "LifecycleClient"

        # LIST (paginated response: {total, items, limit, offset})
        r = client.get("/api/v1/clients")
        assert r.status_code == 200
        d = r.json()
        assert "total" in d
        assert "items" in d
        assert d["total"] >= 1
        names = [c["name"] for c in d["items"]]
        assert "LifecycleClient" in names

        # DISABLE
        r = client.post(f"/api/v1/clients/{client_id}/disable")
        assert r.status_code == 200

        # ENABLE
        r = client.post(f"/api/v1/clients/{client_id}/enable")
        assert r.status_code == 200

        # DELETE PREVIEW
        r = client.get(f"/api/v1/clients/{client_id}/delete-preview")
        assert r.status_code == 200
        d = r.json()
        assert d["client_name"] == "LifecycleClient"
        assert "warning" in d

        # DELETE
        r = client.delete(f"/api/v1/clients/{client_id}")
        assert r.status_code == 200

        # VERIFY GONE
        r = client.get(f"/api/v1/clients/{client_id}")
        assert r.status_code == 404

    def test_delete_preview_404(self, client):
        r = client.get("/api/v1/clients/999/delete-preview")
        assert r.status_code == 404

    def test_create_client_no_name(self, client):
        r = client.post("/api/v1/clients", json={"server_id": 1})
        assert r.status_code == 422

    def test_create_client_invalid_server(self, client):
        """Server 999 doesn't exist → core.create_client returns None → 500.
        Note: ideally this should be 404, but current contract is 500."""
        r = client.post("/api/v1/clients", json={
            "name": "OrphanClient",
            "server_id": 999,
        })
        assert r.status_code == 500

    @patch("src.core.wireguard.WireGuardManager.generate_keypair")
    @patch("src.core.wireguard.WireGuardManager.generate_preshared_key")
    @patch("src.core.wireguard.WireGuardManager.add_peer")
    def test_create_duplicate_name(self, mock_add, mock_psk, mock_keys, client):
        mock_keys.return_value = ("FakePrivKey" + "=" * 33, "FakePubKey" + "x" * 34)
        mock_psk.return_value = "FakePSK" + "x" * 37
        mock_add.return_value = True

        r1 = client.post("/api/v1/clients", json={
            "name": "DupClient",
            "server_id": 1,
        })
        assert r1.status_code == 201

        # Duplicate name on same server → 400 from client_exists check
        r2 = client.post("/api/v1/clients", json={
            "name": "DupClient",
            "server_id": 1,
        })
        assert r2.status_code == 400
        assert "already exists" in r2.json()["detail"]


# ============================================================================
# 5. CLIENT PORTAL AUTH (register → login → profile)
# ============================================================================

class TestClientPortalFlow:
    def test_register_and_login(self, client):
        r = client.post("/client-portal/auth/register", json={
            "email": "newuser@example.com",
            "password": "securepass123",
            "username": "newuser",
        })
        assert r.status_code == 201
        d = r.json()
        assert "access_token" in d

        r = client.post("/client-portal/auth/login", json={
            "email": "newuser@example.com",
            "password": "securepass123",
        })
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_register_duplicate_email(self, client):
        r1 = client.post("/client-portal/auth/register", json={
            "email": "dup@example.com",
            "password": "securepass123",
            "username": "first",
        })
        assert r1.status_code == 201

        # Duplicate email → 400 from SubscriptionManager.create_user
        r = client.post("/client-portal/auth/register", json={
            "email": "dup@example.com",
            "password": "securepass456",
            "username": "second",
        })
        assert r.status_code == 400
        assert "already registered" in r.json()["detail"].lower()

    def test_register_short_password(self, client):
        r = client.post("/client-portal/auth/register", json={
            "email": "short@example.com",
            "password": "short",
            "username": "shortpw",
        })
        assert r.status_code == 422

    def test_login_wrong_password(self, client):
        client.post("/client-portal/auth/register", json={
            "email": "wrong@example.com",
            "password": "securepass123",
            "username": "wrongpw",
        })
        r = client.post("/client-portal/auth/login", json={
            "email": "wrong@example.com",
            "password": "badpassword123",
        })
        assert r.status_code == 401


# ============================================================================
# 6. BACKUP API VALIDATION (path traversal protection)
# ============================================================================

class TestBackupValidation:
    def test_backup_id_path_traversal_delete(self, client):
        """Valid backup_id format but file doesn't exist → 404 from FileNotFoundError."""
        r = client.delete("/api/v1/backup/evil__backup")
        assert r.status_code == 404

    def test_backup_id_with_dots_blocked(self, client):
        """'..' in backup_id → 400 from _validate_backup_id."""
        r = client.post("/api/v1/backup/restore/database/backup..id")
        assert r.status_code == 400
        assert "Invalid backup ID" in r.json()["detail"]

    def test_backup_list(self, client):
        r = client.get("/api/v1/backup/list")
        assert r.status_code == 200
        d = r.json()
        assert "backups" in d
        assert "count" in d


# ============================================================================
# 7. SYSTEM STATUS (admin protected, auth bypassed)
# ============================================================================

class TestSystemEndpoints:
    @patch("src.core.wireguard.WireGuardManager.get_all_peers")
    def test_system_status(self, mock_peers, client):
        mock_peers.return_value = {}
        r = client.get("/api/v1/system/status")
        assert r.status_code == 200
        d = r.json()
        assert "servers" in d
        assert "clients" in d


# ============================================================================
# 8. MULTI-CLIENT SERVER OPERATIONS
# ============================================================================

class TestMultiClientServer:
    @patch("src.core.wireguard.WireGuardManager.remove_peer")
    def test_server_delete_blocked_without_force(self, mock_remove, client, db_for_test):
        mock_remove.return_value = True
        _seed_client(db_for_test, name="BlockClient", ip_index=5)

        r = client.delete("/api/v1/servers/1")
        assert r.status_code == 400

    @patch("src.core.wireguard.WireGuardManager.remove_peer")
    @patch("src.core.wireguard.WireGuardManager.stop_interface")
    def test_server_delete_with_force(self, mock_stop, mock_remove, client, db_for_test):
        mock_remove.return_value = True
        mock_stop.return_value = True
        _seed_client(db_for_test, name="ForceClient", ip_index=5)

        r = client.delete("/api/v1/servers/1?force=true")
        assert r.status_code == 200

        r = client.get("/api/v1/servers/1")
        assert r.status_code == 404

    @patch("src.core.wireguard.WireGuardManager.get_all_peers")
    def test_server_stats(self, mock_peers, client, db_for_test):
        mock_peers.return_value = {}
        _seed_client(db_for_test, name="StatsClient1", ip_index=2)
        _seed_client(db_for_test, name="StatsClient2", ip_index=3)

        r = client.get("/api/v1/servers/1/stats")
        assert r.status_code == 200
        d = r.json()
        assert d["total_clients"] >= 2
