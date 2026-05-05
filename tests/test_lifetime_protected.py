"""
Tests for the 1.5.64 lifetime_protected license type:

  • license_generator emits owner_name, owner_email, license_type,
    migration_secret in the signed payload
  • migration_code generates / verifies / rejects tampered codes
  • is_decommissioned() flips True after the 3-day deadline
  • online_validator is_license_blocked returns False for lifetime / lifetime_protected
  • heartbeat interval is selected per license_type
"""

import base64
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Modules under test
from src.modules.license import migration_code as mc
from src.modules.license.online_validator import (
    _local_license_type, is_license_blocked,
)
from src.modules.license.instance_manager import (
    _read_license_type_from_env, _HEARTBEAT_INTERVAL_BY_TYPE,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fake_license_key(payload: dict) -> str:
    """Build a base64.signature pair with arbitrary signature bytes —
    online_validator + migration_code only parse the payload, not verify it."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    head = base64.urlsafe_b64encode(body).rstrip(b"=").decode()
    sig  = base64.urlsafe_b64encode(b"\x00" * 32).rstrip(b"=").decode()
    return head + "." + sig


def _make_protected_payload():
    return {
        "plan": "enterprise",
        "tier": "enterprise",
        "billing_type": "lifetime",
        "license_type": "lifetime_protected",
        "max_clients": 999999,
        "max_servers": 999999,
        "features": ["multi_server", "white_label_basic"],
        "hardware_id": "abcd1234",
        "issued_at": "2026-05-05T00:00:00+00:00",
        "expires_at": None,
        "owner_name": "Herbert Rivera",
        "owner_email": "h@example.com",
        "migration_secret": "MIGSECRET_32CHARS_TESTONLY________",
    }


# ── license_type detection from raw LICENSE_KEY ──────────────────────────────

def test_local_license_type_subscription_when_no_field(monkeypatch):
    payload = _make_protected_payload()
    payload.pop("license_type")
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key(payload))
    assert _local_license_type() == "subscription"


def test_local_license_type_lifetime_protected(monkeypatch):
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key(_make_protected_payload()))
    assert _local_license_type() == "lifetime_protected"


def test_local_license_type_lifetime(monkeypatch):
    p = _make_protected_payload()
    p["license_type"] = "lifetime"
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key(p))
    assert _local_license_type() == "lifetime"


def test_local_license_type_no_key(monkeypatch):
    monkeypatch.delenv("LICENSE_KEY", raising=False)
    assert _local_license_type() == "subscription"


def test_local_license_type_garbage_falls_back(monkeypatch):
    monkeypatch.setenv("LICENSE_KEY", "not-a-key")
    assert _local_license_type() == "subscription"


# ── Heartbeat interval selection ─────────────────────────────────────────────

def test_heartbeat_interval_subscription(monkeypatch):
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key({
        **_make_protected_payload(), "license_type": "subscription"
    }))
    assert _read_license_type_from_env() == "subscription"
    assert _HEARTBEAT_INTERVAL_BY_TYPE["subscription"] == 300


def test_heartbeat_interval_lifetime_protected_is_24h(monkeypatch):
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key(_make_protected_payload()))
    assert _read_license_type_from_env() == "lifetime_protected"
    assert _HEARTBEAT_INTERVAL_BY_TYPE["lifetime_protected"] == 86_400


def test_heartbeat_interval_lifetime_disabled(monkeypatch):
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key({
        **_make_protected_payload(), "license_type": "lifetime"
    }))
    assert _read_license_type_from_env() == "lifetime"
    assert _HEARTBEAT_INTERVAL_BY_TYPE["lifetime"] is None


# ── online_validator blocking gate ───────────────────────────────────────────

def test_online_validator_never_blocks_lifetime_protected(monkeypatch):
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key(_make_protected_payload()))
    # Force "server unreachable" simulation: even without server URLs the
    # blocked check returns (False, "") for lifetime_protected.
    blocked, reason = is_license_blocked()
    assert blocked is False, reason


def test_online_validator_never_blocks_lifetime(monkeypatch):
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key({
        **_make_protected_payload(), "license_type": "lifetime"
    }))
    blocked, _ = is_license_blocked()
    assert blocked is False


# ── migration_code generation + verification ────────────────────────────────

def test_migration_code_round_trip(monkeypatch):
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key(_make_protected_payload()))
    code_obj = mc.generate_migration_code()
    assert code_obj is not None
    assert code_obj.code.startswith("MIGRATE-")
    ok, msg = mc.verify_migration_code(code_obj.code)
    assert ok, msg


def test_migration_code_tamper_detection(monkeypatch):
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key(_make_protected_payload()))
    code_obj = mc.generate_migration_code()
    # flip one char in the HMAC portion
    parts = code_obj.code.split("-")
    bad_char = "A" if parts[1][0] != "A" else "B"
    parts[1] = bad_char + parts[1][1:]
    bad = "-".join(parts)
    ok, msg = mc.verify_migration_code(bad)
    assert not ok
    assert "signature" in msg.lower() or "decode" in msg.lower()


def test_migration_code_refused_for_subscription_type(monkeypatch):
    p = _make_protected_payload()
    p["license_type"] = "subscription"
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key(p))
    assert mc.generate_migration_code() is None


def test_migration_code_refused_when_no_secret_in_payload(monkeypatch):
    p = _make_protected_payload()
    p.pop("migration_secret")
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key(p))
    assert mc.generate_migration_code() is None


# ── Self-decommission countdown (3-day burning bridge) ───────────────────────

def test_decommission_path(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "_MIGRATION_INITIATED_PATH", str(tmp_path / "mig.json"))
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key(_make_protected_payload()))

    # Before generation: not decommissioned
    assert mc.is_decommissioned() is False
    assert mc.get_migration_initiated() is None

    # Generate code → record persisted
    code_obj = mc.generate_migration_code()
    assert code_obj is not None
    rec = mc.get_migration_initiated()
    assert rec is not None
    assert rec["license_id"] == code_obj.license_id
    assert rec["deadline_days"] == mc.OLD_SERVER_DECOMMISSION_DAYS

    # Still inside the 3-day window
    assert mc.is_decommissioned() is False
    ttd = mc.time_to_decommission()
    assert ttd is not None and ttd.total_seconds() > 0

    # Fast-forward by overwriting file with a stale initiated_at
    rec["initiated_at"] = (datetime.now(timezone.utc)
                          - timedelta(days=mc.OLD_SERVER_DECOMMISSION_DAYS + 1)).isoformat()
    Path(mc._MIGRATION_INITIATED_PATH).write_text(json.dumps(rec))
    assert mc.is_decommissioned() is True


def test_decommission_idempotent_on_second_generate(monkeypatch, tmp_path):
    """Clicking 'Generate code' twice must NOT extend the 3-day deadline."""
    monkeypatch.setattr(mc, "_MIGRATION_INITIATED_PATH", str(tmp_path / "mig.json"))
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key(_make_protected_payload()))

    mc.generate_migration_code()
    rec1 = mc.get_migration_initiated()
    time.sleep(0.05)
    mc.generate_migration_code()
    rec2 = mc.get_migration_initiated()
    # Same initiated_at — second call did not reset
    assert rec1["initiated_at"] == rec2["initiated_at"]


def test_cancel_migration_clears_record(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "_MIGRATION_INITIATED_PATH", str(tmp_path / "mig.json"))
    monkeypatch.setenv("LICENSE_KEY", _fake_license_key(_make_protected_payload()))

    mc.generate_migration_code()
    assert mc.get_migration_initiated() is not None
    assert mc.cancel_migration() is True
    assert mc.get_migration_initiated() is None


# ── license_generator payload roundtrip ──────────────────────────────────────

def test_license_generator_emits_protected_fields(tmp_path):
    """Round-trip through generate_license_key — verify new fields are signed."""
    from license_server.services.license_generator import generate_license_key

    # Generate a throwaway RSA key for the test
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    keyfile = tmp_path / "priv.pem"
    keyfile.write_bytes(pem)

    key, payload = generate_license_key(
        private_key_path=str(keyfile),
        plan="enterprise",
        max_clients=999999, max_servers=999999,
        features=["multi_server"],
        hardware_id="abc",
        duration_days=None,
        billing_type="lifetime",
        license_type="lifetime_protected",
        owner_name="Herbert Rivera",
        owner_email="h@example.com",
    )
    assert payload["license_type"] == "lifetime_protected"
    assert payload["owner_name"] == "Herbert Rivera"
    assert payload["owner_email"] == "h@example.com"
    assert "migration_secret" in payload
    assert len(payload["migration_secret"]) >= 32
    # Roundtrip via key string
    head = key.split(".", 1)[0] + "==="
    decoded = json.loads(base64.urlsafe_b64decode(head).decode())
    assert decoded["license_type"] == "lifetime_protected"
    assert decoded["migration_secret"] == payload["migration_secret"]


def test_license_generator_omits_migration_secret_for_subscription(tmp_path):
    from license_server.services.license_generator import generate_license_key
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    keyfile = tmp_path / "priv.pem"
    keyfile.write_bytes(pem)

    key, payload = generate_license_key(
        private_key_path=str(keyfile),
        plan="standard",
        max_clients=100, max_servers=2,
        features=["basic_management"],
        hardware_id="abc",
        duration_days=30,
        billing_type="monthly",
        license_type="subscription",
    )
    assert "migration_secret" not in payload  # subscription doesn't need one


def test_license_generator_rejects_unknown_type(tmp_path):
    from license_server.services.license_generator import generate_license_key
    keyfile = tmp_path / "priv.pem"
    keyfile.write_bytes(b"unused")
    with pytest.raises(ValueError, match="license_type"):
        generate_license_key(
            private_key_path=str(keyfile),
            plan="enterprise", max_clients=1, max_servers=1, features=[],
            hardware_id="abc", duration_days=None,
            license_type="never-existed",
        )
