"""
Integration tests for SpongeBot FastAPI API
Uses TestClient with SQLite in-memory database
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Force SQLite for tests
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_ENABLED"] = "false"
os.environ["SMTP_ENABLED"] = "false"
os.environ["LICENSE_CHECK_ENABLED"] = "false"

from src.database.models import Base, Server, Client, ClientStatus, SystemConfig
from src.database.connection import get_db
from src.api.main import create_app
from src.api.middleware.auth import get_current_admin
from src.api.routes import admin_auth, client_portal
from src.modules.subscription.subscription_models import (
    ClientUser,
    ClientPortalSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
)


@pytest.fixture
def app_with_db():
    """Create test app with in-memory SQLite database"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    app = create_app(debug=True)
    app.state.operational_mode_session_factory = TestSession

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = lambda: {
        "user_id": 1, "username": "testadmin", "is_superadmin": True
    }

    # Seed a server
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
def client(app_with_db):
    """Create a test HTTP client"""
    app, _, _ = app_with_db
    return TestClient(app)


@pytest.fixture
def db_for_test(app_with_db):
    """Get a DB session for direct database access in tests"""
    _, TestSession, _ = app_with_db
    db = TestSession()
    yield db
    db.close()


# ============================================================================
# SYSTEM ENDPOINTS
# ============================================================================

class TestSystemEndpoints:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_client_portal_features_reports_corporate_access(self, client, db_for_test):
        user = ClientUser(email="corp-feature@example.com", username="corpfeature", password_hash="x")
        db_for_test.add(user)
        db_for_test.flush()

        db_for_test.add(
            SubscriptionPlan(
                tier="STANDARD",
                name="Standard",
                description="std",
                max_devices=5,
                traffic_limit_gb=200,
                bandwidth_limit_mbps=100,
                price_monthly_usd=10.0,
                is_active=True,
                is_visible=True,
                display_order=1,
                features={"corp_networks": 1, "corp_sites": 5},
            )
        )
        db_for_test.add(
            ClientPortalSubscription(
                user_id=user.id,
                tier="STANDARD",
                status=SubscriptionStatus.ACTIVE,
            )
        )
        db_for_test.commit()

        from src.api.routes import client_portal as cp_module

        client.app.dependency_overrides[cp_module.get_current_user] = lambda: user.id
        response = client.get("/client-portal/features")
        assert response.status_code == 200
        assert response.json()["features"]["corp_networks"] is True

    def test_maintenance_mode_blocks_mutating_admin_routes(self, client, db_for_test):
        db_for_test.add(SystemConfig(key="maintenance_mode", value="true", value_type="bool"))
        db_for_test.add(SystemConfig(key="maintenance_reason", value="planned maintenance", value_type="string"))
        db_for_test.commit()

        blocked = client.post("/api/v1/servers", json={})
        assert blocked.status_code == 423
        assert blocked.json()["operational_mode"] == "maintenance"

        allowed = client.get("/api/v1/system/status")
        assert allowed.status_code == 200

    def test_operational_mode_endpoint_returns_ui_banner_payload(self, client, db_for_test):
        db_for_test.add(SystemConfig(key="maintenance_mode", value="true", value_type="bool"))
        db_for_test.add(SystemConfig(key="maintenance_reason", value="planned maintenance", value_type="string"))
        db_for_test.commit()

        response = client.get("/api/v1/system/operational-mode")
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "maintenance"
        assert data["reason"] == "planned maintenance"
        assert data["banner_severity"] == "warning"
        assert data["allowed_actions"]["mutate_business"] is False
        assert data["allowed_actions"]["run_updates"] is True


class TestClientIpHandling:
    @staticmethod
    def _request(client_ip: str, forwarded: str | None = None) -> Request:
        headers = []
        if forwarded is not None:
            headers.append((b"x-forwarded-for", forwarded.encode()))
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (client_ip, 12345),
            "scheme": "http",
            "query_string": b"",
            "server": ("testserver", 80),
        }
        return Request(scope)

    def test_client_portal_does_not_trust_forwarded_header_from_public_client(self):
        request = self._request("203.0.113.10", "198.51.100.5")
        assert client_portal._get_client_ip(request) == "203.0.113.10"

    def test_client_portal_trusts_forwarded_header_from_local_proxy(self):
        request = self._request("127.0.0.1", "198.51.100.5, 127.0.0.1")
        assert client_portal._get_client_ip(request) == "198.51.100.5"

    def test_admin_auth_does_not_trust_forwarded_header_from_public_client(self):
        request = self._request("203.0.113.10", "198.51.100.5")
        assert admin_auth._get_client_ip(request) == "203.0.113.10"


class TestClientPortalAuthFlows:
    def test_forgot_password_keeps_email_verification_token(self, client, db_for_test):
        register_response = client.post("/client-portal/auth/register", json={
            "email": "auth-flow@example.com",
            "password": "strong-password-123",
            "username": "authflow",
        })
        assert register_response.status_code == 201

        user = db_for_test.query(ClientUser).filter(ClientUser.email == "auth-flow@example.com").first()
        assert user is not None
        verification_token = user.verification_token
        assert verification_token

        forgot_response = client.post("/client-portal/auth/forgot-password", json={
            "email": "auth-flow@example.com",
        })
        assert forgot_response.status_code == 200

        db_for_test.refresh(user)
        assert user.verification_token == verification_token
        assert user.password_reset_token
        assert user.password_reset_token_created_at is not None

    def test_verification_and_password_reset_can_both_complete(self, client, db_for_test):
        register_response = client.post("/client-portal/auth/register", json={
            "email": "dual-flow@example.com",
            "password": "strong-password-123",
            "username": "dualflow",
        })
        assert register_response.status_code == 201

        user = db_for_test.query(ClientUser).filter(ClientUser.email == "dual-flow@example.com").first()
        assert user is not None
        verification_token = user.verification_token

        forgot_response = client.post("/client-portal/auth/forgot-password", json={
            "email": "dual-flow@example.com",
        })
        assert forgot_response.status_code == 200

        db_for_test.refresh(user)
        reset_token = user.password_reset_token
        assert reset_token

        verify_response = client.post("/client-portal/auth/verify-email", json={
            "token": verification_token,
        })
        assert verify_response.status_code == 200

        reset_response = client.post("/client-portal/auth/reset-password", json={
            "token": reset_token,
            "new_password": "new-strong-password-456",
        })
        assert reset_response.status_code == 200

        login_response = client.post("/client-portal/auth/login", json={
            "email": "dual-flow@example.com",
            "password": "new-strong-password-456",
        })
        assert login_response.status_code == 200

        db_for_test.refresh(user)
        assert user.email_verified is True
        assert user.password_reset_token is None
        assert user.password_reset_token_created_at is None

    def test_reset_password_rejects_short_passwords(self, client, db_for_test):
        register_response = client.post("/client-portal/auth/register", json={
            "email": "short-reset@example.com",
            "password": "strong-password-123",
            "username": "shortreset",
        })
        assert register_response.status_code == 201

        forgot_response = client.post("/client-portal/auth/forgot-password", json={
            "email": "short-reset@example.com",
        })
        assert forgot_response.status_code == 200

        user = db_for_test.query(ClientUser).filter(ClientUser.email == "short-reset@example.com").first()
        assert user is not None

        reset_response = client.post("/client-portal/auth/reset-password", json={
            "token": user.password_reset_token,
            "new_password": "short7!",
        })
        assert reset_response.status_code == 422

    def test_change_password_rejects_short_passwords(self, client):
        register_response = client.post("/client-portal/auth/register", json={
            "email": "short-change@example.com",
            "password": "strong-password-123",
            "username": "shortchange",
        })
        assert register_response.status_code == 201

        token = register_response.json()["access_token"]
        change_response = client.post(
            "/client-portal/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "strong-password-123",
                "new_password": "short7!",
            },
        )
        assert change_response.status_code == 422


class TestSubscriptionLinkSecurity:
    def test_public_subscription_link_rejects_invalid_token_format(self, client):
        response = client.get("/client-portal/sub/invalid+token")
        assert response.status_code == 404


class TestTariffCorporateFields:
    def test_create_tariff_roundtrips_corp_sites(self, client):
        payload = {
            "tier": "corp-plus",
            "name": "Corp Plus",
            "description": "corporate tier",
            "max_devices": 10,
            "traffic_limit_gb": 500,
            "bandwidth_limit_mbps": 200,
            "price_monthly_usd": 49.0,
            "is_active": True,
            "is_visible": True,
            "display_order": 10,
            "corp_networks": 2,
            "corp_sites": 12,
        }
        response = client.post("/api/v1/tariffs", json=payload)
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["corp_networks"] == 2
        assert data["corp_sites"] == 12

    def test_update_tariff_roundtrips_corp_sites(self, client):
        create_payload = {
            "tier": "corp-edit",
            "name": "Corp Edit",
            "description": "corporate tier",
            "max_devices": 10,
            "traffic_limit_gb": 500,
            "bandwidth_limit_mbps": 200,
            "price_monthly_usd": 49.0,
            "is_active": True,
            "is_visible": True,
            "display_order": 10,
            "corp_networks": 2,
            "corp_sites": 12,
        }
        created = client.post("/api/v1/tariffs", json=create_payload)
        assert created.status_code == 201, created.text
        tariff_id = created.json()["id"]

        updated = client.put(
            f"/api/v1/tariffs/{tariff_id}",
            json={"corp_networks": 4, "corp_sites": 40},
        )
        assert updated.status_code == 200, updated.text
        data = updated.json()
        assert data["corp_networks"] == 4
        assert data["corp_sites"] == 40


# ============================================================================
# SERVER ENDPOINTS
# ============================================================================

class TestServerEndpoints:
    def test_list_servers(self, client):
        response = client.get("/api/v1/servers")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "wg0"

    def test_get_server(self, client):
        response = client.get("/api/v1/servers/1")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "wg0"
        assert data["listen_port"] == 57473

    def test_get_server_not_found(self, client):
        response = client.get("/api/v1/servers/999")
        assert response.status_code == 404


# ============================================================================
# CLIENT ENDPOINTS
# ============================================================================

class TestClientEndpoints:

    @patch("src.core.wireguard.WireGuardManager.generate_keypair")
    @patch("src.core.wireguard.WireGuardManager.generate_preshared_key")
    @patch("src.core.wireguard.WireGuardManager.add_peer")
    def test_create_client(self, mock_add, mock_psk, mock_keys, client):
        mock_keys.return_value = ("FakePrivKey" + "=" * 33, "FakePubKey" + "x" * 34)
        mock_psk.return_value = "FakePSK" + "x" * 37
        mock_add.return_value = True

        response = client.post("/api/v1/clients", json={
            "name": "TestPhone",
            "server_id": 1,
        })
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["name"] == "TestPhone"
        assert "ipv4" in data

    def test_create_client_no_name(self, client):
        response = client.post("/api/v1/clients", json={
            "server_id": 1,
        })
        assert response.status_code == 422  # Validation error

    def test_list_clients(self, client):
        response = client.get("/api/v1/clients")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    @patch("src.core.wireguard.WireGuardManager.generate_keypair")
    @patch("src.core.wireguard.WireGuardManager.generate_preshared_key")
    @patch("src.core.wireguard.WireGuardManager.add_peer")
    @patch("src.core.wireguard.WireGuardManager.remove_peer")
    def test_enable_disable_client(self, mock_remove, mock_add, mock_psk, mock_keys, client, db_for_test):
        mock_keys.return_value = ("FakePrivKey" + "=" * 33, "FakePubKey" + "x" * 34)
        mock_psk.return_value = "FakePSK" + "x" * 37
        mock_add.return_value = True
        mock_remove.return_value = True

        # Create client first
        c = Client(
            name="ToggleTest",
            server_id=1,
            public_key="TogglePubKey" + "x" * 32,
            private_key="TogglePrivKey" + "x" * 31,
            preshared_key="TogglePSK" + "x" * 35,
            ipv4="10.66.66.5",
            ip_index=5,
            enabled=True,
            status=ClientStatus.ACTIVE,
        )
        db_for_test.add(c)
        db_for_test.commit()
        client_id = c.id

        # Disable
        response = client.post(f"/api/v1/clients/{client_id}/disable")
        assert response.status_code == 200

        # Enable
        response = client.post(f"/api/v1/clients/{client_id}/enable")
        assert response.status_code == 200

    def test_get_client_not_found(self, client):
        response = client.get("/api/v1/clients/999")
        assert response.status_code == 404

    @patch("src.core.wireguard.WireGuardManager.remove_peer")
    def test_delete_client(self, mock_remove, client, db_for_test):
        mock_remove.return_value = True

        c = Client(
            name="DeleteMe",
            server_id=1,
            public_key="DelPubKey" + "x" * 35,
            private_key="DelPrivKey" + "x" * 34,
            ipv4="10.66.66.10",
            ip_index=10,
            enabled=True,
            status=ClientStatus.ACTIVE,
        )
        db_for_test.add(c)
        db_for_test.commit()
        client_id = c.id

        response = client.delete(f"/api/v1/clients/{client_id}")
        assert response.status_code == 200

        # Verify deleted
        response = client.get(f"/api/v1/clients/{client_id}")
        assert response.status_code == 404


# ============================================================================
# SYSTEM STATUS ENDPOINT
# ============================================================================

class TestSystemStatus:

    @patch("src.core.wireguard.WireGuardManager.get_all_peers")
    def test_system_status(self, mock_peers, client):
        mock_peers.return_value = {}
        response = client.get("/api/v1/system/status")
        assert response.status_code == 200
        data = response.json()
        assert "servers" in data
        assert "clients" in data
