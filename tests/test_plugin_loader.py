"""Tests for the generic plugin loader.

Verifies manifest validation, license-gated discovery, and integration with
FastAPI router mounting.
"""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI

from src.modules.plugin_loader import (
    Plugin,
    PluginLoader,
    PluginLoadError,
    PluginManifestError,
)
from src.modules.plugin_loader.base import load_manifest


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _write_plugin(
    base_dir: Path,
    name: str,
    *,
    manifest: dict | None = None,
    init_py: str | None = None,
) -> Path:
    """Create a minimal plugin directory with a manifest and __init__.py."""
    plugin_dir = base_dir / name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    if manifest is None:
        manifest = {
            "name": name,
            "version": "1.0.0",
            "display_name": name.replace("-", " ").title(),
            "requires_license_feature": f"{name.replace('-', '_')}_feature",
        }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    if init_py is None:
        init_py = f'''
from src.modules.plugin_loader import Plugin
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/{name}")

@router.get("/ping")
async def ping():
    return {{"plugin": "{name}"}}

class _P(Plugin):
    def get_router(self):
        return router

PLUGIN = _P({json.dumps(manifest)})
'''
    (plugin_dir / "__init__.py").write_text(init_py, encoding="utf-8")
    return plugin_dir


class FakeLicenseManager:
    def __init__(self, features):
        self._features = set(features)

    def has_feature(self, name):
        return name in self._features


# ── Manifest validation ──────────────────────────────────────────────────────


class TestManifestValidation:
    def test_valid_manifest(self, tmp_path):
        plugin_dir = _write_plugin(tmp_path, "valid-plugin")
        manifest = load_manifest(plugin_dir)
        assert manifest["name"] == "valid-plugin"

    def test_missing_manifest_file(self, tmp_path):
        plugin_dir = tmp_path / "no-manifest"
        plugin_dir.mkdir()
        with pytest.raises(PluginManifestError, match="manifest.json not found"):
            load_manifest(plugin_dir)

    def test_invalid_json(self, tmp_path):
        plugin_dir = tmp_path / "bad-json"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.json").write_text("{ not json")
        with pytest.raises(PluginManifestError, match="Invalid JSON"):
            load_manifest(plugin_dir)

    def test_missing_required_fields(self, tmp_path):
        plugin_dir = _write_plugin(
            tmp_path, "incomplete",
            manifest={"name": "incomplete"},
        )
        with pytest.raises(PluginManifestError, match="missing required fields"):
            load_manifest(plugin_dir)

    def test_unknown_field_rejected(self, tmp_path):
        plugin_dir = _write_plugin(
            tmp_path, "with-typo",
            manifest={
                "name": "with-typo",
                "version": "1.0.0",
                "display_name": "x",
                "requires_license_feature": "f",
                "typo_field": "oops",   # not in ALLOWED_FIELDS
            },
        )
        with pytest.raises(PluginManifestError, match="unknown fields"):
            load_manifest(plugin_dir)

    def test_invalid_name(self, tmp_path):
        plugin_dir = _write_plugin(
            tmp_path, "bad",
            manifest={
                "name": "BadName",   # uppercase not allowed
                "version": "1.0.0",
                "display_name": "x",
                "requires_license_feature": "f",
            },
        )
        with pytest.raises(PluginManifestError, match="Invalid 'name'"):
            load_manifest(plugin_dir)

    def test_invalid_version(self, tmp_path):
        plugin_dir = _write_plugin(
            tmp_path, "bad-ver",
            manifest={
                "name": "bad-ver",
                "version": "1.0",   # not semver
                "display_name": "x",
                "requires_license_feature": "f",
            },
        )
        with pytest.raises(PluginManifestError, match="Invalid 'version'"):
            load_manifest(plugin_dir)


# ── Discovery + loading ──────────────────────────────────────────────────────


class TestDiscovery:
    def test_empty_plugins_dir(self, tmp_path):
        loader = PluginLoader(tmp_path)
        records = loader.discover_and_load(license_manager=FakeLicenseManager([]))
        assert records == []
        assert loader.loaded_plugins() == []

    def test_skips_dunder_and_underscore_dirs(self, tmp_path):
        # __pycache__ and _example must be ignored
        _write_plugin(tmp_path, "real-plugin")
        (tmp_path / "__pycache__").mkdir()
        _write_plugin(tmp_path, "_example")

        loader = PluginLoader(tmp_path)
        lm = FakeLicenseManager(["real_plugin_feature", "_example_feature"])
        records = loader.discover_and_load(license_manager=lm)
        names = {r.name for r in records}
        assert names == {"real-plugin"}

    def test_skips_payments_dir(self, tmp_path):
        # `payments` is reserved for the existing payment plugin loader.
        _write_plugin(tmp_path, "payments", manifest={
            "name": "payments",
            "version": "1.0.0",
            "display_name": "Payments",
            "requires_license_feature": "any",
        })
        loader = PluginLoader(tmp_path)
        records = loader.discover_and_load(license_manager=FakeLicenseManager(["any"]))
        assert records == []


# ── License gating ───────────────────────────────────────────────────────────


class TestLicenseGating:
    def test_loads_when_feature_present(self, tmp_path):
        _write_plugin(tmp_path, "premium-feature")
        loader = PluginLoader(tmp_path)
        lm = FakeLicenseManager(["premium_feature_feature"])
        records = loader.discover_and_load(license_manager=lm)
        assert len(records) == 1
        assert records[0].loaded is True
        assert records[0].plugin is not None

    def test_skips_when_feature_missing(self, tmp_path):
        _write_plugin(tmp_path, "premium-feature")
        loader = PluginLoader(tmp_path)
        lm = FakeLicenseManager([])  # no features
        records = loader.discover_and_load(license_manager=lm)
        assert len(records) == 1
        rec = records[0]
        assert rec.loaded is False
        assert rec.skipped is True
        assert "license missing feature" in rec.skip_reason

    def test_loads_all_when_license_manager_none(self, tmp_path):
        # Test convenience: pass None to skip entitlement checks entirely.
        _write_plugin(tmp_path, "test-plugin")
        loader = PluginLoader(tmp_path)
        records = loader.discover_and_load(license_manager=None)
        assert records[0].loaded is True

    def test_partial_loads_with_mixed_features(self, tmp_path):
        _write_plugin(tmp_path, "available-plugin", manifest={
            "name": "available-plugin",
            "version": "1.0.0",
            "display_name": "Available",
            "requires_license_feature": "feature_a",
        })
        _write_plugin(tmp_path, "blocked-plugin", manifest={
            "name": "blocked-plugin",
            "version": "1.0.0",
            "display_name": "Blocked",
            "requires_license_feature": "feature_b",
        })
        loader = PluginLoader(tmp_path)
        records = loader.discover_and_load(license_manager=FakeLicenseManager(["feature_a"]))
        assert {r.name: r.loaded for r in records} == {
            "available-plugin": True,
            "blocked-plugin": False,
        }


# ── Plugin loading errors ────────────────────────────────────────────────────


class TestLoadErrors:
    def test_missing_init_py(self, tmp_path):
        plugin_dir = tmp_path / "no-init"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.json").write_text(json.dumps({
            "name": "no-init",
            "version": "1.0.0",
            "display_name": "x",
            "requires_license_feature": "f",
        }))
        loader = PluginLoader(tmp_path)
        records = loader.discover_and_load(license_manager=FakeLicenseManager(["f"]))
        assert records[0].loaded is False
        assert "__init__.py missing" in records[0].error

    def test_no_plugin_attribute(self, tmp_path):
        _write_plugin(
            tmp_path, "no-plugin-attr",
            init_py="# no PLUGIN here\n",
        )
        loader = PluginLoader(tmp_path)
        records = loader.discover_and_load(
            license_manager=FakeLicenseManager(["no_plugin_attr_feature"])
        )
        assert records[0].loaded is False
        assert "does not export PLUGIN attribute" in records[0].error

    def test_plugin_not_subclass(self, tmp_path):
        _write_plugin(
            tmp_path, "wrong-type",
            init_py="PLUGIN = 'just a string'\n",
        )
        loader = PluginLoader(tmp_path)
        records = loader.discover_and_load(
            license_manager=FakeLicenseManager(["wrong_type_feature"])
        )
        assert records[0].loaded is False
        assert "not a Plugin instance" in records[0].error

    def test_manifest_name_mismatch(self, tmp_path):
        # manifest.name == "wrong" but folder is "right"
        _write_plugin(tmp_path, "right", manifest={
            "name": "wrong",
            "version": "1.0.0",
            "display_name": "x",
            "requires_license_feature": "f",
        })
        loader = PluginLoader(tmp_path)
        records = loader.discover_and_load(license_manager=FakeLicenseManager(["f"]))
        # manifest.json validation passes (name matches itself), but the
        # instantiate step catches the folder/instance mismatch.
        rec = records[0]
        assert rec.loaded is False
        assert "name mismatch" in rec.error


# ── FastAPI integration ──────────────────────────────────────────────────────


class TestFastAPIRegistration:
    def test_router_mounted_on_app(self, tmp_path):
        _write_plugin(tmp_path, "with-router")
        app = FastAPI()
        loader = PluginLoader(tmp_path)
        loader.discover_and_load(
            license_manager=FakeLicenseManager(["with_router_feature"]),
            fastapi_app=app,
        )
        # Verify the route was added
        routes = [r.path for r in app.routes]
        assert "/api/v1/with-router/ping" in routes

    def test_no_router_no_problem(self, tmp_path):
        _write_plugin(
            tmp_path, "no-router",
            init_py='''
from src.modules.plugin_loader import Plugin

class _P(Plugin):
    pass

PLUGIN = _P({"name": "no-router", "version": "1.0.0", "display_name": "X", "requires_license_feature": "no_router_feature"})
''',
        )
        app = FastAPI()
        loader = PluginLoader(tmp_path)
        records = loader.discover_and_load(
            license_manager=FakeLicenseManager(["no_router_feature"]),
            fastapi_app=app,
        )
        assert records[0].loaded is True


# ── Introspection ────────────────────────────────────────────────────────────


class TestIntrospection:
    def test_loaded_features_collects_all(self, tmp_path):
        _write_plugin(tmp_path, "alpha", manifest={
            "name": "alpha",
            "version": "1.0.0",
            "display_name": "A",
            "requires_license_feature": "alpha",
        })
        _write_plugin(tmp_path, "beta", manifest={
            "name": "beta",
            "version": "1.0.0",
            "display_name": "B",
            "requires_license_feature": "beta",
        })
        loader = PluginLoader(tmp_path)
        loader.discover_and_load(license_manager=FakeLicenseManager(["alpha", "beta"]))
        assert loader.loaded_features() == {"alpha", "beta"}
        assert loader.is_loaded("alpha") is True
        assert loader.is_loaded("beta") is True
        assert loader.is_loaded("nonexistent") is False
