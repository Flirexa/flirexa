"""
VPN Management Studio Backup API Routes
Admin-only endpoints for backup management.

POST   /backup/create                    — create full backup (tar.gz v2)
GET    /backup/list                      — list all backups
POST   /backup/verify/{backup_id}        — verify archive integrity + checksums
POST   /backup/restore/full/{backup_id}  — full system restore (DB + .env + WireGuard)
POST   /backup/restore/database/{backup_id}  — restore database only
POST   /backup/restore/server/{server_id}/{backup_id}  — restore one server
DELETE /backup/{backup_id}               — delete backup
POST   /backup/migrate                   — migrate server to new host
"""

import re
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from loguru import logger

from src.database.connection import get_db
from src.modules.backup_manager import BackupManager

router = APIRouter()

_BACKUP_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]+$')


def _validate_backup_id(backup_id: str) -> str:
    if not backup_id or not _BACKUP_ID_PATTERN.match(backup_id) or '..' in backup_id:
        raise HTTPException(status_code=400, detail="Invalid backup ID format")
    return backup_id


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


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/create")
async def create_backup(db=Depends(get_db)):
    """Create a full system backup (tar.gz with DB + .env + WireGuard configs)."""
    try:
        mgr = BackupManager(db)
        metadata = mgr.create_full_backup()
        # Don't expose archive_path or env contents in response
        safe = {k: v for k, v in metadata.items()
                if k not in ("archive_path", "checksums")}
        return {"success": True, "backup": safe}
    except Exception as e:
        logger.error(f"Backup creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/list")
async def list_backups(db=Depends(get_db)):
    """List all available backups with timestamps and sizes."""
    try:
        mgr = BackupManager(db)
        backups = mgr.list_backups()
        # Strip sensitive paths from listing
        safe = []
        for b in backups:
            entry = {k: v for k, v in b.items()
                     if k not in ("archive_path", "backup_dir", "checksums")}
            safe.append(entry)
        return {"backups": safe, "count": len(safe)}
    except Exception as e:
        logger.error(f"Backup list failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Verify ────────────────────────────────────────────────────────────────────

@router.post("/verify/{backup_id}")
async def verify_backup(backup_id: str, db=Depends(get_db)):
    """Verify backup archive integrity and checksums."""
    _validate_backup_id(backup_id)
    try:
        mgr = BackupManager(db)
        result = mgr.verify_backup(backup_id)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Backup verification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Restore: full system ──────────────────────────────────────────────────────

@router.post("/restore/full/{backup_id}")
async def restore_full_system(
    backup_id: str,
    req: FullRestoreRequest = FullRestoreRequest(),
    db=Depends(get_db),
):
    """
    Full disaster recovery restore: database + .env + WireGuard configs.
    Creates a pre-restore safety snapshot automatically.
    """
    _validate_backup_id(backup_id)
    try:
        mgr = BackupManager(db)
        result = mgr.restore_full_system(backup_id, restart_services=req.restart_services)
        return {"success": True, "result": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Full restore failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Restore: database only ────────────────────────────────────────────────────

@router.post("/restore/database/{backup_id}")
async def restore_database(backup_id: str, db=Depends(get_db)):
    """Restore database from a backup (v1 or v2 format)."""
    _validate_backup_id(backup_id)
    try:
        mgr = BackupManager(db)
        mgr.restore_database(backup_id)
        return {"success": True, "message": f"Database restored from backup {backup_id}"}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Database restore failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Restore: single server ────────────────────────────────────────────────────

@router.post("/restore/server/{server_id}/{backup_id}")
async def restore_server(server_id: int, backup_id: str, db=Depends(get_db)):
    """Restore a server's clients and WG config from backup."""
    _validate_backup_id(backup_id)
    try:
        mgr = BackupManager(db)
        result = mgr.restore_server_from_backup(server_id, backup_id)
        return {"success": True, "result": result}
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Server restore failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{backup_id}")
async def delete_backup(backup_id: str, db=Depends(get_db)):
    """Delete a specific backup."""
    _validate_backup_id(backup_id)
    try:
        mgr = BackupManager(db)
        mgr.delete_backup(backup_id)
        return {"success": True, "message": f"Backup {backup_id} deleted"}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Backup deletion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Migrate ───────────────────────────────────────────────────────────────────

@router.post("/migrate")
async def migrate_server(req: MigrateRequest, db=Depends(get_db)):
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
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Server migration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
