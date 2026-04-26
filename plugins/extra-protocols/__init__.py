"""
extra-protocols plugin — Hysteria2 + TUIC support gate.

The actual protocol implementations live in src/core/{hysteria2,tuic}.py
inside the open-core codebase; this plugin's role is to:

1. Declare the `proxy_protocols` license feature requirement so the
   generic plugin loader skips loading it on FREE installs.
2. Expose a tiny status route (/api/v1/plugins/extra-protocols/status)
   so admins can verify the plugin is active.
3. Surface in the introspection API (/system/plugins, app.state.plugin_loader)
   so the admin UI can show "Hysteria2/TUIC: enabled" instead of probing
   license features directly.

Server-side enforcement of the proxy_protocols feature is in
src/api/routes/servers.py — the create-server endpoint blocks
hysteria2/tuic when the feature flag is absent.
"""

from fastapi import APIRouter

from src.modules.plugin_loader import Plugin


router = APIRouter(prefix="/api/v1/plugins/extra-protocols", tags=["plugins"])


@router.get("/status")
async def status():
    """Confirm the plugin is loaded and which protocols it unlocks."""
    return {
        "plugin": "extra-protocols",
        "version": "1.0.0",
        "active": True,
        "protocols": ["hysteria2", "tuic"],
    }


class ExtraProtocolsPlugin(Plugin):
    def get_router(self):
        return router

    def get_features(self):
        # Provides the umbrella feature plus per-protocol flags for UI
        # convenience (Servers.vue can render protocol cards based on these).
        return ["proxy_protocols", "hysteria2", "tuic"]


_MANIFEST = {
    "name": "extra-protocols",
    "version": "1.0.0",
    "display_name": "Extra Protocols (Hysteria2 + TUIC)",
    "requires_license_feature": "proxy_protocols",
}

PLUGIN = ExtraProtocolsPlugin(_MANIFEST)
