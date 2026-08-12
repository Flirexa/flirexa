"""
Flirexa Backup API Routes
Admin-only endpoints for backup management. Single source of truth — both
the operations (create/list/verify/restore/delete/migrate) AND the
configuration (schedule, storage, mount/unmount, test write) live here.

Until 1.5.83 the surface was split between this module and `system.py`,
which forced the UI to talk to two places and confused operators.

Endpoints
---------
Settings:
  GET    /backup/settings              — full backup config (passwords masked)
  POST   /backup/settings              — update backup config

Storage / mount:
  POST   /backup/storage/mount         — mount network storage with saved creds
  POST   /backup/storage/unmount       — unmount network storage
  GET    /backup/storage/status        — mount + disk-usage status
  POST   /backup/storage/test-write    — write+delete a probe file at target

Operations:
  POST   /backup/create                — create full backup (tar.gz v2)
  GET    /backup/list                  — list all backups
  POST   /backup/verify/{backup_id}    — verify archive integrity
  POST   /backup/restore/full/{id}     — full system restore
  POST   /backup/restore/database/{id} — restore database only
  POST   /backup/restore/server/{srv}/{id}  — restore one server
  DELETE /backup/{backup_id}           — delete backup
  POST   /backup/migrate               — migrate server to new host
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from loguru import logger

from src.database.connection import get_db
from src.modules.backup_manager import BackupAlreadyRunningError, BackupManager
from ..middleware.license_gate import require_license_feature

router = APIRouter()

# Auto-backup feature is gated by license. Operations (create/restore/list)
# are FREE so a panel without auto-backup can still take manual backups.
# Settings/mount endpoints stay gated since they configure the scheduler.
_auto_backup_gate = Depends(require_license_feature("auto_backup"))


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

_BACKUP_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]+$')
def _validate_backup_id(backup_id: str) -> str:
    if not backup_id or not _BACKUP_ID_PATTERN.match(backup_id) or '..' in backup_id:
        raise HTTPException(status_code=400, detail="Invalid backup ID format")
    return backup_id


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class MigrateRequest(BaseModel):
    backup_id: str
    server_name: str
    ssh_host: str
    ssh_port: int = 22
    ssh_user: str = "root"
    ssh_password: str = ""
    ssh_private_key: Optional[str] = None


class FullRestoreRequest(BaseModel):
    restart_services: bool = True


# ============================================================================
# SETTINGS — get / update the entire backup config
# ============================================================================

@router.get("/settings", dependencies=[_auto_backup_gate])
def get_backup_settings(db: Session = Depends(get_db)):
    from ...modules.auto_backup_admin import get_backup_settings as protected_get

    return protected_get(db)


@router.post("/settings", dependencies=[_auto_backup_gate])
def update_backup_settings(data: dict, db: Session = Depends(get_db)):
    from ...modules.auto_backup_admin import (
        update_backup_settings as protected_update,
    )

    return protected_update(data, db)


# ============================================================================
# STORAGE / MOUNT
# ============================================================================

@router.post("/storage/mount", dependencies=[_auto_backup_gate])
def mount_network_storage(db: Session = Depends(get_db)):
    from ...modules.auto_backup_admin import mount_network_storage as protected_mount

    return protected_mount(db)


@router.post("/storage/unmount", dependencies=[_auto_backup_gate])
def unmount_network_storage(db: Session = Depends(get_db)):
    from ...modules.auto_backup_admin import (
        unmount_network_storage as protected_unmount,
    )

    return protected_unmount(db)


@router.get("/storage/status", dependencies=[_auto_backup_gate])
def get_storage_status(db: Session = Depends(get_db)):
    from ...modules.auto_backup_admin import get_storage_status as protected_status

    return protected_status(db)


@router.post("/storage/test-write", dependencies=[_auto_backup_gate])
def test_backup_write(db: Session = Depends(get_db)):
    from ...modules.auto_backup_admin import test_backup_write as protected_test

    return protected_test(db)


# ============================================================================
# OPERATIONS — create / list / verify / restore / delete / migrate
# ============================================================================

@router.post("/create")
def create_backup(db: Session = Depends(get_db)):
    """Create a full system backup (tar.gz with DB + .env + WireGuard configs).

    BackupManager.create_full_backup auto-mounts network storage if needed
    and refuses to write to an unmounted-but-existing-as-dir target. So a
    failure here is a real failure, not a silent-write-to-local-disk.
    """
    try:
        mgr = BackupManager(db)
        metadata = mgr.create_full_backup()
        # Strip internal-only fields before returning to the UI
        safe = {k: v for k, v in metadata.items() if k not in ("archive_path", "checksums")}
        return {"success": True, "backup": safe}
    except BackupAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.error(f"Backup creation failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}")


@router.get("/list")
def list_backups(db: Session = Depends(get_db)):
    """List all available backups with timestamps and sizes."""
    try:
        mgr = BackupManager(db)
        backups = mgr.list_backups()
        safe = []
        for b in backups:
            entry = {k: v for k, v in b.items() if k not in ("archive_path", "backup_dir", "checksums")}
            safe.append(entry)
        return {"backups": safe, "count": len(safe)}
    except Exception as exc:
        logger.error(f"Backup list failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/verify/{backup_id}")
def verify_backup(backup_id: str, db: Session = Depends(get_db)):
    """Verify backup archive integrity and checksums."""
    _validate_backup_id(backup_id)
    try:
        mgr = BackupManager(db)
        return mgr.verify_backup(backup_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Backup verification failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/restore/full/{backup_id}")
def restore_full_system(
    backup_id: str,
    req: FullRestoreRequest = FullRestoreRequest(),
    db: Session = Depends(get_db),
):
    """Full disaster recovery: database + .env + WireGuard configs.
    Creates a pre-restore safety snapshot automatically."""
    _validate_backup_id(backup_id)
    try:
        mgr = BackupManager(db)
        result = mgr.restore_full_system(backup_id, restart_services=req.restart_services)
        return {"success": True, "result": result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Full restore failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/restore/database/{backup_id}")
def restore_database(backup_id: str, db: Session = Depends(get_db)):
    """Restore database from a backup (v1 or v2 format)."""
    _validate_backup_id(backup_id)
    try:
        mgr = BackupManager(db)
        mgr.restore_database(backup_id)
        return {"success": True, "message": f"Database restored from backup {backup_id}"}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Database restore failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/restore/server/{server_id}/{backup_id}")
def restore_server(server_id: int, backup_id: str, db: Session = Depends(get_db)):
    """Restore a server's clients and WG config from backup."""
    _validate_backup_id(backup_id)
    try:
        mgr = BackupManager(db)
        result = mgr.restore_server_from_backup(server_id, backup_id)
        return {"success": True, "result": result}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Server restore failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{backup_id}")
def delete_backup(backup_id: str, db: Session = Depends(get_db)):
    """Delete a specific backup."""
    _validate_backup_id(backup_id)
    try:
        mgr = BackupManager(db)
        mgr.delete_backup(backup_id)
        return {"success": True, "message": f"Backup {backup_id} deleted"}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Backup deletion failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/migrate")
def migrate_server(req: MigrateRequest, db: Session = Depends(get_db)):
    """Migrate a server to a new host using backup data."""
    try:
        mgr = BackupManager(db)
        result = mgr.migrate_server(
            backup_id=req.backup_id,
            server_name=req.server_name,
            new_ssh_host=req.ssh_host,
            new_ssh_port=req.ssh_port,
            new_ssh_user=req.ssh_user,
            new_ssh_password=req.ssh_password,
            new_ssh_private_key=req.ssh_private_key,
        )
        return {"success": True, "result": result}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Server migration failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
