"""promo-codes — customer acquisition tools (codes + auto-renewal)."""

from fastapi import APIRouter

from src.modules.plugin_loader import Plugin


router = APIRouter(prefix="/api/v1/plugins/promo-codes", tags=["plugins"])


@router.get("/status")
async def status():
    return {
        "plugin": "promo-codes",
        "version": "1.0.0",
        "active": True,
        "capabilities": ["promo_codes", "auto_renewal"],
    }


class PromoCodesPlugin(Plugin):
    def get_router(self):
        return router

    def get_features(self):
        return ["promo_codes", "auto_renewal"]


_MANIFEST = {
    "name": "promo-codes",
    "version": "1.0.0",
    "display_name": "Promo Codes & Auto-Renewal",
    "requires_license_feature": "promo_codes",
}

PLUGIN = PromoCodesPlugin(_MANIFEST)
