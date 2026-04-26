"""
Generic plugin loader for premium feature plugins.

Plugin layout:
    plugins/<plugin_name>/
        manifest.json     — metadata + license requirement (required)
        __init__.py       — exports `PLUGIN: Plugin` instance (required)
        backend/          — optional: routes, services, models
        frontend/         — optional: Vue components (lazy-loaded)

Usage:
    from src.modules.plugin_loader import PluginLoader
    loader = PluginLoader(plugin_dir=Path("plugins"))
    loaded = loader.discover_and_load(license_manager=lm, fastapi_app=app)

Premium plugins (multi-server, corporate-vpn, etc.) are loaded only if the
current license grants the required feature. Without entitlement, the plugin
directory is silently skipped — FREE installs see no traces.
"""

from .base import Plugin, PluginLoadError, PluginManifestError
from .loader import PluginLoader, PluginRecord

__all__ = [
    "Plugin",
    "PluginLoadError",
    "PluginManifestError",
    "PluginLoader",
    "PluginRecord",
]
