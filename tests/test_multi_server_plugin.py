"""Tests for the multi-server plugin and its license gate dependency.

Verifies that:
- LICENSE_TIERS for paid plans contain `multi_server` (FREE does not)
- The plugin discovers + skips correctly based on feature presence
- The require_license_feature dependency raises 403 in FREE mode
- The dependency passes silently when the feature is granted
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.api.middleware.license_gate import require_license_feature
from src.modules.license.manager import (
    LICENSE_TIERS,
    LicenseManager,
    LicenseType,
    reset_license_manager,
)
from src.modules.plugin_loader import PluginLoader


PLUGIN_NAME = "multi-server"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("LICENSE_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_LICENSE_MODE", raising=False)
    reset_license_manager()
    yield
    reset_license_manager()


# ── License tier configuration ────────────────────────────────────────────────


class TestMultiServerTiers:
    def test_free_lacks_multi_server(self):
        free = LICENSE_TIERS[LicenseType.FREE]
        assert "multi_server" not in free["features"]
        # FREE is also limited to 1 server, which prevents the situation
        # entirely at the limit-check layer
        assert free["max_servers"] == 1

    @pytest.mark.parametrize(
        "tier,has_feature",
        [
            (LicenseType.STANDARD, False),    # STANDARD = single-server tier
            (LicenseType.STARTER, False),     # alias for STANDARD
            (LicenseType.PRO, True),
            (LicenseType.BUSINESS, True),
            (LicenseType.ENTERPRISE, True),
        ],
    )
    def test_tier_multi_server_alignment(self, tier, has_feature):
        features = LICENSE_TIERS[tier]["features"]
        assert ("multi_server" in features) is has_feature, (
            f"{tier.value} multi_server should be {has_feature}"
        )

    def test_business_can_run_multiple_servers(self):
        biz = LICENSE_TIERS[LicenseType.BUSINESS]
        assert biz["max_servers"] >= 2, "BUSINESS must allow more than one server"

    def test_enterprise_unlimited_servers(self):
        ent = LICENSE_TIERS[LicenseType.ENTERPRISE]
        assert ent["max_servers"] >= 999, "ENTERPRISE must allow effectively unlimited servers"


# ── Plugin discovery ──────────────────────────────────────────────────────────


@pytest.fixture
def repo_plugins_dir():
    return Path(__file__).resolve().parent.parent / "plugins"


class TestPluginDiscovery:
    def test_skipped_on_free_install(self, repo_plugins_dir):
        loader = PluginLoader(repo_plugins_dir)
        free_mgr = LicenseManager(license_key=None)
        free_mgr.validate_license()
        records = loader.discover_and_load(license_manager=free_mgr)
        rec = next((r for r in records if r.name == PLUGIN_NAME), None)
        assert rec is not None
        assert rec.skipped is True
        assert "multi_server" in rec.skip_reason

    def test_loaded_when_feature_granted(self, repo_plugins_dir):
        class FakeLM:
            def has_feature(self, name):
                return name == "multi_server"

        loader = PluginLoader(repo_plugins_dir)
        records = loader.discover_and_load(license_manager=FakeLM())
        rec = next((r for r in records if r.name == PLUGIN_NAME), None)
        assert rec is not None
        assert rec.loaded is True, f"plugin failed: {rec.error}"


# ── License gate dependency ───────────────────────────────────────────────────


class TestLicenseGateDependency:
    @pytest.mark.asyncio
    async def test_blocks_when_feature_missing(self):
        gate = require_license_feature("multi_server")
        with pytest.raises(HTTPException) as exc:
            await gate()
        assert exc.value.status_code == 403
        assert "multi_server" in exc.value.detail

    @pytest.mark.asyncio
    async def test_passes_when_feature_present(self):
        # Patch the global LicenseManager to a fake that grants the feature.
        class FakeMgr:
            def get_license_info(self):
                class _Info:
                    type = LicenseType.BUSINESS
                    def has_feature(self, name):
                        return name == "multi_server"
                return _Info()

        with patch(
            "src.modules.license.manager.get_license_manager",
            return_value=FakeMgr(),
        ):
            gate = require_license_feature("multi_server")
            # Should NOT raise
            await gate()

    @pytest.mark.asyncio
    async def test_fails_closed_on_manager_exception(self):
        # If LicenseManager itself blows up, the gate must default to 503,
        # not 200 (don't let FREE bypass via crash).
        with patch(
            "src.modules.license.manager.get_license_manager",
            side_effect=RuntimeError("boom"),
        ):
            gate = require_license_feature("multi_server")
            with pytest.raises(HTTPException) as exc:
                await gate()
            assert exc.value.status_code == 503
