"""manager-rbac — multi-admin role-based access control."""

from fastapi import APIRouter

from src.modules.plugin_loader import Plugin


router = APIRouter(prefix="/api/v1/plugins/manager-rbac", tags=["plugins"])


@router.get("/status")
async def status():
    return {"plugin": "manager-rbac", "version": "1.0.0", "active": True}


class ManagerRbacPlugin(Plugin):
    def get_router(self):
        return router


_MANIFEST = {
    "name": "manager-rbac",
    "version": "1.0.0",
    "display_name": "Manager Roles & RBAC",
    "requires_license_feature": "manager_rbac",
}

PLUGIN = ManagerRbacPlugin(_MANIFEST)
