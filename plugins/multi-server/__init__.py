"""
multi-server plugin — orchestration of remote VPN servers.

Like extra-protocols, the implementation lives in the open-core codebase
(src/api/routes/servers.py for create/list/discover, src/api/routes/agent.py
for the agent lifecycle, src/core/agent_client.py for HTTP transport).
This plugin's role is the license boundary, not the implementation:

1. Declare the `multi_server` feature so the plugin loader skips it on
   FREE installs (the loader already prevents 1-server lockouts: FREE
   has max_servers=1, so users never see multi-server UI affordances).
2. Centralise the upgrade-prompt copy in /api/v1/plugins/multi-server/status
   so admin UI banners stay consistent.
3. Surface in app.state.plugin_loader for introspection.

Server-side enforcement of the multi_server feature lives in:
- src/api/routes/servers.py: create-server limit + /discover + /install-agent
- src/api/routes/agent.py: install/uninstall/switch-mode

(Read-only endpoints — list servers, agent-status — stay open so admins
who downgrade can still observe their inherited fleet.)
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
