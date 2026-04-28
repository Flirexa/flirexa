"""PluginLoader — discovers, validates, and registers premium plugins."""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .base import (
    Plugin,
    PluginLoadError,
    PluginManifestError,
    load_manifest,
)

logger = logging.getLogger(__name__)


# ── Reserved names (handled by other code paths or scaffolding) ──────────────

# `payments` directory is loaded by the existing payment plugin loader in
# api/main.py; the generic loader must skip it.
RESERVED_DIRS = {"payments"}


@dataclass
class PluginRecord:
    """Result of a single plugin load attempt."""
    name: str
    path: Path
    plugin: Optional[Plugin] = None
    loaded: bool = False
    skipped: bool = False
    skip_reason: str = ""
    error: str = ""
    features: list[str] = field(default_factory=list)


class PluginLoader:
    """Scans a plugins directory and loads plugins whose license entitlement
    is satisfied by the current LicenseManager.

    The loader is intentionally idempotent — the result of `discover_and_load`
    is the same whether called once or many times.
    """

    def __init__(self, plugin_dir: Path):
        self.plugin_dir = Path(plugin_dir)
        self.records: dict[str, PluginRecord] = {}

    # ── discovery ────────────────────────────────────────────────────────────

    def _candidate_dirs(self) -> list[Path]:
        if not self.plugin_dir.is_dir():
            return []
        out = []
        for child in sorted(self.plugin_dir.iterdir()):
            if not child.is_dir():
                continue
            if child.name in RESERVED_DIRS:
                continue
            # Skip dotted dirs, dunder dirs (e.g. __pycache__), and underscored
            # template/example dirs (e.g. _example). Plugins live as bare names.
            if child.name.startswith(".") or child.name.startswith("_"):
                continue
            out.append(child)
        return out

    # ── loading one plugin ───────────────────────────────────────────────────

    def _import_plugin_module(self, plugin_path: Path) -> Any:
        """Import the plugin's __init__.py as a module.

        Uses a unique module name (`flirexa_plugin_<name>`) so multiple
        plugins coexist in sys.modules and re-imports during tests are safe.
        """
        init_file = plugin_path / "__init__.py"
        if not init_file.is_file():
            raise PluginLoadError(f"__init__.py missing in {plugin_path}")

        module_name = f"flirexa_plugin_{plugin_path.name.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(
            module_name,
            str(init_file),
            submodule_search_locations=[str(plugin_path)],
        )
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"Could not build import spec for {init_file}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(module_name, None)
            raise PluginLoadError(f"Import failed for {plugin_path.name}: {exc}") from exc
        return module

    def _instantiate_plugin(self, module: Any, manifest: dict, plugin_path: Path) -> Plugin:
        plugin = getattr(module, "PLUGIN", None)
        if plugin is None:
            raise PluginLoadError(
                f"Plugin {plugin_path.name} module does not export PLUGIN attribute"
            )
        if not isinstance(plugin, Plugin):
            raise PluginLoadError(
                f"Plugin {plugin_path.name}.PLUGIN is not a Plugin instance "
                f"(got {type(plugin).__name__})"
            )
        # Sanity: manifest name must match folder + Plugin instance
        if plugin.name != manifest["name"] or plugin.name != plugin_path.name:
            raise PluginLoadError(
                f"Plugin name mismatch: folder={plugin_path.name} "
                f"manifest={manifest['name']} instance={plugin.name}"
            )
        return plugin

    # ── public API ───────────────────────────────────────────────────────────

    def discover_and_load(
        self,
        license_manager: Any = None,
        fastapi_app: Any = None,
    ) -> list[PluginRecord]:
        """Scan plugins/ and load plugins whose license requirements are met.

        Args:
            license_manager: object with `has_feature(name) -> bool`. When None,
                             all entitlement checks are skipped (used in tests).
            fastapi_app: FastAPI instance to mount plugin routers on. When None,
                         routers are returned but not mounted (used in tests).

        Returns:
            List of PluginRecord objects describing each candidate directory.
        """
        self.records.clear()
        for plugin_path in self._candidate_dirs():
            record = PluginRecord(name=plugin_path.name, path=plugin_path)
            self.records[plugin_path.name] = record

            # Stage 1: manifest
            try:
                manifest = load_manifest(plugin_path)
            except PluginManifestError as exc:
                record.error = f"manifest: {exc}"
                logger.warning("Plugin %s skipped (bad manifest): %s", plugin_path.name, exc)
                continue

            # Stage 2: license entitlement
            # The reserved feature name "community" is always granted — it's
            # the way plugin authors declare "no licence required, runs on
            # every install including FREE." Anything else must come from
            # the licence manager.
            if license_manager is not None:
                feature = manifest["requires_license_feature"]
                if feature != "community" and not license_manager.has_feature(feature):
                    record.skipped = True
                    record.skip_reason = f"license missing feature {feature!r}"
                    logger.debug("Plugin %s skipped: %s", plugin_path.name, record.skip_reason)
                    continue

            # Stage 3: import + instantiate
            try:
                module = self._import_plugin_module(plugin_path)
                plugin = self._instantiate_plugin(module, manifest, plugin_path)
            except PluginLoadError as exc:
                record.error = str(exc)
                logger.error("Plugin %s failed to load: %s", plugin_path.name, exc)
                continue

            # Stage 4: register router (if any) on FastAPI app
            router = plugin.get_router()
            if router is not None and fastapi_app is not None:
                try:
                    fastapi_app.include_router(router)
                except Exception as exc:
                    record.error = f"router registration failed: {exc}"
                    logger.error("Plugin %s router failed to mount: %s", plugin_path.name, exc)
                    continue

            # Stage 5: on_load hook (best-effort)
            try:
                plugin.on_load()
            except Exception as exc:
                # Plugin is still considered loaded — on_load is just a hint
                logger.warning("Plugin %s on_load() raised: %s", plugin_path.name, exc)

            record.plugin = plugin
            record.features = list(plugin.get_features())
            record.loaded = True
            logger.info(
                "Plugin loaded: %s v%s (%s)",
                plugin.display_name, plugin.version, plugin.name,
            )

        return list(self.records.values())

    # ── introspection ────────────────────────────────────────────────────────

    def loaded_plugins(self) -> list[Plugin]:
        return [r.plugin for r in self.records.values() if r.loaded and r.plugin is not None]

    def loaded_features(self) -> set[str]:
        feats: set[str] = set()
        for r in self.records.values():
            if r.loaded:
                feats.update(r.features)
        return feats

    def is_loaded(self, plugin_name: str) -> bool:
        rec = self.records.get(plugin_name)
        return bool(rec and rec.loaded)
