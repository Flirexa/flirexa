"""Integration tests: FREE tier interaction with failsafe and operational_mode.

Verifies that FREE-mode installs never trigger license-related fail-safe
or readonly modes — they're open-core, no license to be invalid.
"""

import os
import pytest

from src.modules.failsafe import FailSafeManager
from src.modules.license.manager import (
    LicenseManager,
    LicenseType,
    get_license_manager,
    reset_license_manager,
)
from src.modules.operational_mode import derive_license_mode


@pytest.fixture(autouse=True)
def _free_mode_env(monkeypatch):
    """Run every test with no LICENSE_KEY (FREE mode)."""
    monkeypatch.delenv("LICENSE_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_LICENSE_MODE", raising=False)
    monkeypatch.delenv("TRIAL_STARTED_AT", raising=False)
    monkeypatch.delenv("TRIAL_HARDWARE_ID", raising=False)
    reset_license_manager()
    yield
    reset_license_manager()


# ── derive_license_mode() in FREE ────────────────────────────────────────────

class TestDeriveLicenseModeFree:
    def test_no_license_key_returns_normal(self):
        # The operational mode resolver must treat "no key" as normal usage.
        assert derive_license_mode() == "normal"

    def test_invalid_license_key_falls_back_to_normal(self, monkeypatch):
        # Even when LICENSE_KEY is set to garbage, LicenseManager falls back to
        # FREE — operational mode must follow.
        monkeypatch.setenv("LICENSE_KEY", "garbage.notvalid")
        reset_license_manager()
        assert derive_license_mode() == "normal"

    def test_free_mode_skips_online_validator(self, monkeypatch):
        # Sentinel: derive_license_mode must not call online_validator helpers
        # when the manager is in FREE mode.
        called = []

        def boom(*a, **kw):
            called.append("get_online_status")
            raise RuntimeError("FREE mode must not call online_validator")

        monkeypatch.setattr(
            "src.modules.operational_mode.get_online_status",
            boom,
        )
        # No LICENSE_KEY in env → goes through "normal" fast path before
        # touching get_online_status at all.
        assert derive_license_mode() == "normal"
        assert called == []


# ── FailSafe with FREE ───────────────────────────────────────────────────────

class TestFailsafeFreeMode:
    def test_failsafe_does_not_trigger_on_free_license(self):
        # In FREE mode, license check inside FailSafeManager.refresh()
        # must NOT add a license_invalid reason — there is no license.
        fsm = FailSafeManager()  # fresh instance, not the singleton
        state = fsm.refresh(db=None)
        assert state.active is False
        assert not any("license_invalid" in r for r in state.reasons)

    def test_payment_allowed_in_free_mode(self):
        fsm = FailSafeManager()
        fsm.refresh(db=None)
        # Should not raise
        fsm.check_payment_allowed()
        fsm.check_client_creation()

    def test_failsafe_state_reasons_clean_on_free(self):
        fsm = FailSafeManager()
        state = fsm.refresh(db=None)
        # FREE installs without DB and without WG errors → no reasons.
        assert state.reasons == []


# ── LicenseManager helpers ────────────────────────────────────────────────────

class TestLicenseManagerInOperationalContext:
    def test_global_manager_reports_free(self):
        mgr = get_license_manager()
        assert mgr.is_free() is True
        assert mgr.is_paid() is False
        assert mgr.is_properly_activated() is False

    def test_global_manager_features_subset(self):
        mgr = get_license_manager()
        # FREE feature set must be a subset of full LICENSE_TIERS[FREE]
        assert mgr.has_feature("wireguard") is True
        assert mgr.has_feature("amneziawg") is True
        assert mgr.has_feature("multi_server") is False
        assert mgr.has_feature("white_label") is False
