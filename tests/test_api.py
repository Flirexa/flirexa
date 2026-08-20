"""
Integration tests for the Flirexa FastAPI API
Uses TestClient with SQLite in-memory database
"""

import os
import importlib
from datetime import datetime, timedelta, timezone

import bcrypt
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

from src.database.models import (
    AdminUser,
    AuditAction,
    AuditLog,
    Base,
    Client,
    ClientStatus,
    Server,
    SystemConfig,
)
from src.database.connection import get_db
from src.api.main import create_app
from src.api.middleware.auth import get_current_admin
from src.api.routes import admin_auth, client_portal, client_portal_auth
from src.modules.subscription.subscription_models import (
    ClientUser,
    ClientRefreshToken,
    ClientPortalSubscription,
    PortalRateLimit,
    SupportMessage,
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

    # Seed the authoritative admin row used by DB-backed RBAC dependencies.
    db = TestSession()
    db.add(AdminUser(
        id=1,
        username="testadmin",
        password_hash="not-used-by-overridden-auth",
        is_superadmin=True,
        is_active=True,
        role="owner",
    ))

    # Seed a server
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

    def test_client_portal_mode_defaults_preserve_existing_app_operators(self, client, db_for_test):
        response = client.get("/api/v1/system/client-portal-settings")
        assert response.status_code == 200
        assert response.json() == {"mode": "simple"}

        db_for_test.add(SystemConfig(key="app_integration_enabled", value="true", value_type="bool"))
        db_for_test.commit()
        response = client.get("/api/v1/system/client-portal-settings")
        assert response.status_code == 200
        assert response.json() == {"mode": "advanced"}

        response = client.post(
            "/api/v1/system/client-portal-settings",
            json={"mode": "simple"},
        )
        assert response.status_code == 200
        assert response.json() == {"mode": "simple"}

        response = client.get("/api/v1/system/client-portal-settings")
        assert response.status_code == 200
        assert response.json() == {"mode": "simple"}

    def test_client_portal_mode_rejects_unknown_values(self, client):
        response = client.post(
            "/api/v1/system/client-portal-settings",
            json={"mode": "technical"},
        )
        assert response.status_code == 422

    def test_client_portal_features_requires_customer_and_operator_corporate_access(self, client, db_for_test):
        from src.modules.corporate import manager as corporate_manager

        if getattr(corporate_manager, "FLIREXA_COMMERCIAL_STUB", False):
            pytest.skip("corporate VPN implementation is private in the open core")
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
        # A corporate-capable customer tariff alone cannot bypass the
        # operator's Enterprise entitlement.
        response = client.get("/client-portal/features")
        assert response.status_code == 200
        assert response.json()["features"]["corp_networks"] is False
        assert response.json()["features"]["auto_renewal"] is False
        assert response.json()["portal_mode"] == "simple"

        with patch.object(
            cp_module,
            "_operator_has_feature",
            side_effect=lambda feature: feature in {"corporate_vpn", "auto_renewal"},
        ):
            response = client.get("/client-portal/features")
        assert response.status_code == 200
        assert response.json()["features"]["corp_networks"] is True
        assert response.json()["features"]["auto_renewal"] is False

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


class TestClientPortalAbuseControls:
    @staticmethod
    def _registration_payload(index: int) -> dict:
        return {
            "email": f"rate-{index}@example.com",
            "password": "strong-password-123",
            "username": f"rateuser{index}",
        }

    def test_registration_limit_is_persistent_and_does_not_store_raw_ip(
        self,
        client,
        db_for_test,
        monkeypatch,
    ):
        monkeypatch.setattr(client_portal, "_REGISTER_RATE_MAX", 2)
        monkeypatch.setattr(client_portal, "_REGISTER_RATE_WINDOW", 3600)

        first = client.post(
            "/client-portal/auth/register",
            json=self._registration_payload(1),
        )
        second = client.post(
            "/client-portal/auth/register",
            json=self._registration_payload(2),
        )
        blocked = client.post(
            "/client-portal/auth/register",
            json=self._registration_payload(3),
        )

        assert first.status_code == 201
        assert second.status_code == 201
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        assert blocked.json()["detail"] == (
            "Too many registrations. Please try again later."
        )

        bucket = db_for_test.query(PortalRateLimit).one()
        assert bucket.request_count == 2
        assert "testclient" not in bucket.bucket_key

    def test_support_limit_caps_authenticated_db_amplification(
        self,
        client,
        db_for_test,
        monkeypatch,
    ):
        monkeypatch.setattr(client_portal, "_SUPPORT_USER_RATE_MAX", 2)
        monkeypatch.setattr(client_portal, "_SUPPORT_IP_RATE_MAX", 100)

        registered = client.post(
            "/client-portal/auth/register",
            json=self._registration_payload(10),
        )
        assert registered.status_code == 201
        token = registered.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        for index in (1, 2):
            response = client.post(
                "/client-portal/support/send",
                headers=headers,
                json={"subject": f"Question {index}", "message": "Please help"},
            )
            assert response.status_code == 200

        blocked = client.post(
            "/client-portal/support/send",
            headers=headers,
            json={"subject": "Question 3", "message": "Please help again"},
        )
        assert blocked.status_code == 429
        assert db_for_test.query(SupportMessage).count() == 2

    def test_limiter_survives_a_new_database_session(self, app_with_db):
        _, TestSession, _ = app_with_db
        first_session = TestSession()
        try:
            assert client_portal._consume_persistent_rate_limit(
                first_session,
                scope="persistence_test",
                identity="198.51.100.10",
                maximum=1,
                window_seconds=3600,
            ) is None
        finally:
            first_session.close()

        second_session = TestSession()
        try:
            retry_after = client_portal._consume_persistent_rate_limit(
                second_session,
                scope="persistence_test",
                identity="198.51.100.10",
                maximum=1,
                window_seconds=3600,
            )
        finally:
            second_session.close()

        assert retry_after is not None
        assert retry_after > 0

    def test_public_portal_api_docs_are_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("CLIENT_PORTAL_API_DOCS_ENABLED", raising=False)
        import client_portal_main

        portal_module = importlib.reload(client_portal_main)
        assert portal_module.app.openapi_url is None
        # Newer FastAPI versions also expose an internal router sentinel in
        # app.routes; only concrete HTTP routes carry a path.
        route_paths = {
            route.path
            for route in portal_module.app.routes
            if getattr(route, "path", None)
        }
        assert {"/docs", "/redoc", "/openapi.json"} <= route_paths


class TestAdminPortalUserPassword:
    @staticmethod
    def _create_user(db, *, username: str = "passworduser") -> ClientUser:
        user = ClientUser(
            email=f"{username}@example.com",
            username=username,
            password_hash=bcrypt.hashpw(b"old-password-123", bcrypt.gensalt()).decode("utf-8"),
            password_reset_token="pending-reset-token",
            password_reset_token_created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def test_admin_can_set_password_and_revoke_reset_token(self, client, db_for_test):
        user = self._create_user(db_for_test)
        db_for_test.add(ClientRefreshToken(
            user_id=user.id,
            token_hash="a" * 64,
            family_id="b" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            created_at=datetime.now(timezone.utc),
        ))
        db_for_test.commit()

        response = client.post(
            f"/api/v1/portal-users/{user.id}/password",
            json={"new_password": "new-password-456"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "message": "Password updated successfully",
            "id": user.id,
        }
        assert "new-password-456" not in response.text

        db_for_test.expire_all()
        updated = db_for_test.get(ClientUser, user.id)
        assert bcrypt.checkpw(b"new-password-456", updated.password_hash.encode("utf-8"))
        assert not bcrypt.checkpw(b"old-password-123", updated.password_hash.encode("utf-8"))
        assert updated.password_reset_token is None
        assert updated.password_reset_token_created_at is None

        audit = (
            db_for_test.query(AuditLog)
            .filter(
                AuditLog.action == AuditAction.CONFIG_CHANGE,
                AuditLog.target_type == "portal_user",
                AuditLog.target_id == user.id,
            )
            .one()
        )
        assert audit.user_id == 1
        assert audit.details == {
            "action": "admin_password_reset",
            "reset_token_revoked": True,
            "browser_sessions_revoked": 1,
        }
        assert "new_password" not in audit.details
        assert "new-password-456" not in str(audit.details)
        refresh = (
            db_for_test.query(ClientRefreshToken)
            .filter(ClientRefreshToken.user_id == user.id)
            .one()
        )
        assert refresh.revoked_at is not None

    @pytest.mark.parametrize("new_password", ["short7", "я" * 40])
    def test_admin_password_validation_rejects_unsafe_lengths(
        self,
        client,
        db_for_test,
        new_password,
    ):
        user = self._create_user(db_for_test, username=f"validation{len(new_password)}")

        response = client.post(
            f"/api/v1/portal-users/{user.id}/password",
            json={"new_password": new_password},
        )

        assert response.status_code == 422

    def test_admin_password_update_returns_404_for_unknown_user(self, client):
        response = client.post(
            "/api/v1/portal-users/999999/password",
            json={"new_password": "new-password-456"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"


class TestClientPortalAuthFlows:
    @staticmethod
    def _register_web(client, monkeypatch, username="cookiesession"):
        monkeypatch.setattr(client_portal_auth, "PORTAL_COOKIE_SECURE", False)
        return client.post(
            "/client-portal/auth/register",
            headers={"X-Portal-Client": "web"},
            json={
                "email": f"{username}@example.com",
                "password": "strong-password-123",
                "username": username,
            },
        )

    def test_web_login_uses_short_httponly_cookie_without_json_bearer(
        self,
        client,
        db_for_test,
        monkeypatch,
    ):
        response = self._register_web(client, monkeypatch)
        assert response.status_code == 201
        assert response.json()["access_token"] is None

        set_cookies = response.headers.get_list("set-cookie")
        access_cookie = next(
            value for value in set_cookies
            if value.startswith("flirexa_portal_access=")
        )
        refresh_cookie = next(
            value for value in set_cookies
            if value.startswith("flirexa_portal_refresh=")
        )
        csrf_cookie = next(
            value for value in set_cookies
            if value.startswith("flirexa_portal_csrf=")
        )
        assert "HttpOnly" in access_cookie
        assert "HttpOnly" in refresh_cookie
        assert "SameSite=strict" in access_cookie
        assert "HttpOnly" not in csrf_cookie

        access_token = client.cookies.get("flirexa_portal_access")
        payload = client_portal.decode_access_token(access_token)
        assert payload["token_use"] == "portal_cookie"
        assert 13 * 60 <= payload["exp"] - payload["iat"] <= 16 * 60

        refresh_raw = client.cookies.get("flirexa_portal_refresh")
        stored = db_for_test.query(ClientRefreshToken).one()
        assert stored.token_hash == client_portal._refresh_token_hash(refresh_raw)
        assert refresh_raw not in stored.token_hash

        me = client.get("/client-portal/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "cookiesession"

    def test_production_cookie_names_are_host_only_and_secure(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.setattr(client_portal_auth, "PORTAL_COOKIE_SECURE", True)
        response = client.post(
            "/client-portal/auth/register",
            headers={"X-Portal-Client": "web"},
            json={
                "email": "secure-cookie@example.com",
                "password": "strong-password-123",
                "username": "securecookie",
            },
        )
        assert response.status_code == 201
        set_cookies = response.headers.get_list("set-cookie")
        assert len(set_cookies) == 3
        assert all(
            value.startswith("__Host-flirexa_portal_")
            and "Secure" in value
            and "Path=/" in value
            and "SameSite=strict" in value
            for value in set_cookies
        )

    def test_cookie_auth_requires_csrf_and_refresh_rotates_with_replay_defence(
        self,
        client,
        db_for_test,
        monkeypatch,
    ):
        response = self._register_web(
            client,
            monkeypatch,
            username="cookierotation",
        )
        assert response.status_code == 201

        rejected = client.post(
            "/client-portal/auth/change-password",
            json={
                "current_password": "strong-password-123",
                "new_password": "new-strong-password-456",
            },
        )
        assert rejected.status_code == 403
        assert rejected.json()["detail"] == "CSRF validation failed"

        old_refresh = client.cookies.get("flirexa_portal_refresh")
        csrf = client.cookies.get("flirexa_portal_csrf")
        refreshed = client.post(
            "/client-portal/auth/refresh",
            headers={"X-CSRF-Token": csrf},
        )
        assert refreshed.status_code == 200
        new_refresh = client.cookies.get("flirexa_portal_refresh")
        assert new_refresh != old_refresh

        rows = (
            db_for_test.query(ClientRefreshToken)
            .order_by(ClientRefreshToken.id)
            .all()
        )
        assert len(rows) == 2
        assert rows[0].revoked_at is not None
        assert rows[0].replaced_by_hash == rows[1].token_hash
        assert rows[0].family_id == rows[1].family_id

        # Replaying the consumed token revokes the replacement family too.
        # Clear the response-managed cookie jar first. Newer httpx versions
        # otherwise retain a domain-scoped replacement beside the manually set
        # host-only token and may serialize the replacement first, so the test
        # no longer sends the consumed token it claims to replay.
        replay_csrf = client.cookies.get("flirexa_portal_csrf")
        client.cookies.clear()
        client.cookies.set("flirexa_portal_refresh", old_refresh)
        client.cookies.set("flirexa_portal_csrf", replay_csrf)
        replay = client.post(
            "/client-portal/auth/refresh",
            headers={
                "X-CSRF-Token": client.cookies.get(
                    "flirexa_portal_csrf"
                )
            },
        )
        assert replay.status_code == 401
        assert replay.json()["detail"] == "Refresh token replay detected"
        db_for_test.expire_all()
        assert all(
            row.revoked_at is not None
            for row in db_for_test.query(ClientRefreshToken).all()
        )

    def test_mobile_bearer_contract_remains_long_lived(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.setattr(client_portal_auth, "PORTAL_COOKIE_SECURE", False)
        response = client.post("/client-portal/auth/register", json={
            "email": "mobile-bearer@example.com",
            "password": "strong-password-123",
            "username": "mobilebearer",
        })
        assert response.status_code == 201
        token = response.json()["access_token"]
        assert token
        assert not response.headers.get_list("set-cookie")

        payload = client_portal.decode_access_token(token)
        assert payload["token_use"] == "bearer"
        assert 89 * 86400 <= payload["exp"] - payload["iat"] <= 91 * 86400

        client.cookies.clear()
        me = client.get(
            "/client-portal/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me.status_code == 200
        assert me.json()["username"] == "mobilebearer"

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

    def test_tariff_popular_flag_roundtrips_and_can_be_cleared(self, client):
        payload = {
            "tier": "featured-plan",
            "name": "Featured",
            "description": "highlighted tier",
            "max_devices": 5,
            "traffic_limit_gb": 100,
            "bandwidth_limit_mbps": 50,
            "price_monthly_usd": 12.0,
            "is_active": True,
            "is_visible": True,
            "display_order": 5,
            "popular": True,
        }
        created = client.post("/api/v1/tariffs", json=payload)
        assert created.status_code == 201, created.text
        assert created.json()["popular"] is True

        tariff_id = created.json()["id"]
        updated = client.put(
            f"/api/v1/tariffs/{tariff_id}",
            json={"popular": False},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["popular"] is False


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
        assert data["items"][0]["address_pool_ipv4"] == "10.66.66.0/24"
        assert data["items"][0]["public_key"].startswith("TestServerPublicKey")

    def test_get_server(self, client):
        response = client.get("/api/v1/servers/1")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "wg0"
        assert data["listen_port"] == 57473

    def test_get_server_not_found(self, client):
        response = client.get("/api/v1/servers/999")
        assert response.status_code == 404

    def test_server_clients_response_contains_rows_and_ui_fields(self, client, db_for_test):
        db_for_test.add(Client(
            name="CardClient",
            server_id=1,
            public_key="CardPubKey" + "x" * 34,
            private_key="CardPrivKey" + "x" * 33,
            ipv4="10.66.66.12",
            ip_index=12,
            enabled=True,
            status=ClientStatus.ACTIVE,
            traffic_used_rx=1200,
            traffic_used_tx=3400,
        ))
        db_for_test.commit()

        response = client.get("/api/v1/servers/1/clients")
        assert response.status_code == 200
        data = response.json()
        assert data["client_count"] == 1
        assert data["clients"] == [{
            "id": data["clients"][0]["id"],
            "name": "CardClient",
            "ipv4": "10.66.66.12",
            "enabled": True,
            "status": "active",
            "traffic_used_rx": 1200,
            "traffic_used_tx": 3400,
        }]


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
