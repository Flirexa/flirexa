"""License gate for the multi_server feature.

Implementation lives in src/api/routes/{servers,agent}.py. This file only
declares the license-feature flag so the plugin loader skips it on FREE.
Read-only endpoints (list servers, agent status) stay open so users who
downgrade can still see servers they had on a paid period.
"""

from fastapi import APIRouter

from src.modules.plugin_loader import Plugin


router = APIRouter(prefix="/api/v1/plugins/multi-server", tags=["plugins"])


@router.get("/status")
async def status():
    return {
        "plugin": "multi-server",
        "version": "1.0.0",
        "active": True,
        "capabilities": [
            "remote_server_discovery",
            "agent_install",
            "agent_mode_switching",
            "aggregated_stats",
        ],
    }


class MultiServerPlugin(Plugin):
    def get_router(self):
        return router

    def get_features(self):
        return ["multi_server"]


_MANIFEST = {
    "name": "multi-server",
    "version": "1.0.0",
    "display_name": "Multi-Server Management",
    "requires_license_feature": "multi_server",
}

PLUGIN = MultiServerPlugin(_MANIFEST)
