"""Tests for the Phase 5 batch of license-gated plugins.

Covered plugins (all gate-only — the implementation lives in core):
- white-label-basic       (white_label_basic, Business+)
- client-tg-bot           (telegram_client_bot, Business+)
- traffic-rules           (traffic_rules, Business+)
- promo-codes             (promo_codes, Starter+)
- auto-backup             (auto_backup, Business+)
- manager-rbac            (manager_rbac, Enterprise)
- corporate-vpn           (corporate_vpn, Enterprise)

Each test verifies:
- The plugin's required feature is present in the expected paid tiers
- FREE installs skip the plugin (no router mounted, no traces)
- The plugin loads when the feature is granted
"""

from pathlib import Path

import pytest

from src.modules.license.manager import (
    LICENSE_TIERS,
    LicenseManager,
    LicenseType,
)
from src.modules.plugin_loader import PluginLoader


PLUGINS = [
    # (plugin_name, required_feature, tiers_with_feature)
    ("white-label-basic", "white_label_basic",
     [LicenseType.PRO, LicenseType.BUSINESS, LicenseType.ENTERPRISE]),
    ("client-tg-bot", "telegram_client_bot",
     [LicenseType.BUSINESS, LicenseType.ENTERPRISE]),
    ("traffic-rules", "traffic_rules",
     [LicenseType.PRO, LicenseType.BUSINESS, LicenseType.ENTERPRISE]),
    ("promo-codes", "promo_codes",
     [LicenseType.STANDARD, LicenseType.STARTER, LicenseType.PRO,
      LicenseType.BUSINESS, LicenseType.ENTERPRISE]),
    ("auto-backup", "auto_backup",
     [LicenseType.PRO, LicenseType.BUSINESS, LicenseType.ENTERPRISE]),
    ("manager-rbac", "manager_rbac",
     [LicenseType.ENTERPRISE]),
    ("corporate-vpn", "corporate_vpn",
     [LicenseType.ENTERPRISE]),
]


@pytest.fixture
def repo_plugins_dir():
    return Path(__file__).resolve().parent.parent / "plugins"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("LICENSE_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_LICENSE_MODE", raising=False)


# ── Tier feature presence ────────────────────────────────────────────────────


@pytest.mark.parametrize("plugin_name,feature,tiers", PLUGINS)
def test_feature_in_expected_tiers(plugin_name, feature, tiers):
    for tier in tiers:
        assert feature in LICENSE_TIERS[tier]["features"], (
            f"{tier.value} should grant {feature!r} for plugin {plugin_name}"
        )


@pytest.mark.parametrize("plugin_name,feature,_", PLUGINS)
def test_free_lacks_all_phase5_features(plugin_name, feature, _):
    free = LICENSE_TIERS[LicenseType.FREE]
    assert feature not in free["features"], (
        f"FREE must not grant {feature!r} (would unlock {plugin_name})"
    )


# ── Plugin discovery ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("plugin_name,feature,_", PLUGINS)
def test_plugin_skipped_on_free(plugin_name, feature, _, repo_plugins_dir):
    loader = PluginLoader(repo_plugins_dir)
    free_mgr = LicenseManager(license_key=None)
    free_mgr.validate_license()
    records = loader.discover_and_load(license_manager=free_mgr)
    rec = next((r for r in records if r.name == plugin_name), None)
    assert rec is not None, f"{plugin_name} dir should be discovered"
    assert rec.skipped is True, f"{plugin_name} should skip on FREE"
    assert feature in rec.skip_reason


@pytest.mark.parametrize("plugin_name,feature,_", PLUGINS)
def test_plugin_loads_when_feature_granted(plugin_name, feature, _, repo_plugins_dir):
    class FakeLM:
        def has_feature(self, name):
            return name == feature

    loader = PluginLoader(repo_plugins_dir)
    records = loader.discover_and_load(license_manager=FakeLM())
    rec = next((r for r in records if r.name == plugin_name), None)
    assert rec is not None
    assert rec.loaded is True, f"{plugin_name} failed to load: {rec.error}"
    assert rec.plugin is not None
    assert rec.plugin.name == plugin_name


# ── Sanity: full Phase 5 set discoverable on a maximal license ──────────────


def test_all_phase5_plugins_load_on_enterprise(repo_plugins_dir):
    """An ENTERPRISE-equivalent license should load every Phase 5 plugin."""
    enterprise_features = LICENSE_TIERS[LicenseType.ENTERPRISE]["features"]

    class EnterpriseMgr:
        def has_feature(self, name):
            return name in enterprise_features

    loader = PluginLoader(repo_plugins_dir)
    records = loader.discover_and_load(license_manager=EnterpriseMgr())
    loaded = {r.name for r in records if r.loaded}

    expected = {p[0] for p in PLUGINS}
    missing = expected - loaded
    assert not missing, f"ENTERPRISE failed to load: {missing}"


# ── Tier limit alignment with feature_split_mapping doc ──────────────────────


def test_starter_does_not_get_business_features():
    """STARTER must not include Business-only features."""
    starter = LICENSE_TIERS[LicenseType.STARTER]["features"]
    business_only = ["multi_server", "telegram_client_bot",
                     "white_label_basic", "auto_backup", "traffic_rules"]
    leaks = [f for f in business_only if f in starter]
    assert not leaks, f"STARTER leaked Business features: {leaks}"


def test_business_does_not_get_enterprise_features():
    business = LICENSE_TIERS[LicenseType.BUSINESS]["features"]
    enterprise_only = ["corporate_vpn", "manager_rbac", "white_label"]
    leaks = [f for f in enterprise_only if f in business]
    assert not leaks, f"BUSINESS leaked Enterprise features: {leaks}"
