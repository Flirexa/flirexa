"""License gate for Hysteria2 + TUIC support.

Protocol implementations live in src/core/{hysteria2,tuic}.py. This file
declares the license-feature flag and exposes a status endpoint so the
admin UI can render Hysteria2/TUIC affordances when the plugin is active.
Server-side enforcement (blocking server creation with these protocols on
FREE) is in src/api/routes/servers.py.
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
