"""
Example plugin — reference scaffolding.

Copy this directory to plugins/<your-plugin-name>/, edit manifest.json,
and implement your routes/services in backend/.

This plugin requires a fictitious license feature so it never loads in
production; it exists purely as a template and as a fixture for tests.
"""

from src.modules.plugin_loader import Plugin
from .backend.routes import router


class ExamplePlugin(Plugin):
    """Plugin entry point — mounts a single demo route."""

    def get_router(self):
        return router

    def on_load(self):
        # Place to start background tasks, prime caches, run startup checks.
        return None


_MANIFEST = {
    "name": "_example",
    "version": "0.1.0",
    "display_name": "Example Plugin",
    "requires_license_feature": "_example_feature_that_no_one_has",
}

PLUGIN = ExamplePlugin(_MANIFEST)
