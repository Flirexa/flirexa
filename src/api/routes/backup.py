"""
VPN Management Studio Backup API Routes
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

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from loguru import logger

from src.database.connection import get_db
from src.modules.backup_manager import BackupManager
from ..middleware.license_gate import require_license_feature

router = APIRouter()

# Auto-backup feature is gated by license. Operations (create/restore/list)
# are FREE so a panel without auto-backup can still take manual backups.
# Settings/mount endpoints stay gated since they configure the scheduler.
_auto_backup_gate = Depends(require_license_feature("auto_backup"))


# ============================================================================
# CONSTANTS — backup configuration keys + defaults
# ============================================================================

BACKUP_CONFIG_KEYS = [
    "backup_enabled", "backup_interval_hours", "backup_hour_utc",
    "backup_retention_count", "backup_auto_cleanup",
    "backup_storage_type", "backup_path",
    "backup_mount_type", "backup_mount_address",
    "backup_mount_username", "backup_mount_password",
    "backup_mount_point", "backup_mount_options",
]

BACKUP_DEFAULTS = {
    "backup_enabled": "true",
    "backup_interval_hours": "24",
    "backup_hour_utc": "3",
    "backup_retention_count": "7",
    "backup_auto_cleanup": "true",
    "backup_storage_type": "local",
    "backup_path": str(Path(__file__).parent.parent.parent.parent / "backups"),
    "backup_mount_type": "smb",
    "backup_mount_address": "",
    "backup_mount_username": "",
    "backup_mount_password": "",
    "backup_mount_point": "/mnt/vpnmanager-backup",
    "backup_mount_options": "",
}


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

_BACKUP_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]+$')
_DANGEROUS_PATHS = {
    "/", "/etc", "/usr", "/bin", "/sbin", "/lib", "/boot",
    "/dev", "/proc", "/sys", "/var", "/root",
}
_MOUNT_OPTIONS_RE = re.compile(r'^[a-zA-Z0-9.,=_\-/]+$')


def _validate_backup_id(backup_id: str) -> str:
    if not backup_id or not _BACKUP_ID_PATTERN.match(backup_id) or '..' in backup_id:
        raise HTTPException(status_code=400, detail="Invalid backup ID format")
    return backup_id


def _validate_backup_path(path: str) -> str:
    """Block dangerous system paths and traversal attempts."""
    path = path.strip()
    if not path or not path.startswith("/"):
        raise HTTPException(status_code=400, detail="Path must be absolute (start with /)")
    normalized = os.path.normpath(path)
    if normalized in _DANGEROUS_PATHS:
        raise HTTPException(status_code=400, detail=f"Dangerous path: {normalized}")
    if ".." in path:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    return normalized


def _validate_mount_options(options: str) -> str:
    options = options.strip()
    if not options:
        return ""
    if not _MOUNT_OPTIONS_RE.match(options):
        raise HTTPException(status_code=400, detail="Invalid characters in mount options")
    return options


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

@router.get("/settings")
def get_backup_settings(db: Session = Depends(get_db)):
    """Return all backup config from SystemConfig with the password masked.

    The frontend uses the `backup_mount_password_set` flag to know whether
    a password is on file (so it can show 'unchanged' as the placeholder)
    without ever sending the raw value back over the wire.
    """
    from src.database.models import SystemConfig

    rows = db.query(SystemConfig).filter(SystemConfig.key.in_(BACKUP_CONFIG_KEYS)).all()
    settings = {r.key: r.value for r in rows}

    result = {}
    for key in BACKUP_CONFIG_KEYS:
        val = settings.get(key, BACKUP_DEFAULTS.get(key, ""))
        if key == "backup_mount_password" and val:
            result[key] = "••••••"
            result["backup_mount_password_set"] = True
        else:
            result[key] = val
    if "backup_mount_password" not in result or not settings.get("backup_mount_password"):
        result["backup_mount_password_set"] = False

    return result


@router.post("/settings")
def update_backup_settings(data: dict, db: Session = Depends(get_db)):
    """Persist backup settings. Validates each field; rejects invalid
    combos (interval not in {6,12,24,48,168}, hour out of 0-23, etc.).
    The password mask placeholder ('••••••') is treated as 'unchanged'
    so re-saving without retyping the password does not clear it."""
    from src.database.models import SystemConfig

    if "backup_path" in data and data["backup_path"]:
        data["backup_path"] = _validate_backup_path(data["backup_path"])
    if "backup_mount_point" in data and data["backup_mount_point"]:
        data["backup_mount_point"] = _validate_backup_path(data["backup_mount_point"])
    if "backup_mount_options" in data:
        data["backup_mount_options"] = _validate_mount_options(data.get("backup_mount_options", ""))
    if "backup_interval_hours" in data:
        try:
            val = int(data["backup_interval_hours"])
            if val not in (6, 12, 24, 48, 168):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid interval_hours, must be 6/12/24/48/168")
    if "backup_hour_utc" in data:
        try:
            val = int(data["backup_hour_utc"])
            if not (0 <= val <= 23):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid hour_utc, must be 0-23")
    if "backup_retention_count" in data:
        try:
            val = int(data["backup_retention_count"])
            if not (1 <= val <= 100):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid retention_count, must be 1-100")

    updated = 0
    for key, value in data.items():
        if key not in BACKUP_CONFIG_KEYS:
            continue
        if key == "backup_mount_password" and value == "••••••":
            continue
        existing = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if existing:
            existing.value = str(value)
        else:
            db.add(SystemConfig(key=key, value=str(value)))
        updated += 1

    db.commit()
    return {"message": f"Updated {updated} backup settings", "updated": updated}


# ============================================================================
# STORAGE / MOUNT
# ============================================================================

@router.post("/storage/mount", dependencies=[_auto_backup_gate])
def mount_network_storage(db: Session = Depends(get_db)):
    """Mount network storage using saved settings. Uses BackupManager so
    password handling (credentials file, not -o password=) lives in one
    place."""
    mgr = BackupManager(db)
    cfg = mgr._get_storage_config()
    if cfg["backup_storage_type"] != "network":
        raise HTTPException(status_code=400, detail="Storage type is not 'network' — mount has no effect")
    if not cfg.get("backup_mount_address"):
        raise HTTPException(status_code=400, detail="Mount address is empty — fill it in Storage settings first")
    try:
        mgr._mount_network_storage(cfg)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Mount failed: {exc}")
    if not BackupManager.is_path_mounted(cfg["backup_mount_point"]):
        raise HTTPException(status_code=500, detail="Mount command succeeded but path is still not a mount point")
    return {
        "status": "ok",
        "message": f"Mounted {cfg['backup_mount_address']} at {cfg['backup_mount_point']}",
        "mount_point": cfg["backup_mount_point"],
    }


@router.post("/storage/unmount", dependencies=[_auto_backup_gate])
def unmount_network_storage(db: Session = Depends(get_db)):
    """Unmount network storage. Refuses to do anything if the configured
    mount point is not actually a mount — avoids surprising the operator
    with 'unmount succeeded' on a regular directory."""
    mgr = BackupManager(db)
    cfg = mgr._get_storage_config()
    mount_point = _validate_backup_path(cfg["backup_mount_point"])
    if not BackupManager.is_path_mounted(mount_point):
        return {"status": "ok", "message": f"{mount_point} is not mounted (nothing to do)"}
    try:
        BackupManager._run_mount_cmd(["umount", mount_point])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unmount failed: {exc}")
    return {"status": "ok", "message": f"Unmounted {mount_point}"}


@router.get("/storage/status")
def get_storage_status(db: Session = Depends(get_db)):
    """Live state of the backup target: storage type, resolved path, mount
    health (network only), disk usage. Drives the Storage status indicator
    in the UI so the operator sees the truth rather than the saved config."""
    mgr = BackupManager(db)
    cfg = mgr._get_storage_config()
    target = mgr._get_backup_dir()

    storage_type = cfg["backup_storage_type"]
    is_mounted = BackupManager.is_path_mounted(target) if storage_type == "network" else None

    usage = None
    try:
        if os.path.exists(target):
            stat = shutil.disk_usage(target)
            usage = {
                "total_bytes": stat.total,
                "used_bytes": stat.used,
                "free_bytes": stat.free,
                "free_mb": stat.free // (1024 * 1024),
                "total_mb": stat.total // (1024 * 1024),
                "percent_used": round((stat.used / stat.total) * 100, 1) if stat.total else 0,
            }
    except OSError as exc:
        logger.warning(f"disk_usage({target}) failed: {exc}")

    return {
        "storage_type": storage_type,
        "target": target,
        "mounted": is_mounted,
        "mount_address": cfg.get("backup_mount_address", ""),
        "usage": usage,
    }


@router.post("/storage/test-write", dependencies=[_auto_backup_gate])
def test_backup_write(db: Session = Depends(get_db)):
    """Probe the target with a tiny write+delete. Surfaces real errors
    (perm denied, ENOSPC, mount stale) before the operator finds out at
    backup time."""
    mgr = BackupManager(db)
    ready = mgr.ensure_storage_ready()
    if not ready["ready"]:
        raise HTTPException(
            status_code=500,
            detail=f"Storage not ready ({ready['storage_type']}): {ready.get('error') or 'unknown'}",
        )
    target = ready["target"]
    test_file = os.path.join(target, ".vms_write_test")
    try:
        with open(test_file, "w") as fh:
            fh.write("vms-test")
        os.remove(test_file)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Write failed: {exc}")
    msg = f"Write OK: {target}"
    if ready["auto_mounted"]:
        msg += " (auto-mounted)"
    return {"status": "ok", "message": msg, "target": target}


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
