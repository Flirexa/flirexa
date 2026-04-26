"""Plugin base class and manifest validation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional, Any

from fastapi import APIRouter


class PluginManifestError(ValueError):
    """Manifest is missing or malformed."""


class PluginLoadError(RuntimeError):
    """Plugin failed to load (import error, invalid Plugin class, etc.)."""


# ── Manifest schema ──────────────────────────────────────────────────────────

REQUIRED_FIELDS = {"name", "version", "display_name", "requires_license_feature"}
OPTIONAL_FIELDS = {
    "description",
    "min_app_version",
    "min_tier",          # informational: "starter" / "business" / "enterprise"
    "author",
    "homepage",
    "frontend_chunks",   # list[str]: Vue chunk names to lazy-load on the admin
}
ALLOWED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[\w.-]+)?$")


def load_manifest(plugin_dir: Path) -> dict:
    """Load and validate manifest.json from a plugin directory.

    Raises PluginManifestError on any validation failure.
    """
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.is_file():
        raise PluginManifestError(f"manifest.json not found in {plugin_dir}")

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest: Any = json.load(f)
    except json.JSONDecodeError as exc:
        raise PluginManifestError(f"Invalid JSON in {manifest_path}: {exc}") from exc

    if not isinstance(manifest, dict):
        raise PluginManifestError(f"Manifest must be a JSON object, got {type(manifest).__name__}")

    missing = REQUIRED_FIELDS - manifest.keys()
    if missing:
        raise PluginManifestError(f"Manifest missing required fields: {sorted(missing)}")

    # Reject unknown fields to catch typos early
    extra = set(manifest.keys()) - ALLOWED_FIELDS
    if extra:
        raise PluginManifestError(f"Manifest has unknown fields: {sorted(extra)}")

    # Field validation
    name = manifest["name"]
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise PluginManifestError(
            f"Invalid 'name' (must be lowercase, letters/digits/hyphen, 2-40 chars): {name!r}"
        )

    version = manifest["version"]
    if not isinstance(version, str) or not _SEMVER_RE.match(version):
        raise PluginManifestError(f"Invalid 'version' (must be semver MAJOR.MINOR.PATCH): {version!r}")

    if not isinstance(manifest["display_name"], str) or not manifest["display_name"].strip():
        raise PluginManifestError("'display_name' must be a non-empty string")

    feat = manifest["requires_license_feature"]
    if not isinstance(feat, str) or not feat.strip():
        raise PluginManifestError("'requires_license_feature' must be a non-empty string")

    if "frontend_chunks" in manifest:
        chunks = manifest["frontend_chunks"]
        if not isinstance(chunks, list) or not all(isinstance(c, str) for c in chunks):
            raise PluginManifestError("'frontend_chunks' must be a list of strings")

    return manifest


# ── Plugin base class ────────────────────────────────────────────────────────


class Plugin:
    """Base class for premium feature plugins.

    Subclasses live inside the plugin's __init__.py and override the hooks
    they need. The plugin's __init__.py must export a `PLUGIN` attribute
    that is an instance of this class.

    Example:
        # plugins/multi-server/__init__.py
        from src.modules.plugin_loader import Plugin
        from .backend.routes import router

        class MultiServerPlugin(Plugin):
            def get_router(self):
                return router

        PLUGIN = MultiServerPlugin(manifest)
    """

    def __init__(self, manifest: dict):
        self.manifest = manifest
        self.name: str = manifest["name"]
        self.version: str = manifest["version"]
        self.display_name: str = manifest["display_name"]
        self.requires_license_feature: str = manifest["requires_license_feature"]

    # ── hooks (override as needed) ────────────────────────────────────────

    def get_router(self) -> Optional[APIRouter]:
        """Return a FastAPI router to mount, or None if plugin adds no routes."""
        return None

    def get_features(self) -> list[str]:
        """Return additional feature flags this plugin provides at runtime.

        Used by the admin UI to show plugin-specific controls. Defaults to
        the single feature this plugin requires.
        """
        return [self.requires_license_feature]

    def on_load(self) -> None:
        """Called once after the plugin is registered with the app.

        Override to start background tasks, prime caches, etc. Errors
        raised here will not prevent the plugin from being marked active,
        but will be logged.
        """
        return None

    def on_unload(self) -> None:
        """Called when the plugin is being unloaded (license expired, etc.)."""
        return None

    # ── representation ────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<Plugin {self.name} v{self.version}>"
