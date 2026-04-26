"""traffic-rules — bandwidth caps and automatic throttling rules."""

from fastapi import APIRouter

from src.modules.plugin_loader import Plugin


router = APIRouter(prefix="/api/v1/plugins/traffic-rules", tags=["plugins"])


@router.get("/status")
async def status():
    return {"plugin": "traffic-rules", "version": "1.0.0", "active": True}


class TrafficRulesPlugin(Plugin):
    def get_router(self):
        return router


_MANIFEST = {
    "name": "traffic-rules",
    "version": "1.0.0",
    "display_name": "Traffic Rules & Auto-Throttling",
    "requires_license_feature": "traffic_rules",
}

PLUGIN = TrafficRulesPlugin(_MANIFEST)
