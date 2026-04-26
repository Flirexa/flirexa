"""auto-backup — scheduled backups + remote storage mount."""

from fastapi import APIRouter

from src.modules.plugin_loader import Plugin


router = APIRouter(prefix="/api/v1/plugins/auto-backup", tags=["plugins"])


@router.get("/status")
async def status():
    return {"plugin": "auto-backup", "version": "1.0.0", "active": True}


class AutoBackupPlugin(Plugin):
    def get_router(self):
        return router


_MANIFEST = {
    "name": "auto-backup",
    "version": "1.0.0",
    "display_name": "Automatic Backups",
    "requires_license_feature": "auto_backup",
}

PLUGIN = AutoBackupPlugin(_MANIFEST)
