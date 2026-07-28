"""Enterprise white-label appearance gate."""

from fastapi import APIRouter

from src.modules.plugin_loader import Plugin


router = APIRouter(prefix="/api/v1/plugins/white-label-basic", tags=["plugins"])


@router.get("/status")
async def status():
    return {"plugin": "white-label-basic", "version": "1.0.0", "active": True}


class WhiteLabelBasicPlugin(Plugin):
    def get_router(self):
        return router


_MANIFEST = {
    "name": "white-label-basic",
    "version": "1.0.0",
    "display_name": "White-Label Branding",
    "requires_license_feature": "white_label",
}

PLUGIN = WhiteLabelBasicPlugin(_MANIFEST)
