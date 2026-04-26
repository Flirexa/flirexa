"""corporate-vpn — site-to-site mesh VPN for B2B / Enterprise."""

from fastapi import APIRouter

from src.modules.plugin_loader import Plugin


router = APIRouter(prefix="/api/v1/plugins/corporate-vpn", tags=["plugins"])


@router.get("/status")
async def status():
    return {"plugin": "corporate-vpn", "version": "1.0.0", "active": True}


class CorporateVpnPlugin(Plugin):
    def get_router(self):
        return router


_MANIFEST = {
    "name": "corporate-vpn",
    "version": "1.0.0",
    "display_name": "Corporate VPN (Site-to-Site)",
    "requires_license_feature": "corporate_vpn",
}

PLUGIN = CorporateVpnPlugin(_MANIFEST)
