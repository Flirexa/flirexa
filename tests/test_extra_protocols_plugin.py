"""Tests for the extra-protocols plugin and its license gate.

Verifies that:
- The plugin discovers and loads when license has `proxy_protocols`
- The plugin is silently skipped on FREE installs
- LICENSE_TIERS for paid plans actually contain `proxy_protocols`
- LICENSE_TIERS[FREE] does NOT contain `proxy_protocols`
"""

from pathlib import Path

import pytest

from src.modules.license.manager import (
    LICENSE_TIERS,
    LicenseManager,
    LicenseType,
)
from src.modules.plugin_loader import PluginLoader


PLUGIN_NAME = "extra-protocols"


@pytest.fixture(autouse=True)
def _no_license_env(monkeypatch):
    monkeypatch.delenv("LICENSE_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_LICENSE_MODE", raising=False)


# ── License tier configuration ────────────────────────────────────────────────


class TestLicenseTiersIncludeProxyProtocols:
    def test_free_does_not_include_proxy_protocols(self):
        free = LICENSE_TIERS[LicenseType.FREE]
        assert "proxy_protocols" not in free["features"]
        assert "hysteria2" not in free["features"]
        assert "tuic" not in free["features"]

    @pytest.mark.parametrize(
        "tier",
        [LicenseType.STANDARD, LicenseType.PRO,
         LicenseType.STARTER, LicenseType.BUSINESS, LicenseType.ENTERPRISE],
    )
    def test_paid_tiers_include_proxy_protocols(self, tier):
        features = LICENSE_TIERS[tier]["features"]
        assert "proxy_protocols" in features, (
            f"{tier.value} must include proxy_protocols feature"
        )


# ── Plugin discovery ──────────────────────────────────────────────────────────


@pytest.fixture
def repo_plugins_dir():
    return Path(__file__).resolve().parent.parent / "plugins"


class TestPluginDiscovery:
    def test_plugin_skipped_on_free_install(self, repo_plugins_dir):
        loader = PluginLoader(repo_plugins_dir)
        free_mgr = LicenseManager(license_key=None)
        free_mgr.validate_license()
        records = loader.discover_and_load(license_manager=free_mgr)
        rec = next((r for r in records if r.name == PLUGIN_NAME), None)
        assert rec is not None, "extra-protocols dir must be discovered"
        assert rec.loaded is False
        assert rec.skipped is True
        assert "proxy_protocols" in rec.skip_reason

    def test_plugin_loads_when_feature_granted(self, repo_plugins_dir):
        class FakeLM:
            def has_feature(self, name):
                return name == "proxy_protocols"

        loader = PluginLoader(repo_plugins_dir)
        records = loader.discover_and_load(license_manager=FakeLM())
        rec = next((r for r in records if r.name == PLUGIN_NAME), None)
        assert rec is not None
        assert rec.loaded is True, f"plugin failed: {rec.error}"
        assert rec.plugin is not None
        assert rec.plugin.name == PLUGIN_NAME

    def test_plugin_exposes_protocol_features(self, repo_plugins_dir):
        class FakeLM:
            def has_feature(self, name):
                return name == "proxy_protocols"

        loader = PluginLoader(repo_plugins_dir)
        loader.discover_and_load(license_manager=FakeLM())
        # The plugin advertises proxy_protocols + hysteria2 + tuic
        assert "proxy_protocols" in loader.loaded_features()
        assert "hysteria2" in loader.loaded_features()
        assert "tuic" in loader.loaded_features()


# ── License manager feature checks ────────────────────────────────────────────


class TestProtocolFeatureChecks:
    def test_free_blocks_proxy_protocols(self):
        mgr = LicenseManager(license_key=None)
        mgr.validate_license()
        assert mgr.has_feature("proxy_protocols") is False
        assert mgr.has_feature("hysteria2") is False
        assert mgr.has_feature("tuic") is False

    def test_free_allows_amneziawg(self):
        mgr = LicenseManager(license_key=None)
        mgr.validate_license()
        # AmneziaWG stays in FREE — it's the censorship-resistance moat
        assert mgr.has_feature("amneziawg") is True
        assert mgr.has_feature("wireguard") is True
