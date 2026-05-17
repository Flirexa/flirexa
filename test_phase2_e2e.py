"""
Phase 2 E2E Verification — Crypto Subscription Billing
Read-only verification: TC1–TC10.  Writes to /tmp/phase2_e2e.db only.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest

# ── 1. Constants ──────────────────────────────────────────────────────────────

TEST_DB              = "/tmp/phase2_e2e.db"
KEYS_DIR             = Path("/root/spongebot_new/license_server/keys")
LICENSE_PRIVATE_KEY  = Path("/root/.flirexa-secrets/license-signing-keys/license_private.pem")
MIGRATION_SCRIPT     = Path("/root/spongebot_new/tools/migrate_subscription_schema.py")

# ── 2. Set env vars BEFORE any app code imports ───────────────────────────────

os.environ["DATABASE_PATH"]                  = TEST_DB
os.environ["DATABASE_URL"]                   = f"sqlite:///{TEST_DB}"
os.environ["SQLITE_DB_PATH"]                 = TEST_DB
os.environ["NOWPAYMENTS_API_KEY"]            = "test_key"
os.environ["NOWPAYMENTS_IPN_SECRET"]         = "test_secret"
os.environ["ADMIN_TOKEN"]                    = "test_admin"
os.environ["PANEL_USERNAME"]                 = "test"
os.environ["PANEL_PASSWORD"]                 = "test"
os.environ["LICENSE_PRIVATE_KEY_PATH"]       = str(LICENSE_PRIVATE_KEY)
os.environ["SERVER_VERIFY_PRIVATE_KEY_PATH"] = str(KEYS_DIR / "server_verify_private.pem")
os.environ["SERVER_VERIFY_PUBLIC_KEY_PATH"]  = str(KEYS_DIR / "server_verify_public.pem")
os.environ["SMTP_USERNAME"]                  = ""   # disable real mail
os.environ["SMTP_PASSWORD"]                  = ""

# ── 3. Fresh test DB ──────────────────────────────────────────────────────────

if Path(TEST_DB).exists():
    os.unlink(TEST_DB)

# ── 4. Monkey-patch DB engine BEFORE app modules import ──────────────────────

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

test_engine = create_engine(
    f"sqlite:///{TEST_DB}",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

import license_server.database as db_module
db_module.engine       = test_engine
db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
db_module.DATABASE_URL = f"sqlite:///{TEST_DB}"
db_module.DB_PATH      = TEST_DB

# Create tables
from license_server.database import Base
Base.metadata.create_all(bind=test_engine)

# Run schema migration (adds subscription_payments unique index etc.)
_mig_env = os.environ.copy()
_mig_env["SQLITE_PATH"] = TEST_DB
_mig_result = subprocess.run(
    [sys.executable, str(MIGRATION_SCRIPT)],
    env=_mig_env, capture_output=True, text=True,
)
print("Migration:", _mig_result.stdout.strip(), _mig_result.stderr.strip())

# Seed plans via raw sqlite3
_conn = sqlite3.connect(TEST_DB)
_cur  = _conn.cursor()
for plan_name, display_name, price_onetime, price_monthly, price_lifetime, max_clients, max_servers in [
    ("standard",   "Standard",   9900,  1900,  0,     50,     1),
    ("pro",        "Pro",        24900, 4900,  0,     200,    5),
    ("enterprise", "Enterprise", 0,     14900, 69900, 999999, 999999),
    ("starter",    "Starter",    0,     1200,  9900,  50,     1),
    ("business",   "Business",   0,     4900,  39900, 200,    5),
]:
    _cur.execute(
        "INSERT OR IGNORE INTO plans "
        "(plan_name, display_name, price_onetime, price_monthly, price_lifetime, "
        "max_clients, max_servers, is_active, features_json, sort_order) "
        "VALUES (?,?,?,?,?,?,?,1,'[]',1)",
        (plan_name, display_name, price_onetime, price_monthly, price_lifetime,
         max_clients, max_servers),
    )
_conn.commit()
_conn.close()

# ── 5. Load app and wire DB override ─────────────────────────────────────────

from fastapi.testclient import TestClient
from license_server.main import app
from license_server.database import get_db


def _override_get_db():
    db = db_module.SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db

# Override get_db used by subscriptions route (it has its own local copy)
from license_server.routes.subscriptions import get_db as _sub_get_db
app.dependency_overrides[_sub_get_db] = _override_get_db


# ── 6. Single shared TestClient ───────────────────────────────────────────────
# Use a global client so all tests share the same DB session context.
# We start it once and close at the end.

_client = TestClient(app, raise_server_exceptions=False)
_client.__enter__()


# ── 7. Helpers ────────────────────────────────────────────────────────────────

IPN_SECRET = "test_secret"


def sign_ipn(body: str) -> str:
    """Compute NOWPayments HMAC-SHA512 over the body string (UTF-8)."""
    return hmac.new(
        IPN_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        "sha512",
    ).hexdigest()


def make_ipn(payment_id: str, order_id: str,
             amount: float = 12.00, currency: str = "btc",
             status: str = "confirmed") -> str:
    return json.dumps({
        "payment_id":     payment_id,
        "payment_status": status,
        "order_id":       order_id,
        "invoice_id":     "INV_TEST",
        "price_amount":   amount,
        "actually_paid":  amount,
        "pay_amount":     amount,
        "pay_currency":   currency,
    })


def ipn_headers(body: str) -> dict:
    return {
        "content-type":      "application/json",
        "x-nowpayments-sig": sign_ipn(body),
    }


def db_session():
    return db_module.SessionLocal()


def decode_license_payload(license_key: str) -> dict:
    """Decode <payload_b64>.<sig_b64> — payload is JSON."""
    payload_b64 = license_key.split(".")[0]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded).decode())


# ── 8. Test state ─────────────────────────────────────────────────────────────

state: dict = {
    "token1":          "",
    "sub_id1":         0,
    "activation_code": "",
    "license_key1":    "",
    "ipn_body1":       "",
    "token2":          "",
    "sub_id2":         0,
    "lifetime_ac":     None,
}


# ── 9. Tests ──────────────────────────────────────────────────────────────────

def tc1_monthly_create():
    print("\n--- TC1: Monthly subscription create ---")

    # _create_nowpayments_invoice is `async def` → need AsyncMock
    mock_invoice = AsyncMock(return_value=("https://fake.nowpayments/inv/1", "INV_001"))

    with patch("license_server.routes.subscriptions._create_nowpayments_invoice",
               new=mock_invoice):
        r = _client.post("/api/v1/subscriptions/create", json={
            "plan":             "starter",
            "billing_period":   "monthly",
            "customer_email":   "tc1@example.com",
        })

    print(f"  status={r.status_code} body={r.json()}")
    assert r.status_code == 200, f"FAIL: {r.status_code}: {r.json()}"
    body = r.json()

    assert body["amount_usd"] == 1200, \
        f"FAIL: amount_usd={body['amount_usd']}, expected 1200"
    assert body["period_days"] == 30, \
        f"FAIL: period_days={body['period_days']}, expected 30"
    assert body["billing_period"] == "monthly", \
        f"FAIL: billing_period={body['billing_period']}"

    state["token1"]  = body["customer_token"]
    state["sub_id1"] = body["subscription_id"]

    # DB check
    db = db_session()
    from license_server.database import Subscription
    sub = db.query(Subscription).filter(Subscription.id == state["sub_id1"]).first()
    assert sub is not None, "FAIL: Subscription row missing"
    assert sub.status == "pending", f"FAIL: sub.status={sub.status}"
    db.close()

    print("  PASS")


def tc2_status_pre_payment():
    print("\n--- TC2: Status pre-payment ---")
    r = _client.get(f"/api/v1/subscriptions/{state['token1']}")
    print(f"  status={r.status_code} body={r.json()}")

    assert r.status_code == 200, f"FAIL: {r.status_code} {r.json()}"
    s = r.json()
    assert s["status"] == "pending",         f"FAIL: status={s['status']}"
    assert s["is_lifetime"] is False,        f"FAIL: is_lifetime={s['is_lifetime']}"
    assert s["activation_code"] is None,     f"FAIL: activation_code={s['activation_code']}"
    assert s["next_charge_at"] is None,      f"FAIL: next_charge_at={s['next_charge_at']}"
    print("  PASS")


def tc3_first_payment_webhook():
    print("\n--- TC3: First-payment webhook ---")
    body_str = make_ipn("PAY_001", f"sub:{state['sub_id1']}:initial")
    state["ipn_body1"] = body_str

    license_calls = []
    conf_calls    = []

    def _mock_license(*args, **kwargs):
        license_calls.append((args, kwargs))
        return True

    def _mock_conf(sub, db):
        conf_calls.append(sub.id)

    with patch("license_server.routes.webhooks._send_license_email",
               side_effect=_mock_license), \
         patch("license_server.routes.webhooks._send_subscription_confirmation",
               side_effect=_mock_conf):
        r = _client.post("/webhooks/nowpayments",
                         content=body_str,
                         headers=ipn_headers(body_str))

    print(f"  status={r.status_code} body={r.json()}")
    print(f"  _send_license_email calls={len(license_calls)}")
    print(f"  _send_subscription_confirmation calls={len(conf_calls)}")

    assert r.status_code == 200, f"FAIL: {r.status_code} {r.json()}"
    resp = r.json()
    assert resp.get("ok") is True, f"FAIL: resp.ok={resp.get('ok')}"

    db = db_session()
    from license_server.database import Subscription, SubscriptionPayment, ActivationCode

    sub = db.query(Subscription).filter(Subscription.id == state["sub_id1"]).first()
    assert sub.status == "active", f"FAIL: sub.status={sub.status}"
    assert sub.started_at is not None, "FAIL: sub.started_at is None"
    assert sub.current_period_end is not None, "FAIL: sub.current_period_end is None"

    now = datetime.now(timezone.utc)
    cpe = sub.current_period_end
    if cpe.tzinfo is None:
        cpe = cpe.replace(tzinfo=timezone.utc)
    delta = cpe - now
    assert 28 <= delta.days <= 32, \
        f"FAIL: current_period_end delta={delta.days}d, expected ~30"

    pay = db.query(SubscriptionPayment).filter(
        SubscriptionPayment.nowpayments_payment_id == "PAY_001"
    ).first()
    assert pay is not None, "FAIL: SubscriptionPayment PAY_001 missing"
    assert pay.subscription_id == state["sub_id1"], \
        f"FAIL: pay.subscription_id={pay.subscription_id}"

    ac = db.query(ActivationCode).filter(
        ActivationCode.notes == f"Subscription #{state['sub_id1']}"
    ).first()
    assert ac is not None, "FAIL: ActivationCode not found"
    assert len(ac.code) == 16, f"FAIL: ac.code len={len(ac.code)}"

    db.close()

    assert len(license_calls) == 1, \
        f"FAIL: _send_license_email call count={len(license_calls)}, expected 1"
    assert len(conf_calls) == 1, \
        f"FAIL: _send_subscription_confirmation call count={len(conf_calls)}, expected 1"

    print("  PASS")


def tc4_status_post_payment():
    print("\n--- TC4: Status post-payment ---")
    r = _client.get(f"/api/v1/subscriptions/{state['token1']}")
    s = r.json()
    print(f"  body={s}")

    assert r.status_code == 200, f"FAIL: {r.status_code}"
    assert s["status"] == "active", f"FAIL: status={s['status']}"
    assert s["activation_code"] is not None, "FAIL: activation_code is None"
    assert len(s["activation_code"]) == 16, \
        f"FAIL: code len={len(s['activation_code'])}"
    assert s["next_charge_at"] is not None, "FAIL: next_charge_at is None"

    state["activation_code"] = s["activation_code"]
    print("  PASS")


def tc5_duplicate_webhook():
    print("\n--- TC5: Duplicate webhook (dedup) ---")
    body_str = state["ipn_body1"]

    license_calls2 = []

    def _mock_license(*args, **kwargs):
        license_calls2.append((args, kwargs))
        return True

    with patch("license_server.routes.webhooks._send_license_email",
               side_effect=_mock_license), \
         patch("license_server.routes.webhooks._send_subscription_confirmation"):
        r = _client.post("/webhooks/nowpayments",
                         content=body_str,
                         headers=ipn_headers(body_str))

    print(f"  status={r.status_code} body={r.json()}")
    print(f"  extra license calls={len(license_calls2)}")

    assert r.status_code == 200, f"FAIL: {r.status_code}"
    resp = r.json()
    is_deduped = resp.get("deduped") is True or resp.get("action") == "duplicate"
    assert is_deduped, f"FAIL: expected dedup response, got {resp}"

    db = db_session()
    from license_server.database import SubscriptionPayment, ActivationCode

    cnt_pay = db.query(SubscriptionPayment).filter(
        SubscriptionPayment.nowpayments_payment_id == "PAY_001"
    ).count()
    assert cnt_pay == 1, f"FAIL: SubscriptionPayment count={cnt_pay}, expected 1"

    cnt_ac = db.query(ActivationCode).filter(
        ActivationCode.notes == f"Subscription #{state['sub_id1']}"
    ).count()
    assert cnt_ac == 1, f"FAIL: ActivationCode count={cnt_ac}, expected 1"
    db.close()

    assert len(license_calls2) == 0, \
        f"FAIL: _send_license_email called {len(license_calls2)} extra time(s)"

    print("  PASS")


def tc6_activation_redeem():
    print("\n--- TC6: Activation redeem ---")
    ac_code = state["activation_code"]
    assert ac_code, "FAIL: no activation_code from TC4"

    r = _client.post("/api/activate", json={
        "activation_code": ac_code,
        "hardware_id":     "TEST_HW_ID_TC6_12345678",
        "client_version":  "1.6.13",
    })

    print(f"  status={r.status_code}")
    resp_body = r.json()
    print(f"  body keys={list(resp_body.keys())}")
    assert r.status_code == 200, f"FAIL: {r.status_code} {resp_body}"

    db = db_session()
    from license_server.database import License, Subscription

    lic = db.query(License).filter(
        License.hardware_id == "TEST_HW_ID_TC6_12345678"
    ).first()
    assert lic is not None, "FAIL: License row missing"
    print(f"  lic.id={lic.id} sub_id={lic.subscription_id} billing={lic.billing_type}")

    assert lic.subscription_id == state["sub_id1"], \
        f"FAIL: lic.subscription_id={lic.subscription_id}, expected {state['sub_id1']}"

    sub = db.query(Subscription).filter(Subscription.id == state["sub_id1"]).first()
    assert sub.license_id == lic.id, \
        f"FAIL: sub.license_id={sub.license_id}, expected {lic.id}"
    assert sub.hardware_id == "TEST_HW_ID_TC6_12345678", \
        f"FAIL: sub.hardware_id={sub.hardware_id}"

    # expires_at ≈ current_period_end + 3d
    cpe = sub.current_period_end
    if cpe.tzinfo is None:
        cpe = cpe.replace(tzinfo=timezone.utc)
    expected_exp = cpe + timedelta(days=3)

    lic_exp = lic.expires_at
    if lic_exp and lic_exp.tzinfo is None:
        lic_exp = lic_exp.replace(tzinfo=timezone.utc)

    assert lic_exp is not None, "FAIL: lic.expires_at is None (monthly should have expiry)"
    diff_s = abs((lic_exp - expected_exp).total_seconds())
    assert diff_s < 60, \
        f"FAIL: lic.expires_at={lic_exp} not ≈ cpe+3d ({expected_exp}), diff={diff_s:.0f}s"

    assert lic.billing_type.startswith("subscription"), \
        f"FAIL: lic.billing_type={lic.billing_type}, expected starts with 'subscription'"

    db.close()
    state["license_key1"] = resp_body.get("license_key", "")
    print("  PASS")


def tc7_license_type_subscription():
    print("\n--- TC7: Signed payload license_type=subscription ---")
    key = state["license_key1"]
    assert key, "FAIL: no license_key from TC6"

    payload = decode_license_payload(key)
    print(f"  license_type={payload.get('license_type')} billing_type={payload.get('billing_type')}")

    assert payload.get("license_type") == "subscription", \
        f"FAIL: license_type={payload.get('license_type')}, expected 'subscription'"
    print("  PASS")


def tc8_lifetime_subscription():
    print("\n--- TC8: Lifetime subscription create + payment ---")

    license_calls = []
    conf_calls    = []

    def _mock_license(*args, **kwargs):
        license_calls.append((args, kwargs))
        return True

    def _mock_conf(sub, db):
        conf_calls.append(sub.id)

    mock_invoice = AsyncMock(return_value=("https://fake.nowpayments/inv/2", "INV_002"))

    with patch("license_server.routes.subscriptions._create_nowpayments_invoice",
               new=mock_invoice):
        r = _client.post("/api/v1/subscriptions/create", json={
            "plan":           "starter",
            "billing_period": "lifetime",
            "customer_email": "lifetime@example.com",
        })

    print(f"  create status={r.status_code} body={r.json()}")
    assert r.status_code == 200, f"FAIL: {r.status_code} {r.json()}"
    body = r.json()
    assert body["amount_usd"] == 9900, \
        f"FAIL: amount_usd={body['amount_usd']}, expected 9900"
    assert body["period_days"] is None, \
        f"FAIL: period_days={body['period_days']}, expected None"

    state["token2"]  = body["customer_token"]
    state["sub_id2"] = body["subscription_id"]

    # Send lifetime payment IPN
    ipn_body2 = make_ipn("PAY_002", f"sub:{state['sub_id2']}:initial", amount=99.00)

    with patch("license_server.routes.webhooks._send_license_email",
               side_effect=_mock_license), \
         patch("license_server.routes.webhooks._send_subscription_confirmation",
               side_effect=_mock_conf):
        r2 = _client.post("/webhooks/nowpayments",
                          content=ipn_body2,
                          headers=ipn_headers(ipn_body2))

    print(f"  webhook status={r2.status_code} body={r2.json()}")
    assert r2.status_code == 200, f"FAIL: {r2.status_code} {r2.json()}"

    # Status endpoint
    r3 = _client.get(f"/api/v1/subscriptions/{state['token2']}")
    s = r3.json()
    print(f"  status endpoint={s}")

    assert s["is_lifetime"] is True,    f"FAIL: is_lifetime={s['is_lifetime']}"
    assert s["next_charge_at"] is None, f"FAIL: next_charge_at={s['next_charge_at']}"
    assert s["status"] == "active",     f"FAIL: status={s['status']}"

    # DB: ActivationCode for lifetime
    db = db_session()
    from license_server.database import ActivationCode

    ac = db.query(ActivationCode).filter(
        ActivationCode.customer_email == "lifetime@example.com"
    ).first()
    assert ac is not None, "FAIL: ActivationCode for lifetime@example.com not found"
    print(f"  ac.expires_at={ac.expires_at} ac.billing_type={ac.billing_type}")

    assert ac.expires_at is None, \
        f"FAIL: ac.expires_at={ac.expires_at}, expected None (lifetime)"
    assert ac.billing_type == "lifetime", \
        f"FAIL: ac.billing_type={ac.billing_type}, expected 'lifetime'"

    db.close()
    state["lifetime_ac"] = ac.code

    # Lifetime → NO subscription_confirmation email
    assert len(conf_calls) == 0, \
        f"FAIL: _send_subscription_confirmation called {len(conf_calls)} times (expected 0 for lifetime)"
    # License email IS sent
    assert len(license_calls) == 1, \
        f"FAIL: _send_license_email call count={len(license_calls)}, expected 1"

    print("  PASS")


def tc9_lifetime_activation():
    print("\n--- TC9: Lifetime activation → license_type=lifetime ---")
    ac_code = state["lifetime_ac"]
    assert ac_code, "FAIL: no lifetime_ac from TC8"

    r = _client.post("/api/activate", json={
        "activation_code": ac_code,
        "hardware_id":     "LIFETIME_HW_ID_12345678",
        "client_version":  "1.6.13",
    })

    print(f"  status={r.status_code}")
    resp_body = r.json()
    assert r.status_code == 200, f"FAIL: {r.status_code} {resp_body}"

    db = db_session()
    from license_server.database import License
    lic2 = db.query(License).filter(
        License.hardware_id == "LIFETIME_HW_ID_12345678"
    ).first()
    assert lic2 is not None, "FAIL: License row missing for LIFETIME_HW_ID_12345678"
    print(f"  lic2.billing_type={lic2.billing_type} expires_at={lic2.expires_at}")

    assert lic2.billing_type == "lifetime", \
        f"FAIL: lic2.billing_type={lic2.billing_type}, expected 'lifetime'"
    db.close()

    # Decode signed payload
    key = resp_body.get("license_key", "")
    assert key, "FAIL: no license_key in response"
    payload = decode_license_payload(key)
    print(f"  payload license_type={payload.get('license_type')} billing_type={payload.get('billing_type')}")

    assert payload.get("license_type") == "lifetime", \
        f"FAIL: license_type={payload.get('license_type')}, expected 'lifetime' (C2 fix)"
    print("  PASS")


def tc10_renewal_payment():
    print("\n--- TC10: Renewal payment ---")

    db = db_session()
    from license_server.database import Subscription, SubscriptionPayment, ActivationCode, License

    sub1 = db.query(Subscription).filter(Subscription.id == state["sub_id1"]).first()
    assert sub1 is not None, "FAIL: sub1 missing"
    old_period_end = sub1.current_period_end
    if old_period_end and old_period_end.tzinfo is None:
        old_period_end = old_period_end.replace(tzinfo=timezone.utc)
    print(f"  old_period_end={old_period_end}")
    db.close()

    ipn_body3 = make_ipn("PAY_003", f"sub:{state['sub_id1']}:renewal-1", amount=12.00)

    with patch("license_server.routes.webhooks._send_license_email"), \
         patch("license_server.routes.webhooks._send_subscription_confirmation"):
        r = _client.post("/webhooks/nowpayments",
                         content=ipn_body3,
                         headers=ipn_headers(ipn_body3))

    print(f"  webhook status={r.status_code} body={r.json()}")
    assert r.status_code == 200, f"FAIL: {r.status_code} {r.json()}"

    db = db_session()
    sub1 = db.query(Subscription).filter(Subscription.id == state["sub_id1"]).first()
    new_period_end = sub1.current_period_end
    if new_period_end and new_period_end.tzinfo is None:
        new_period_end = new_period_end.replace(tzinfo=timezone.utc)

    print(f"  new_period_end={new_period_end}")
    assert sub1.status == "active", f"FAIL: status={sub1.status}"
    assert sub1.last_payment_id == "PAY_003", \
        f"FAIL: last_payment_id={sub1.last_payment_id}"

    if old_period_end and new_period_end:
        delta_ext = (new_period_end - old_period_end).days
        assert 28 <= delta_ext <= 32, \
            f"FAIL: period extended by {delta_ext}d, expected ≈30"

    # License.expires_at updated to new_period_end + 3d
    lic = db.query(License).filter(License.id == sub1.license_id).first()
    assert lic is not None, "FAIL: No license for sub1"
    lic_exp = lic.expires_at
    if lic_exp and lic_exp.tzinfo is None:
        lic_exp = lic_exp.replace(tzinfo=timezone.utc)
    if lic_exp and new_period_end:
        expected_exp = new_period_end + timedelta(days=3)
        diff_s = abs((lic_exp - expected_exp).total_seconds())
        assert diff_s < 60, \
            f"FAIL: lic.expires_at={lic_exp} not ≈ new_period_end+3d ({expected_exp})"
        print(f"  lic.expires_at={lic_exp} ≈ new_period_end+3d ({expected_exp})")
    else:
        assert lic_exp is not None, "FAIL: lic.expires_at is None after renewal"

    # NO new ActivationCode
    cnt_ac = db.query(ActivationCode).filter(
        ActivationCode.notes == f"Subscription #{state['sub_id1']}"
    ).count()
    assert cnt_ac == 1, f"FAIL: ActivationCode count={cnt_ac} after renewal, expected 1"

    # 2 payment rows
    cnt_pay = db.query(SubscriptionPayment).filter(
        SubscriptionPayment.subscription_id == state["sub_id1"]
    ).count()
    assert cnt_pay == 2, f"FAIL: SubscriptionPayment count={cnt_pay}, expected 2"

    db.close()
    print("  PASS")


# ── 10. Runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import traceback

    tests = [
        ("TC1",  tc1_monthly_create),
        ("TC2",  tc2_status_pre_payment),
        ("TC3",  tc3_first_payment_webhook),
        ("TC4",  tc4_status_post_payment),
        ("TC5",  tc5_duplicate_webhook),
        ("TC6",  tc6_activation_redeem),
        ("TC7",  tc7_license_type_subscription),
        ("TC8",  tc8_lifetime_subscription),
        ("TC9",  tc9_lifetime_activation),
        ("TC10", tc10_renewal_payment),
    ]

    results: dict[str, str] = {}
    for name, fn in tests:
        try:
            fn()
            results[name] = "PASS"
        except Exception as exc:
            results[name] = f"FAIL — {exc}"
            traceback.print_exc()

    # Clean up
    try:
        _client.__exit__(None, None, None)
    except Exception:
        pass

    print("\n" + "=" * 65)
    print("  PHASE 2 E2E VERIFICATION REPORT")
    print("=" * 65)
    for name, outcome in results.items():
        marker = "PASS" if outcome == "PASS" else "FAIL"
        print(f"  [{marker}] {name}: {outcome}")
    print("=" * 65)
    passes = sum(1 for v in results.values() if v == "PASS")
    fails  = sum(1 for v in results.values() if v != "PASS")
    print(f"  Summary: {passes} passed, {fails} failed out of {len(results)}")
    print("=" * 65)
