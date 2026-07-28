"""Lifetime outage and emergency-lease security contract."""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from src.modules.license import online_validator as ov


def _key(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode() + ".test"


def _sign(private_key, payload: dict) -> dict:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    payload_b64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    signature = private_key.sign(
        payload_b64.encode("ascii"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return {
        "payload": payload_b64,
        "signature": base64.urlsafe_b64encode(signature).rstrip(b"=").decode(),
    }


def _local_lifetime(monkeypatch):
    monkeypatch.setenv(
        "LICENSE_KEY",
        _key({"license_type": "lifetime_protected", "lid": "lic-uid-123", "hardware_id": "hw-12345678"}),
    )
    monkeypatch.setattr(ov, "_SERVER_URL", "https://license.example")
    monkeypatch.setattr(ov, "_SERVER_URL_BACKUP", "")
    monkeypatch.setattr(ov, "_get_hardware_id", lambda: "hw-12345678")
    monkeypatch.setattr(ov, "_instance_id", "instance-12345678")
    monkeypatch.setattr(ov, "_cache_warmed", True)
    monkeypatch.setattr(ov, "_last_apply_wall_time", 0.0)


def test_lifetime_works_inside_signed_30_day_window(monkeypatch):
    _local_lifetime(monkeypatch)
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        ov,
        "_state",
        ov.LicenseState(
            status="ok", billing_type="lifetime", license_type="lifetime_protected",
            server_time=now, valid_until=now + timedelta(days=30), lease_kind="online",
            last_check=now, server_reachable=False,
        ),
    )
    assert ov.is_license_blocked() == (False, "")


def test_lifetime_blocks_after_signed_window(monkeypatch):
    _local_lifetime(monkeypatch)
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        ov,
        "_state",
        ov.LicenseState(
            status="ok", billing_type="lifetime", license_type="lifetime_protected",
            server_time=now - timedelta(days=31), valid_until=now - timedelta(days=1),
            lease_kind="online", last_check=now - timedelta(days=31), server_reachable=False,
        ),
    )
    blocked, reason = ov.is_license_blocked()
    assert blocked is True
    assert "offline allowance expired" in reason


def test_cache_deletion_does_not_create_new_lifetime_window(monkeypatch):
    _local_lifetime(monkeypatch)
    monkeypatch.setattr(ov, "_state", ov.LicenseState(server_reachable=False))
    blocked, reason = ov.is_license_blocked()
    assert blocked is True
    assert "No valid signed Lifetime" in reason


def test_hard_revocation_wins_over_future_lease(monkeypatch):
    _local_lifetime(monkeypatch)
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        ov,
        "_state",
        ov.LicenseState(
            status="revoked", server_time=now,
            valid_until=now + timedelta(days=30), lease_kind="online", last_check=now,
        ),
    )
    assert ov.is_license_blocked()[0] is True


def test_emergency_lease_is_signed_bound_and_atomic(monkeypatch, tmp_path):
    _local_lifetime(monkeypatch)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(ov, "_load_server_pub_keys", lambda: [private_key.public_key()])
    monkeypatch.setattr(ov, "_CACHE_PATH", tmp_path / "license_cache.json")
    now = datetime.now(timezone.utc)
    payload = {
        "status": "ok", "message": "emergency", "plan": "business", "tier": "business",
        "billing_type": "lifetime", "license_type": "lifetime_protected",
        "max_clients": 2000, "max_servers": 10, "features": ["multi_server"],
        "expires_at": None, "server_time": now.isoformat(),
        "valid_until": (now + timedelta(days=7)).isoformat(), "license_uid": "lic-uid-123",
        "lease_version": 1, "lease_kind": "emergency", "lease_id": "lease-123",
        "hardware_id": "hw-12345678", "instance_id": "instance-12345678",
    }
    success, message = ov.install_offline_lease(_sign(private_key, payload))
    assert success is True, message
    assert (ov._CACHE_PATH.stat().st_mode & 0o777) == 0o600

    payload["hardware_id"] = "another-machine"
    success, message = ov.install_offline_lease(_sign(private_key, payload))
    assert success is False
    assert "hardware binding mismatch" in message


def test_lifetime_lease_cannot_exceed_30_days(monkeypatch):
    _local_lifetime(monkeypatch)
    now = datetime.now(timezone.utc)
    valid, reason = ov._validate_lease_binding({
        "lease_version": 1, "lease_kind": "online", "license_uid": "lic-uid-123",
        "hardware_id": "hw-12345678", "instance_id": "instance-12345678",
        "billing_type": "lifetime", "server_time": now.isoformat(),
        "valid_until": (now + timedelta(days=31)).isoformat(),
    })
    assert valid is False
    assert "exceeds maximum" in reason


@pytest.mark.asyncio
async def test_fallback_negative_cannot_overwrite_primary_lease(monkeypatch):
    monkeypatch.setenv("LICENSE_KEY", "current-key")
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"payload": "signed", "signature": "signature"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return Response()

    applied = []
    monkeypatch.setattr(ov.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(ov, "_verify_response", lambda *_args: {"status": "not_found"})
    monkeypatch.setattr(ov, "_validate_lease_binding", lambda *_args, **_kwargs: (True, ""))
    monkeypatch.setattr(ov, "_apply_payload", lambda payload: applied.append(payload))
    monkeypatch.setattr(ov, "_save_cache", lambda *_args: applied.append("cache"))

    result = await ov._try_server(
        "https://backup.example",
        {"instance_id": "instance-12345678", "license_key": "current-key"},
        accept_negative_status=False,
    )

    assert result is None
    assert applied == []
