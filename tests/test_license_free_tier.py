"""Tests for FREE tier (open-core mode).

Verifies that LicenseManager correctly enters FREE mode when no LICENSE_KEY
is present, and that FREE mode never makes network calls or expires.
"""

import os
import pytest

from src.modules.license.manager import (
    LicenseInfo,
    LicenseManager,
    LicenseType,
    LICENSE_TIERS,
    _normalize_license_type,
)


@pytest.fixture(autouse=True)
def _no_license_env(monkeypatch):
    """Ensure tests run with no license key set in env."""
    monkeypatch.delenv("LICENSE_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_LICENSE_MODE", raising=False)
    monkeypatch.delenv("TRIAL_STARTED_AT", raising=False)
    monkeypatch.delenv("TRIAL_HARDWARE_ID", raising=False)


class TestLicenseTypeEnum:
    def test_free_value(self):
        assert LicenseType.FREE.value == "free"

    def test_free_normalized(self):
        assert _normalize_license_type("free") == LicenseType.FREE

    def test_unknown_defaults_to_free(self):
        # Open-core: unknown types should default to FREE (not TRIAL).
        assert _normalize_license_type("nonexistent_tier") == LicenseType.FREE


class TestFreeTierConfiguration:
    def test_free_in_tiers_dict(self):
        assert LicenseType.FREE in LICENSE_TIERS

    def test_free_limits(self):
        free = LICENSE_TIERS[LicenseType.FREE]
        assert free["max_clients"] == 80
        assert free["max_servers"] == 1

    def test_free_no_expiry(self):
        # FREE must not have a duration_days key — it never expires.
        free = LICENSE_TIERS[LicenseType.FREE]
        assert "duration_days" not in free

    def test_free_features_include_wireguard_and_amneziawg(self):
        free = LICENSE_TIERS[LicenseType.FREE]
        assert "wireguard" in free["features"]
        assert "amneziawg" in free["features"]

    def test_free_features_exclude_paid(self):
        free = LICENSE_TIERS[LicenseType.FREE]
        # These features must be paid-only.
        assert "hysteria2" not in free["features"]
        assert "tuic" not in free["features"]
        assert "multi_server" not in free["features"]
        assert "white_label" not in free["features"]
        assert "corporate_vpn" not in free["features"]


class TestLicenseManagerFreeMode:
    def test_no_key_returns_free(self):
        mgr = LicenseManager(license_key=None)
        info = mgr.validate_license()
        assert info.type == LicenseType.FREE

    def test_empty_string_key_returns_free(self):
        mgr = LicenseManager(license_key="")
        info = mgr.validate_license()
        assert info.type == LicenseType.FREE

    def test_invalid_key_falls_back_to_free(self):
        mgr = LicenseManager(license_key="garbage.notvalid")
        info = mgr.validate_license()
        assert info.type == LicenseType.FREE

    def test_free_license_never_expires(self):
        mgr = LicenseManager(license_key=None)
        info = mgr.validate_license()
        assert info.expires_at is None
        assert not info.is_expired()
        assert not info.in_grace_period()

    def test_free_license_is_valid(self):
        mgr = LicenseManager(license_key=None)
        info = mgr.validate_license()
        assert info.is_valid is True

    def test_free_billing_type(self):
        mgr = LicenseManager(license_key=None)
        info = mgr.validate_license()
        assert info.billing_type == "free"

    def test_free_has_hardware_id(self):
        # FREE should still report hardware_id (for analytics opt-in / support).
        mgr = LicenseManager(license_key=None)
        info = mgr.validate_license()
        assert info.hardware_id  # non-empty

    def test_free_no_grace_period(self):
        mgr = LicenseManager(license_key=None)
        info = mgr.validate_license()
        assert info.grace_period is False


class TestLicenseManagerHelpers:
    def test_is_free_when_no_key(self):
        mgr = LicenseManager(license_key=None)
        assert mgr.is_free() is True
        assert mgr.is_paid() is False

    def test_is_properly_activated_false_for_free(self):
        # FREE is not "properly activated" — it's open-core mode.
        mgr = LicenseManager(license_key=None)
        assert mgr.is_properly_activated() is False

    def test_has_feature_in_free_mode(self):
        mgr = LicenseManager(license_key=None)
        assert mgr.has_feature("wireguard") is True
        assert mgr.has_feature("amneziawg") is True
        assert mgr.has_feature("hysteria2") is False
        assert mgr.has_feature("multi_server") is False
        assert mgr.has_feature("corporate_vpn") is False

    def test_require_feature_raises_for_paid_in_free(self):
        mgr = LicenseManager(license_key=None)
        with pytest.raises(PermissionError):
            mgr.require_feature("multi_server")

    def test_require_feature_passes_for_free(self):
        mgr = LicenseManager(license_key=None)
        # Should NOT raise — wireguard is in FREE features.
        mgr.require_feature("wireguard")


class TestLicenseManagerLimits:
    def test_check_limits_within_in_free(self):
        mgr = LicenseManager(license_key=None)
        result = mgr.check_limits(current_clients=10, current_servers=0)
        assert result["within_limits"] is True
        assert result["clients"]["available"] == 70   # 80 - 10
        assert result["servers"]["available"] == 1    # 1 - 0

    def test_check_limits_at_client_limit(self):
        mgr = LicenseManager(license_key=None)
        result = mgr.check_limits(current_clients=80, current_servers=0)
        assert result["within_limits"] is False
        assert result["clients"]["at_limit"] is True
        assert result["clients"]["available"] == 0

    def test_check_limits_at_server_limit(self):
        mgr = LicenseManager(license_key=None)
        result = mgr.check_limits(current_clients=10, current_servers=1)
        assert result["within_limits"] is False
        assert result["servers"]["at_limit"] is True
        assert result["servers"]["available"] == 0

    def test_can_add_client_within_limit(self):
        mgr = LicenseManager(license_key=None)
        info = mgr.validate_license()
        assert info.can_add_client(50) is True
        assert info.can_add_client(80) is False

    def test_can_add_server_within_limit(self):
        mgr = LicenseManager(license_key=None)
        info = mgr.validate_license()
        assert info.can_add_server(0) is True
        assert info.can_add_server(1) is False


class TestFreeModeDoesNotMakeNetworkCalls:
    """Regression test: FREE mode must NEVER attempt to contact license server."""

    def test_no_httpx_call_during_free_validation(self, monkeypatch):
        # Sabotage httpx so any network call would raise.
        called = []

        class FakeClient:
            def __init__(self, *a, **kw):
                called.append(("FakeClient", a, kw))
                raise RuntimeError("FREE mode must not call httpx")

        import httpx
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: called.append(("post", a, kw)))
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: called.append(("get", a, kw)))

        mgr = LicenseManager(license_key=None)
        info = mgr.validate_license()
        assert info.type == LicenseType.FREE
        assert called == [], f"FREE mode made unexpected network calls: {called}"


class TestStatus:
    def test_get_status_in_free_mode(self):
        mgr = LicenseManager(license_key=None)
        status = mgr.get_status()
        assert status["license_type"] == "free"
        assert status["plan"] == "free"
        assert status["billing_type"] == "free"
        assert status["is_valid"] is True
        assert status["max_clients"] == 80
        assert status["max_servers"] == 1
        assert status["expires_at"] is None
        assert status["days_remaining"] is None
