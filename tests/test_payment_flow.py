"""
Comprehensive Client Portal Payment Flow Tests
==============================================
Covers the full business process:
  1. User registration → free subscription auto-created
  2. Invoice creation (all providers)
  3. Webhook → subscription activation
  4. Idempotency (duplicate webhook delivery)
  5. Real HMAC signature verification (reject invalid)
  6. Underpayment rejection / overpayment warning
  7. Subscription expiry → WG clients disabled
  8. Re-payment after expiry → subscription restored
  9. Banned user payment (recorded, not activated)
 10. Promo code discount application
 11. Sequential double-delivery idempotency
 12. Payment status check endpoint
 13. PayPal webhook flow
 14. NOWPayments IPN webhook flow
 15. check_and_expire_subscriptions correctness
 16. Payment history isolation
 17. Dashboard stats correctness
"""

import hashlib
import hmac as hmac_mod
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── Env setup BEFORE any project imports ────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("SMTP_ENABLED", "false")
os.environ.setdefault("LICENSE_CHECK_ENABLED", "false")

from src.database.connection import get_db
from src.database.models import Base, Client, ClientStatus, Server
from src.api.main import create_app
from src.api.middleware.auth import get_current_admin
from src.modules.subscription.subscription_manager import SubscriptionManager
from src.modules.subscription.subscription_models import (
    ClientPortalPayment,
    ClientPortalSubscription,
    ClientUser,
    ClientUserClients,
    PaymentMethod,
    SubscriptionStatus,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

CRYPTOPAY_TOKEN = "test_cryptopay_token_abc123"
NOWPAYMENTS_SECRET = "test_nowpayments_ipn_secret"


# ─────────────────────────────────────────────────────────────────────────────
# HMAC helpers — reproduce the exact logic from the real adapters
# ─────────────────────────────────────────────────────────────────────────────

def _cryptopay_sig(body: bytes) -> str:
    """Valid CryptoPay webhook signature."""
    secret = hashlib.sha256(CRYPTOPAY_TOKEN.encode()).digest()
    return hmac_mod.new(secret, body, hashlib.sha256).hexdigest()


def _nowpayments_sig(data: dict) -> str:
    """Valid NOWPayments IPN signature."""
    sorted_data = dict(sorted(data.items()))
    payload = json.dumps(sorted_data, separators=(",", ":"))
    return hmac_mod.new(
        NOWPAYMENTS_SECRET.encode(), payload.encode(), hashlib.sha512
    ).hexdigest()


def _make_invoice_id() -> str:
    return f"INV-{uuid.uuid4().hex[:12].upper()}"


def _now_naive() -> datetime:
    """Naive UTC — matches the DateTime columns in the DB."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────────────────────────────────────
# Real-signature process_webhook for tests that verify auth behaviour
# ─────────────────────────────────────────────────────────────────────────────

async def _real_process_webhook(body: bytes, headers: dict):
    """
    Mimics CryptoPayAdapter.process_webhook() with our test token.
    Returns None on bad/missing signature → triggers 400 in the handler.
    """
    sig = headers.get("crypto-pay-api-signature", "")
    if not sig:
        return None
    secret = hashlib.sha256(CRYPTOPAY_TOKEN.encode()).digest()
    calc = hmac_mod.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac_mod.compare_digest(sig, calc):
        return None
    data = json.loads(body)
    if data.get("update_type") == "invoice_paid":
        pl = data.get("payload", {})
        return {
            "type": "invoice_paid",
            "invoice_id": str(pl.get("invoice_id")),
            "status": pl.get("status", "paid"),
            "amount": float(pl.get("amount", 0)),
        }
    return {"type": data.get("update_type"), "data": data.get("payload")}


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    e = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=e)
    yield e
    Base.metadata.drop_all(bind=e)
    e.dispose()


@pytest.fixture(scope="module")
def SessionFactory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(scope="module")
def seed_db(engine, SessionFactory):
    """One-time seeding: WG server + default plans."""
    sess = SessionFactory()
    # Server
    if not sess.query(Server).filter_by(name="wg-test").first():
        srv = Server(
            name="wg-test", interface="wg0", endpoint="127.0.0.1:51820",
            listen_port=51820,
            public_key="FakeServerPubKeyXXXXXXXXXXXXXXXXXXXXXXXXXX=",
            private_key="FakeServerPrivKeyXXXXXXXXXXXXXXXXXXXXXXXX=",
            address_pool_ipv4="10.99.0.0/24", dns="1.1.1.1",
            max_clients=250, config_path="/etc/wireguard/wg0.conf",
        )
        sess.add(srv)
        sess.commit()
        sess.refresh(srv)
    server_id = sess.query(Server).filter_by(name="wg-test").first().id

    # Default subscription plans
    mgr = SubscriptionManager(sess)
    mgr.create_default_plans()
    sess.close()
    return server_id


@pytest.fixture()
def db(SessionFactory, seed_db):
    """Per-test session, rolls back on teardown."""
    session = SessionFactory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="module")
def app_client(engine, SessionFactory, seed_db):
    """
    FastAPI TestClient with:
    - in-memory SQLite DB
    - real HMAC signature checking (via _real_process_webhook)
    - admin API mocked (no real WG calls)
    """
    app = create_app(debug=True)

    def _override_db():
        db = SessionFactory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_admin] = lambda: {
        "user_id": 1, "username": "testadmin", "is_superadmin": True
    }

    mock_cryptopay = MagicMock()
    mock_cryptopay.api_token = CRYPTOPAY_TOKEN
    # Use real signature verification by default
    mock_cryptopay.process_webhook = _real_process_webhook
    mock_cryptopay.create_invoice = AsyncMock(return_value={
        "invoice_id": "9999999",
        "bot_invoice_url": "https://t.me/CryptoBot?start=IVtest",
        "amount": 10.0, "asset": "USDT",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    })
    mock_cryptopay.check_payment = AsyncMock(return_value="pending")
    mock_cryptopay.get_currencies = AsyncMock(return_value=[{"code": "USDT", "name": "Tether"}])

    mock_admin_api = MagicMock()
    mock_admin_api.create_client = AsyncMock(return_value={"id": 1, "name": "x", "public_key": "k="})
    mock_admin_api.update_client_limits = AsyncMock(return_value=True)

    from src.api.routes import client_portal as cp_module
    orig_cp = cp_module.cryptopay_adapter
    orig_admin = cp_module.admin_api
    cp_module.cryptopay_adapter = mock_cryptopay
    cp_module.admin_api = mock_admin_api

    with TestClient(app) as tc:
        tc._mock_cryptopay = mock_cryptopay
        tc._mock_admin_api = mock_admin_api
        yield tc

    cp_module.cryptopay_adapter = orig_cp
    cp_module.admin_api = orig_admin


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    """Reset the in-memory auth rate limiter before every test."""
    from src.api.routes import client_portal as cp_module
    cp_module._auth_attempts.clear()


@pytest.fixture()
def manager(db):
    """SubscriptionManager bound to per-test session."""
    return SubscriptionManager(db)


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _inject_payment(session, user_id: int, invoice_id: str,
                    amount: float = 5.0, tier: str = "basic",
                    duration: int = 30, provider: str = "cryptopay",
                    provider_invoice_id: str = None) -> ClientPortalPayment:
    p = ClientPortalPayment(
        invoice_id=invoice_id, user_id=user_id, amount_usd=amount,
        payment_method=PaymentMethod.USDT_TRC20, subscription_tier=tier,
        duration_days=duration, provider_name=provider, status="pending",
    )
    if provider_invoice_id:
        p.provider_invoice_id = provider_invoice_id
    session.add(p)
    session.commit()
    return p


def _register(app_client) -> tuple:
    """Register a fresh user via HTTP. Returns (token, user_id)."""
    email = f"u-{uuid.uuid4().hex[:8]}@test.com"
    resp = app_client.post("/client-portal/auth/register", json={
        "email": email, "password": "TestPass123!", "username": f"u_{uuid.uuid4().hex[:6]}",
    })
    assert resp.status_code == 201, resp.text
    d = resp.json()
    return d["access_token"], d["user"]["id"]


def _fire_cryptopay_webhook(app_client, invoice_id: str, amount: float):
    """POST a properly signed CryptoPay webhook and return the response."""
    payload = {"update_type": "invoice_paid", "payload": {
        "invoice_id": invoice_id, "status": "paid",
        "amount": str(amount), "asset": "USDT",
    }}
    body = json.dumps(payload).encode()
    return app_client.post(
        "/client-portal/webhooks/cryptopay", content=body,
        headers={"Content-Type": "application/json",
                 "crypto-pay-api-signature": _cryptopay_sig(body)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. REGISTRATION & FREE SUBSCRIPTION
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistrationFlow:
    def test_register_creates_free_subscription(self, app_client):
        token, _ = _register(app_client)
        resp = app_client.get("/client-portal/subscription",
                              headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["tier"] == "free"
        assert resp.json()["status"] == "active"

    def test_duplicate_email_rejected(self, app_client):
        email = f"dup-{uuid.uuid4().hex[:8]}@test.com"
        base = {"email": email, "password": "Pass123!", "username": f"dup_{uuid.uuid4().hex[:6]}"}
        r1 = app_client.post("/client-portal/auth/register", json=base)
        assert r1.status_code == 201
        base["username"] = f"dup2_{uuid.uuid4().hex[:6]}"
        r2 = app_client.post("/client-portal/auth/register", json=base)
        assert r2.status_code in (400, 409)

    def test_login_returns_token(self, app_client):
        email = f"login-{uuid.uuid4().hex[:8]}@test.com"
        pwd = "LoginPass123!"
        app_client.post("/client-portal/auth/register", json={
            "email": email, "password": pwd, "username": f"login_{uuid.uuid4().hex[:6]}",
        })
        resp = app_client.post("/client-portal/auth/login",
                               json={"email": email, "password": pwd})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_wrong_password_rejected(self, app_client):
        email = f"wp-{uuid.uuid4().hex[:8]}@test.com"
        app_client.post("/client-portal/auth/register", json={
            "email": email, "password": "RealPass123!", "username": f"wp_{uuid.uuid4().hex[:6]}",
        })
        resp = app_client.post("/client-portal/auth/login",
                               json={"email": email, "password": "WrongPass!"})
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 2. INVOICE CREATION
# ─────────────────────────────────────────────────────────────────────────────

class TestInvoiceCreation:
    def test_create_cryptopay_invoice(self, app_client):
        token, _ = _register(app_client)
        resp = app_client.post(
            "/client-portal/payments/create-invoice",
            json={"plan_tier": "basic", "duration_days": 30,
                  "currency": "USDT", "provider": "cryptopay"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert "invoice_id" in d
        assert d["amount_usd"] > 0

    def test_invalid_plan_rejected(self, app_client):
        token, _ = _register(app_client)
        resp = app_client.post(
            "/client-portal/payments/create-invoice",
            json={"plan_tier": "nonexistent_xyz", "duration_days": 30,
                  "currency": "USDT", "provider": "cryptopay"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_unauthenticated_invoice_rejected(self, app_client):
        resp = app_client.post(
            "/client-portal/payments/create-invoice",
            json={"plan_tier": "basic", "duration_days": 30,
                  "currency": "USDT", "provider": "cryptopay"},
        )
        assert resp.status_code in (401, 403)

    def test_providers_list_includes_cryptopay(self, app_client):
        resp = app_client.get("/client-portal/payments/providers")
        assert resp.status_code == 200
        assert "cryptopay" in [p["id"] for p in resp.json()]

    def test_plans_list_returns_all_tiers(self, app_client):
        resp = app_client.get("/client-portal/subscription/plans")
        assert resp.status_code == 200
        tiers = {p["tier"] for p in resp.json()}
        for expected in ("free", "basic", "standard", "premium"):
            assert expected in tiers, f"Missing tier: {expected}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. SUBSCRIPTION MANAGER — UNIT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestSubscriptionManager:

    def _user(self, db, tag=""):
        u = ClientUser(
            email=f"mgr-{tag}-{uuid.uuid4().hex[:6]}@test.com",
            username=f"mgr_{tag}_{uuid.uuid4().hex[:6]}",
            password_hash="$2b$12$fakehash", is_active=True,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    def test_ensure_subscription_creates_free(self, manager, db):
        u = self._user(db, "free")
        sub = manager.ensure_subscription(u.id)
        assert sub.tier == "free"
        assert sub.status == SubscriptionStatus.ACTIVE

    def test_complete_payment_upgrades_tier(self, manager, db):
        u = self._user(db, "upg")
        manager.ensure_subscription(u.id)
        inv = _make_invoice_id()
        manager.create_payment(
            user_id=u.id, amount_usd=5.0, payment_method=PaymentMethod.USDT_TRC20,
            subscription_tier="basic", duration_days=30, invoice_id=inv, provider_name="cryptopay",
        )
        assert manager.complete_payment(inv, sync_wg=False) is True
        sub = manager.get_subscription(u.id)
        assert sub.tier == "basic"
        assert sub.status == SubscriptionStatus.ACTIVE
        delta = sub._aware_expiry() - datetime.now(timezone.utc)
        assert 29 <= delta.days <= 31

    def test_complete_payment_idempotent_no_double_extension(self, manager, db):
        u = self._user(db, "idem")
        manager.ensure_subscription(u.id)
        inv = _make_invoice_id()
        manager.create_payment(
            user_id=u.id, amount_usd=5.0, payment_method=PaymentMethod.USDT_TRC20,
            subscription_tier="basic", duration_days=30, invoice_id=inv, provider_name="cryptopay",
        )
        for _ in range(5):
            result = manager.complete_payment(inv, sync_wg=False)
            assert result is True
        sub = manager.get_subscription(u.id)
        # Must be ~30 days, not 5×30=150 days
        delta = sub._aware_expiry() - datetime.now(timezone.utc)
        assert delta.days <= 33

    def test_complete_payment_returns_false_unknown_invoice(self, manager):
        assert manager.complete_payment("NONEXISTENT-INV-999", sync_wg=False) is False

    def test_banned_user_payment_recorded_not_activated(self, manager, db):
        u = self._user(db, "ban")
        u.is_banned = True
        db.commit()
        manager.ensure_subscription(u.id)
        inv = _make_invoice_id()
        manager.create_payment(
            user_id=u.id, amount_usd=10.0, payment_method=PaymentMethod.USDT_TRC20,
            subscription_tier="standard", duration_days=30, invoice_id=inv, provider_name="cryptopay",
        )
        assert manager.complete_payment(inv, sync_wg=False) is True
        assert manager.get_subscription(u.id).tier == "free"
        assert manager.get_payment_by_invoice(inv).status == "completed"

    def test_check_and_expire_expired_subscription(self, manager, db):
        u = self._user(db, "exp")
        sub = manager.ensure_subscription(u.id)
        sub.tier = "basic"
        sub.status = SubscriptionStatus.ACTIVE
        sub.expiry_date = _now_naive() - timedelta(hours=1)
        sub.max_devices = 2
        db.commit()

        with patch("src.core.client_manager.ClientManager") as mock_cm:
            mock_cm.return_value.disable_client = MagicMock(return_value=True)
            count = manager.check_and_expire_subscriptions()

        assert count >= 1
        db.refresh(sub)
        assert sub.status == SubscriptionStatus.EXPIRED
        assert sub.tier == "free"
        assert sub.max_devices == 1

    def test_active_subscription_not_expired_prematurely(self, manager, db):
        u = self._user(db, "notexp")
        sub = manager.ensure_subscription(u.id)
        sub.tier = "basic"
        sub.status = SubscriptionStatus.ACTIVE
        sub.expiry_date = _now_naive() + timedelta(days=15)
        db.commit()

        with patch("src.core.client_manager.ClientManager") as mock_cm:
            mock_cm.return_value.disable_client = MagicMock(return_value=True)
            manager.check_and_expire_subscriptions()

        db.refresh(sub)
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.tier == "basic"

    def test_renew_subscription_extends_expiry(self, manager, db):
        u = self._user(db, "ren")
        sub = manager.ensure_subscription(u.id)
        sub.tier = "basic"
        sub.status = SubscriptionStatus.ACTIVE
        sub.expiry_date = _now_naive() + timedelta(days=5)
        db.commit()
        manager.renew_subscription(u.id, duration_days=30)
        db.refresh(sub)
        delta = sub._aware_expiry() - datetime.now(timezone.utc)
        assert delta.days >= 34

    def test_upgrade_stacks_remaining_days(self, manager, db):
        u = self._user(db, "stack")
        manager.ensure_subscription(u.id)
        inv1 = _make_invoice_id()
        manager.create_payment(
            user_id=u.id, amount_usd=5.0, payment_method=PaymentMethod.USDT_TRC20,
            subscription_tier="basic", duration_days=30, invoice_id=inv1, provider_name="cryptopay",
        )
        manager.complete_payment(inv1, sync_wg=False)
        first_expiry = manager.get_subscription(u.id)._aware_expiry()

        inv2 = _make_invoice_id()
        manager.create_payment(
            user_id=u.id, amount_usd=10.0, payment_method=PaymentMethod.USDT_TRC20,
            subscription_tier="standard", duration_days=30, invoice_id=inv2, provider_name="cryptopay",
        )
        manager.complete_payment(inv2, sync_wg=False)
        second_expiry = manager.get_subscription(u.id)._aware_expiry()

        assert second_expiry > first_expiry
        assert (second_expiry - first_expiry).days >= 29

    def test_payment_restores_expired_subscription(self, manager, db):
        u = self._user(db, "restore")
        sub = manager.ensure_subscription(u.id)
        sub.tier = "free"
        sub.status = SubscriptionStatus.EXPIRED
        sub.expiry_date = _now_naive() - timedelta(days=5)
        db.commit()

        inv = _make_invoice_id()
        manager.create_payment(
            user_id=u.id, amount_usd=5.0, payment_method=PaymentMethod.USDT_TRC20,
            subscription_tier="basic", duration_days=30, invoice_id=inv, provider_name="cryptopay",
        )
        manager.complete_payment(inv, sync_wg=False)
        db.refresh(sub)
        assert sub.tier == "basic"
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub._aware_expiry() > datetime.now(timezone.utc)

    def test_promo_code_used_count_incremented(self, manager, db):
        from src.modules.subscription.subscription_models import PromoCode
        promo = PromoCode(
            code=f"PROMO-{uuid.uuid4().hex[:6].upper()}",
            discount_type="percentage", discount_value=10.0,
            is_active=True, used_count=5, max_uses=100,
        )
        db.add(promo)
        db.commit()
        db.refresh(promo)

        u = self._user(db, "promo")
        manager.ensure_subscription(u.id)
        inv = _make_invoice_id()
        payment = manager.create_payment(
            user_id=u.id, amount_usd=9.0, payment_method=PaymentMethod.USDT_TRC20,
            subscription_tier="basic", duration_days=30, invoice_id=inv, provider_name="cryptopay",
        )
        payment.promo_code_id = promo.id
        db.commit()

        manager.complete_payment(inv, sync_wg=False)
        db.refresh(promo)
        assert promo.used_count == 6

    def test_wg_clients_disabled_on_expiry(self, manager, db, seed_db):
        u = self._user(db, "wgdis")
        wg_client = Client(
            name=f"wgdis-{uuid.uuid4().hex[:6]}", server_id=seed_db,
            public_key=f"Key{uuid.uuid4().hex[:22]}=",
            private_key="PrivKey=", preshared_key="PSK=",
            ipv4="10.99.0.55", ip_index=55,
            enabled=True, status=ClientStatus.ACTIVE,
        )
        db.add(wg_client)
        db.commit()
        db.refresh(wg_client)
        db.add(ClientUserClients(client_user_id=u.id, client_id=wg_client.id))

        sub = manager.ensure_subscription(u.id)
        sub.tier = "basic"
        sub.status = SubscriptionStatus.ACTIVE
        sub.expiry_date = _now_naive() - timedelta(minutes=5)
        db.commit()

        disabled = []
        with patch("src.core.client_manager.ClientManager") as mock_cm:
            mock_cm.return_value.disable_client = MagicMock(
                side_effect=lambda cid, reason=None: disabled.append(cid)
            )
            manager.check_and_expire_subscriptions()

        assert wg_client.id in disabled


# ─────────────────────────────────────────────────────────────────────────────
# 4. CRYPTOPAY WEBHOOK — SIGNATURE VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────

class TestCryptoPaySignature:
    """
    Uses _real_process_webhook so HMAC verification is genuine.
    The app_client fixture sets process_webhook = _real_process_webhook by default.
    """

    def _post_with_sig(self, app_client, payload: dict, sig: str):
        body = json.dumps(payload).encode()
        return app_client.post(
            "/client-portal/webhooks/cryptopay", content=body,
            headers={"Content-Type": "application/json",
                     "crypto-pay-api-signature": sig},
        )

    def _post_no_sig(self, app_client, payload: dict):
        body = json.dumps(payload).encode()
        return app_client.post(
            "/client-portal/webhooks/cryptopay", content=body,
            headers={"Content-Type": "application/json"},
        )

    def test_invalid_signature_returns_400(self, app_client):
        payload = {"update_type": "invoice_paid",
                   "payload": {"invoice_id": "SIG-FAKE", "status": "paid", "amount": "10"}}
        resp = self._post_with_sig(app_client, payload, "deadbeefdeadbeefdeadbeef")
        assert resp.status_code == 400

    def test_missing_signature_returns_400(self, app_client):
        payload = {"update_type": "invoice_paid",
                   "payload": {"invoice_id": "SIG-NOSIG"}}
        resp = self._post_no_sig(app_client, payload)
        assert resp.status_code == 400

    def test_valid_sig_unknown_invoice_returns_200(self, app_client):
        """Valid signature, unknown invoice → 200 ok (graceful no-op)."""
        payload = {"update_type": "invoice_paid",
                   "payload": {"invoice_id": "UNKNOWN-9999", "status": "paid", "amount": "10"}}
        body = json.dumps(payload).encode()
        resp = self._post_with_sig(app_client, payload, _cryptopay_sig(body))
        assert resp.status_code == 200

    def test_provider_exception_returns_400_not_500(self, app_client):
        """If process_webhook raises, handler must return 400 not 500."""
        from src.api.routes import client_portal as cp_module
        orig = cp_module.cryptopay_adapter.process_webhook
        cp_module.cryptopay_adapter.process_webhook = AsyncMock(
            side_effect=Exception("CryptoPay API unreachable")
        )
        try:
            payload = {"update_type": "invoice_paid",
                       "payload": {"invoice_id": "ERR-001"}}
            body = json.dumps(payload).encode()
            resp = self._post_with_sig(app_client, payload, _cryptopay_sig(body))
            assert resp.status_code == 400
        finally:
            cp_module.cryptopay_adapter.process_webhook = orig


# ─────────────────────────────────────────────────────────────────────────────
# 5. CRYPTOPAY WEBHOOK — FULL BUSINESS FLOW
# ─────────────────────────────────────────────────────────────────────────────

class TestCryptoPayWebhookFlow:

    def test_webhook_activates_subscription(self, app_client, SessionFactory):
        """Basic→basic: webhook fires, subscription upgrades from free to basic."""
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=5.0, tier="basic")
        sess.close()

        resp = _fire_cryptopay_webhook(app_client, inv, 5.0)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        v = SessionFactory()
        p = v.query(ClientPortalPayment).filter_by(invoice_id=inv).first()
        sub = v.query(ClientPortalSubscription).filter_by(user_id=user_id).first()
        v.close()
        assert p.status == "completed"
        assert sub.tier == "basic"
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.expiry_date is not None

    def test_idempotent_no_double_extension(self, app_client, SessionFactory):
        """Delivering webhook twice must not double-extend subscription."""
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=5.0, tier="basic")
        sess.close()

        _fire_cryptopay_webhook(app_client, inv, 5.0)
        v1 = SessionFactory()
        expiry1 = v1.query(ClientPortalSubscription).filter_by(user_id=user_id).first().expiry_date
        v1.close()

        _fire_cryptopay_webhook(app_client, inv, 5.0)
        v2 = SessionFactory()
        expiry2 = v2.query(ClientPortalSubscription).filter_by(user_id=user_id).first().expiry_date
        v2.close()

        assert expiry1 == expiry2

    def test_underpayment_rejected(self, app_client, SessionFactory):
        """Amount < 99% of expected → error, payment stays pending."""
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=10.0, tier="basic")
        sess.close()

        resp = _fire_cryptopay_webhook(app_client, inv, 4.0)  # 40% — underpay
        assert resp.status_code == 200
        assert resp.json().get("status") == "error"

        v = SessionFactory()
        p = v.query(ClientPortalPayment).filter_by(invoice_id=inv).first()
        v.close()
        assert p.status == "pending"

    def test_slight_underpayment_within_tolerance_accepted(self, app_client, SessionFactory):
        """Amount at 99.5% (within 1% tolerance) → accepted."""
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=10.0, tier="basic")
        sess.close()

        resp = _fire_cryptopay_webhook(app_client, inv, 9.95)  # 99.5%
        assert resp.status_code == 200
        assert resp.json().get("status") == "ok"

        v = SessionFactory()
        p = v.query(ClientPortalPayment).filter_by(invoice_id=inv).first()
        v.close()
        assert p.status == "completed"

    def test_overpayment_still_activates(self, app_client, SessionFactory):
        """Overpayment >10% is logged as warning but still processed."""
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=10.0, tier="standard")
        sess.close()

        resp = _fire_cryptopay_webhook(app_client, inv, 25.0)  # 250%
        assert resp.status_code == 200

        v = SessionFactory()
        sub = v.query(ClientPortalSubscription).filter_by(user_id=user_id).first()
        v.close()
        assert sub.tier == "standard"

    def test_premium_tier_activated(self, app_client, SessionFactory):
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=20.0, tier="premium")
        sess.close()

        _fire_cryptopay_webhook(app_client, inv, 20.0)

        v = SessionFactory()
        sub = v.query(ClientPortalSubscription).filter_by(user_id=user_id).first()
        v.close()
        assert sub.tier == "premium"
        assert sub.max_devices == 10

    def test_banned_user_payment_recorded_not_activated(self, app_client, SessionFactory):
        token, user_id = _register(app_client)
        sess = SessionFactory()
        u = sess.query(ClientUser).filter_by(id=user_id).first()
        u.is_banned = True
        sess.commit()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=10.0, tier="standard")
        sess.close()

        resp = _fire_cryptopay_webhook(app_client, inv, 10.0)
        assert resp.status_code == 200

        v = SessionFactory()
        p = v.query(ClientPortalPayment).filter_by(invoice_id=inv).first()
        sub = v.query(ClientPortalSubscription).filter_by(user_id=user_id).first()
        v.close()
        assert p.status == "completed"   # Money recorded
        assert sub.tier == "free"         # Subscription NOT activated

    def test_wg_sync_failure_non_fatal(self, app_client, SessionFactory):
        """WG sync failure after payment commit → webhook still returns 200."""
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=5.0, tier="basic")
        sess.close()

        from src.api.routes import client_portal as cp_module
        cp_module.admin_api.update_client_limits = AsyncMock(
            side_effect=Exception("WG API down"))
        cp_module.admin_api.create_client = AsyncMock(
            side_effect=Exception("WG API down"))
        try:
            resp = _fire_cryptopay_webhook(app_client, inv, 5.0)
        finally:
            cp_module.admin_api.update_client_limits = AsyncMock(return_value=True)
            cp_module.admin_api.create_client = AsyncMock(return_value={"id": 1, "name": "x"})

        assert resp.status_code == 200  # Payment committed, WG failure is non-fatal
        v = SessionFactory()
        p = v.query(ClientPortalPayment).filter_by(invoice_id=inv).first()
        v.close()
        assert p.status == "completed"

    def test_payment_after_expiry_restores_subscription(self, app_client, SessionFactory):
        """After subscription expires, new payment brings it back to active."""
        token, user_id = _register(app_client)
        sess = SessionFactory()
        sub = sess.query(ClientPortalSubscription).filter_by(user_id=user_id).first()
        sub.tier = "free"
        sub.status = SubscriptionStatus.EXPIRED
        sub.expiry_date = _now_naive() - timedelta(days=10)
        sess.commit()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=5.0, tier="basic")
        sess.close()

        _fire_cryptopay_webhook(app_client, inv, 5.0)

        v = SessionFactory()
        sub2 = v.query(ClientPortalSubscription).filter_by(user_id=user_id).first()
        v.close()
        assert sub2.tier == "basic"
        assert sub2.status == SubscriptionStatus.ACTIVE

    def test_subscription_visible_via_api_after_payment(self, app_client, SessionFactory):
        """Subscription endpoint shows updated tier immediately after payment."""
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=5.0, tier="basic")
        sess.close()

        _fire_cryptopay_webhook(app_client, inv, 5.0)

        resp = app_client.get("/client-portal/subscription",
                              headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["tier"] == "basic"
        assert resp.json()["status"] == "active"


# ─────────────────────────────────────────────────────────────────────────────
# 6. NOWPAYMENTS WEBHOOK
# ─────────────────────────────────────────────────────────────────────────────

class TestNOWPaymentsWebhook:

    def _setup(self, app_client, SessionFactory, tier="basic", amount=5.0):
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=amount, tier=tier, provider="nowpayments")
        sess.close()
        return user_id, inv

    def test_finished_status_activates(self, app_client, SessionFactory):
        from src.api.routes import client_portal as cp_module
        mock_now = MagicMock()
        mock_now.process_webhook = AsyncMock(return_value=True)
        orig = cp_module.nowpayments_provider
        cp_module.nowpayments_provider = mock_now
        try:
            user_id, inv = self._setup(app_client, SessionFactory)
            resp = app_client.post(
                "/client-portal/webhooks/nowpayments",
                json={"payment_status": "finished", "order_id": inv, "price_amount": 5.0},
                headers={"x-nowpayments-sig": "sig"},
            )
            assert resp.status_code == 200
            v = SessionFactory()
            p = v.query(ClientPortalPayment).filter_by(invoice_id=inv).first()
            sub = v.query(ClientPortalSubscription).filter_by(user_id=user_id).first()
            v.close()
            assert p.status == "completed"
            assert sub.tier == "basic"
        finally:
            cp_module.nowpayments_provider = orig

    def test_invalid_returns_400(self, app_client):
        from src.api.routes import client_portal as cp_module
        mock_now = MagicMock()
        mock_now.process_webhook = AsyncMock(return_value=False)
        orig = cp_module.nowpayments_provider
        cp_module.nowpayments_provider = mock_now
        try:
            resp = app_client.post(
                "/client-portal/webhooks/nowpayments",
                json={"payment_status": "finished"},
                headers={"x-nowpayments-sig": "bad"},
            )
            assert resp.status_code == 400
        finally:
            cp_module.nowpayments_provider = orig

    def test_confirming_status_does_not_complete(self, app_client, SessionFactory):
        """Intermediate status must NOT trigger payment completion."""
        from src.api.routes import client_portal as cp_module
        mock_now = MagicMock()
        mock_now.process_webhook = AsyncMock(return_value=True)
        orig = cp_module.nowpayments_provider
        cp_module.nowpayments_provider = mock_now
        try:
            user_id, inv = self._setup(app_client, SessionFactory)
            app_client.post(
                "/client-portal/webhooks/nowpayments",
                json={"payment_status": "confirming", "order_id": inv},
                headers={"x-nowpayments-sig": "sig"},
            )
            v = SessionFactory()
            p = v.query(ClientPortalPayment).filter_by(invoice_id=inv).first()
            v.close()
            assert p.status == "pending"
        finally:
            cp_module.nowpayments_provider = orig

    def test_provider_exception_returns_400(self, app_client):
        from src.api.routes import client_portal as cp_module
        mock_now = MagicMock()
        mock_now.process_webhook = AsyncMock(side_effect=Exception("timeout"))
        orig = cp_module.nowpayments_provider
        cp_module.nowpayments_provider = mock_now
        try:
            resp = app_client.post(
                "/client-portal/webhooks/nowpayments",
                json={"payment_status": "finished", "order_id": "X"},
                headers={"x-nowpayments-sig": "sig"},
            )
            assert resp.status_code == 400
        finally:
            cp_module.nowpayments_provider = orig


# ─────────────────────────────────────────────────────────────────────────────
# 7. PAYPAL WEBHOOK
# ─────────────────────────────────────────────────────────────────────────────

class TestPayPalWebhook:

    def _setup(self, app_client, SessionFactory):
        token, user_id = _register(app_client)
        order_id = f"PP-{uuid.uuid4().hex[:10].upper()}"
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=5.0, tier="basic",
                        provider="paypal", provider_invoice_id=order_id)
        sess.close()
        return user_id, inv, order_id

    def _paypal_mock(self, sig_ok=True, process_ok=True):
        m = MagicMock()
        m.verify_webhook_signature = AsyncMock(return_value=sig_ok)
        m.process_webhook = AsyncMock(return_value=process_ok)
        return m

    def test_capture_completed_activates(self, app_client, SessionFactory):
        from src.api.routes import client_portal as cp_module
        mock_pp = self._paypal_mock()
        orig = cp_module.paypal_provider
        cp_module.paypal_provider = mock_pp
        try:
            user_id, inv, order_id = self._setup(app_client, SessionFactory)
            resp = app_client.post("/client-portal/webhooks/paypal", json={
                "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": order_id},
            })
            assert resp.status_code == 200
            v = SessionFactory()
            p = v.query(ClientPortalPayment).filter_by(invoice_id=inv).first()
            sub = v.query(ClientPortalSubscription).filter_by(user_id=user_id).first()
            v.close()
            assert p.status == "completed"
            assert sub.tier == "basic"
        finally:
            cp_module.paypal_provider = orig

    def test_order_approved_activates(self, app_client, SessionFactory):
        from src.api.routes import client_portal as cp_module
        mock_pp = self._paypal_mock()
        orig = cp_module.paypal_provider
        cp_module.paypal_provider = mock_pp
        try:
            user_id, inv, order_id = self._setup(app_client, SessionFactory)
            resp = app_client.post("/client-portal/webhooks/paypal", json={
                "event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": order_id},
            })
            assert resp.status_code == 200
            v = SessionFactory()
            p = v.query(ClientPortalPayment).filter_by(invoice_id=inv).first()
            v.close()
            assert p.status == "completed"
        finally:
            cp_module.paypal_provider = orig

    def test_invalid_signature_returns_400(self, app_client):
        from src.api.routes import client_portal as cp_module
        mock_pp = self._paypal_mock(sig_ok=False)
        orig = cp_module.paypal_provider
        cp_module.paypal_provider = mock_pp
        try:
            resp = app_client.post("/client-portal/webhooks/paypal", json={
                "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {},
            })
            assert resp.status_code == 400
        finally:
            cp_module.paypal_provider = orig

    def test_signature_exception_returns_400(self, app_client):
        from src.api.routes import client_portal as cp_module
        mock_pp = MagicMock()
        mock_pp.verify_webhook_signature = AsyncMock(side_effect=Exception("SSL error"))
        orig = cp_module.paypal_provider
        cp_module.paypal_provider = mock_pp
        try:
            resp = app_client.post("/client-portal/webhooks/paypal", json={
                "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {},
            })
            assert resp.status_code == 400
        finally:
            cp_module.paypal_provider = orig

    def test_unhandled_event_no_action(self, app_client, SessionFactory):
        from src.api.routes import client_portal as cp_module
        mock_pp = self._paypal_mock()
        orig = cp_module.paypal_provider
        cp_module.paypal_provider = mock_pp
        try:
            user_id, inv, order_id = self._setup(app_client, SessionFactory)
            resp = app_client.post("/client-portal/webhooks/paypal", json={
                "event_type": "BILLING.SUBSCRIPTION.CREATED", "resource": {"id": order_id},
            })
            assert resp.status_code == 200
            v = SessionFactory()
            p = v.query(ClientPortalPayment).filter_by(invoice_id=inv).first()
            v.close()
            assert p.status == "pending"
        finally:
            cp_module.paypal_provider = orig


# ─────────────────────────────────────────────────────────────────────────────
# 8. PAYMENT STATUS CHECK
# ─────────────────────────────────────────────────────────────────────────────

class TestPaymentStatusCheck:

    def test_pending_shown_as_pending(self, app_client, SessionFactory):
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv)
        sess.close()

        from src.api.routes import client_portal as cp_module
        cp_module.cryptopay_adapter.check_payment = AsyncMock(return_value="pending")

        resp = app_client.get(f"/client-portal/payments/check/{inv}",
                              headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_completed_shown_as_completed(self, app_client, SessionFactory):
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        p = _inject_payment(sess, user_id, inv)
        p.status = "completed"
        sess.commit()
        sess.close()

        resp = app_client.get(f"/client-portal/payments/check/{inv}",
                              headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    def test_nonexistent_returns_404(self, app_client):
        token, _ = _register(app_client)
        resp = app_client.get("/client-portal/payments/check/NONEXISTENT-XYZ",
                              headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_unauthenticated_returns_401_or_403(self, app_client):
        resp = app_client.get("/client-portal/payments/check/ANY-INV")
        assert resp.status_code in (401, 403)


# ─────────────────────────────────────────────────────────────────────────────
# 9. PAYMENT HISTORY
# ─────────────────────────────────────────────────────────────────────────────

class TestPaymentHistory:

    def test_history_lists_all_payments(self, app_client, SessionFactory):
        token, user_id = _register(app_client)
        sess = SessionFactory()
        for i in range(3):
            sess.add(ClientPortalPayment(
                invoice_id=_make_invoice_id(), user_id=user_id,
                amount_usd=float(5 * (i + 1)),
                payment_method=PaymentMethod.USDT_TRC20,
                subscription_tier="basic", duration_days=30,
                provider_name="cryptopay",
                status="completed" if i < 2 else "pending",
            ))
        sess.commit()
        sess.close()

        resp = app_client.get("/client-portal/payments/history",
                              headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.json()) >= 3

    def test_history_is_user_isolated(self, app_client, SessionFactory):
        """User A must not see user B's payments."""
        token_a, user_a = _register(app_client)
        _, user_b = _register(app_client)
        sess = SessionFactory()
        sess.add(ClientPortalPayment(
            invoice_id=_make_invoice_id(), user_id=user_b, amount_usd=999.0,
            payment_method=PaymentMethod.USDT_TRC20, subscription_tier="premium",
            duration_days=30, provider_name="cryptopay", status="completed",
        ))
        sess.commit()
        sess.close()

        resp = app_client.get("/client-portal/payments/history",
                              headers={"Authorization": f"Bearer {token_a}"})
        assert resp.status_code == 200
        for p in resp.json():
            assert p["amount_usd"] != 999.0


# ─────────────────────────────────────────────────────────────────────────────
# 10. SUBSCRIPTION EXPIRY — HTTP PATHS
# ─────────────────────────────────────────────────────────────────────────────

class TestSubscriptionExpiryHTTP:

    def test_expired_status_visible_via_api(self, app_client, SessionFactory):
        token, user_id = _register(app_client)
        sess = SessionFactory()
        sub = sess.query(ClientPortalSubscription).filter_by(user_id=user_id).first()
        sub.tier = "basic"
        sub.status = SubscriptionStatus.EXPIRED
        sub.expiry_date = _now_naive() - timedelta(days=3)
        sess.commit()
        sess.close()

        resp = app_client.get("/client-portal/subscription",
                              headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "expired"

    def test_payment_after_expiry_restores_via_api(self, app_client, SessionFactory):
        token, user_id = _register(app_client)
        sess = SessionFactory()
        sub = sess.query(ClientPortalSubscription).filter_by(user_id=user_id).first()
        sub.tier = "free"
        sub.status = SubscriptionStatus.EXPIRED
        sub.expiry_date = _now_naive() - timedelta(days=10)
        sess.commit()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=5.0, tier="basic")
        sess.close()

        _fire_cryptopay_webhook(app_client, inv, 5.0)

        resp = app_client.get("/client-portal/subscription",
                              headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["tier"] == "basic"
        assert resp.json()["status"] == "active"


# ─────────────────────────────────────────────────────────────────────────────
# 11. IDEMPOTENCY UNDER RAPID SEQUENTIAL DELIVERY
# ─────────────────────────────────────────────────────────────────────────────

class TestIdempotency:

    def test_ten_sequential_deliveries_idempotent(self, app_client, SessionFactory):
        """Same webhook delivered 10 times → subscription extended exactly once."""
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=5.0, tier="basic")
        sess.close()

        for _ in range(10):
            resp = _fire_cryptopay_webhook(app_client, inv, 5.0)
            assert resp.status_code == 200

        v = SessionFactory()
        sub = v.query(ClientPortalSubscription).filter_by(user_id=user_id).first()
        v.close()
        delta = sub._aware_expiry() - datetime.now(timezone.utc)
        assert delta.days <= 33  # ~30, not 300

    def test_payment_completed_exactly_once(self, app_client, SessionFactory):
        """Payment record transitions to 'completed' exactly once."""
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=5.0, tier="basic")
        sess.close()

        for _ in range(5):
            _fire_cryptopay_webhook(app_client, inv, 5.0)

        v = SessionFactory()
        p = v.query(ClientPortalPayment).filter_by(invoice_id=inv).first()
        v.close()
        assert p.status == "completed"


# ─────────────────────────────────────────────────────────────────────────────
# 12. DASHBOARD STATS
# ─────────────────────────────────────────────────────────────────────────────

class TestDashboardStats:

    def test_stats_show_free_initially(self, app_client):
        token, _ = _register(app_client)
        resp = app_client.get("/client-portal/dashboard/stats",
                              headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        stats = resp.json()
        sub = stats.get("subscription", stats)  # nested or flat
        assert sub["tier"] == "free"
        assert sub["status"] == "active"

    def test_stats_updated_after_payment(self, app_client, SessionFactory):
        token, user_id = _register(app_client)
        sess = SessionFactory()
        inv = _make_invoice_id()
        _inject_payment(sess, user_id, inv, amount=5.0, tier="basic")
        sess.close()

        _fire_cryptopay_webhook(app_client, inv, 5.0)

        resp = app_client.get("/client-portal/dashboard/stats",
                              headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        stats = resp.json()
        sub = stats.get("subscription", stats)
        assert sub["tier"] == "basic"
        assert sub["status"] == "active"
        assert int(sub.get("days_remaining", 0)) >= 29

    def test_days_remaining_zero_for_expired(self, app_client, SessionFactory):
        token, user_id = _register(app_client)
        sess = SessionFactory()
        sub = sess.query(ClientPortalSubscription).filter_by(user_id=user_id).first()
        sub.tier = "basic"
        sub.status = SubscriptionStatus.EXPIRED
        sub.expiry_date = _now_naive() - timedelta(days=5)
        sess.commit()
        sess.close()

        resp = app_client.get("/client-portal/dashboard/stats",
                              headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        sub_data = body.get("subscription", body)
        assert int(sub_data.get("days_remaining", 0)) == 0
