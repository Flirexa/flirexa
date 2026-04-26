"""
VPN Management Studio — Update API Routes
Admin-only endpoints for managing system updates.

GET  /updates/status          — current version + available update
POST /updates/check           — force-check manifest server
GET  /updates/history         — update history list
GET  /updates/log/{id}        — full log for an update
GET  /updates/manifest/{ver}  — stored manifest JSON for a version
POST /updates/apply           — start update (background)
GET  /updates/progress/{id}   — update/rollback progress (poll every 2s)
POST /updates/rollback/{id}   — rollback a completed update
GET  /updates/channel         — current update channel
POST /updates/channel         — set update channel (stable | test)
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import UpdateHistory, UpdateStatus
from src.modules.updates.checker import check_for_update, _parse_version, is_newer
from src.modules.updates.manager import (
    apply_update,
    rollback_update,
    get_progress,
    get_current_version,
    get_active_update_id,
    reconcile_inflight_updates,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_INSTALL_DIR = Path(os.getenv("INSTALL_DIR", "/opt/vpnmanager"))
if not _INSTALL_DIR.exists():
    _INSTALL_DIR = Path(__file__).resolve().parents[3]  # src/api/routes/updates.py → project root
_RESTART_FLAG = _INSTALL_DIR / "data" / "restart_pending"
_STALE_PROGRESS_MINUTES = int(os.getenv("UPDATE_PROGRESS_STALE_MINUTES", "30"))

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_channel(db: Session) -> str:
    from src.database.models import SystemConfig
    cfg = db.query(SystemConfig).filter_by(key="update_channel").first()
    return cfg.value if cfg else "stable"


def _history_to_dict(rec: UpdateHistory) -> dict:
    return {
        "id":                 rec.id,
        "from_version":       rec.from_version,
        "to_version":         rec.to_version,
        "update_type":        rec.update_type,
        "status":             rec.status.value if rec.status else rec.status,
        "started_at":         rec.started_at.isoformat() if rec.started_at else None,
        "completed_at":       rec.completed_at.isoformat() if rec.completed_at else None,
        "duration_seconds":   rec.duration_seconds,
        "started_by":         rec.started_by,
        "rollback_available": rec.rollback_available,
        "backup_path_exists": _backup_exists(rec),
        "is_rollback":        rec.is_rollback,
        "rollback_of_id":     rec.rollback_of_id,
        "error_message":      rec.error_message,
        "has_log":            bool(rec.log),
        "channel":            rec.channel,
        "last_step":          rec.last_step,
        "staging_path":       rec.staging_path,
        "package_path":       rec.package_path,
    }


def _backup_exists(rec: UpdateHistory) -> bool:
    """Check whether the backup files for this record are still on disk."""
    if not rec.rollback_available or not rec.backup_path:
        return False
    backup_dir = Path(rec.backup_path)
    return backup_dir.exists() and (backup_dir / "code.tar.gz").exists()


def _get_active_in_db(db: Session) -> Optional[UpdateHistory]:
    """Return any update record that is in a running state in the DB."""
    active_status_names = [
        UpdateStatus.DOWNLOADING.name,
        UpdateStatus.DOWNLOADED.name,
        UpdateStatus.VERIFIED.name,
        UpdateStatus.READY_TO_APPLY.name,
        UpdateStatus.APPLYING.name,
        UpdateStatus.ROLLING_BACK.name,
    ]
    return (
        db.query(UpdateHistory)
        .filter(cast(UpdateHistory.status, String).in_(active_status_names))
        .first()
    )


def _mark_stale_progress_failed(rec: UpdateHistory, db: Session) -> bool:
    """
    Fail a non-terminal update if it has been stale for too long and no
    detached apply script appears to still be alive.
    """
    if rec.status not in (
        UpdateStatus.PENDING,
        UpdateStatus.DOWNLOADING,
        UpdateStatus.DOWNLOADED,
        UpdateStatus.VERIFIED,
        UpdateStatus.READY_TO_APPLY,
        UpdateStatus.APPLYING,
        UpdateStatus.ROLLING_BACK,
    ):
        return False

    started = rec.started_at
    if not started:
        return False
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if now - started < timedelta(minutes=_STALE_PROGRESS_MINUTES):
        return False

    if rec.backup_path:
        backup_dir = Path(rec.backup_path)
        code_file = backup_dir / "apply.exitcode"
        pid_file = backup_dir / "apply.pid"
        if code_file.exists():
            return False
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)
                return False
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                pass

    rec.status = UpdateStatus.FAILED
    rec.error_message = (
        f"Update progress stale for more than {_STALE_PROGRESS_MINUTES} minutes — "
        "marked failed automatically"
    )
    rec.completed_at = now
    rec.duration_seconds = (now - started).total_seconds()
    db.commit()
    db.refresh(rec)
    logger.warning("Marked stale update record %s as FAILED", rec.id)
    return True


# ── GET /updates/status ────────────────────────────────────────────────────────

@router.get("/status")
async def update_status(db: Session = Depends(get_db)):
    """Returns current version, available update (if any), and last update info."""
    reconcile_inflight_updates()
    current = get_current_version()
    channel = _get_channel(db)

    available_manifest, check_error = await check_for_update(current, channel, force=False)

    last_record = (
        db.query(UpdateHistory)
        .filter(UpdateHistory.is_rollback == False)  # noqa: E712
        .order_by(UpdateHistory.started_at.desc())
        .first()
    )

    last_success = (
        db.query(UpdateHistory)
        .filter(
            UpdateHistory.is_rollback == False,  # noqa: E712
            UpdateHistory.status == UpdateStatus.SUCCESS,
        )
        .order_by(UpdateHistory.completed_at.desc())
        .first()
    )

    active_id = get_active_update_id()

    return {
        "current_version":  current,
        "channel":          channel,
        "available_update": {
            "version":            available_manifest["version"],
            "update_type":        available_manifest.get("update_type"),
            "changelog":          available_manifest.get("release_notes", available_manifest.get("changelog", "")),
            "has_db_migrations":  available_manifest.get("requires_migration", available_manifest.get("has_db_migrations", False)),
            "rollback_supported": available_manifest.get("rollback_supported", True),
            "release_date":       available_manifest.get("published_at", available_manifest.get("release_date")),
            "requires_restart":   available_manifest.get("requires_restart", True),
        } if available_manifest else None,
        "check_error":        check_error,
        "last_update_at":     last_success.completed_at.isoformat() if last_success and last_success.completed_at else None,
        "update_in_progress": active_id is not None,
        "active_update_id":   active_id,
        "last_record":        _history_to_dict(last_record) if last_record else None,
        "restart_pending":    _RESTART_FLAG.exists(),
    }


# ── POST /updates/check ────────────────────────────────────────────────────────

@router.post("/check")
async def check_updates(db: Session = Depends(get_db)):
    """Force-refresh check against manifest server."""
    current = get_current_version()
    channel = _get_channel(db)

    manifest, error = await check_for_update(current, channel, force=True)

    return {
        "current_version":  current,
        "channel":          channel,
        "available_update": {
            "version":            manifest["version"],
            "update_type":        manifest.get("update_type"),
            "changelog":          manifest.get("release_notes", manifest.get("changelog", "")),
            "has_db_migrations":  manifest.get("requires_migration", manifest.get("has_db_migrations", False)),
            "rollback_supported": manifest.get("rollback_supported", True),
            "release_date":       manifest.get("published_at", manifest.get("release_date")),
            "requires_restart":   manifest.get("requires_restart", True),
        } if manifest else None,
        "error":      error,
        "up_to_date": manifest is None and error is None,
    }


# ── GET /updates/history ───────────────────────────────────────────────────────

@router.get("/history")
async def update_history(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Return list of past update/rollback operations."""
    reconcile_inflight_updates()
    records = (
        db.query(UpdateHistory)
        .order_by(UpdateHistory.started_at.desc())
        .limit(limit)
        .all()
    )
    return {"history": [_history_to_dict(r) for r in records], "total": len(records)}


# ── GET /updates/log/{id} ─────────────────────────────────────────────────────

@router.get("/log/{update_id}")
async def update_log(update_id: int, db: Session = Depends(get_db)):
    """Return full log of an update operation."""
    rec = db.get(UpdateHistory, update_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Update record not found")
    return {"id": update_id, "log": rec.log or ""}


# ── GET /updates/manifest/{version} ───────────────────────────────────────────

@router.get("/manifest/{version}")
async def get_manifest(version: str, db: Session = Depends(get_db)):
    """Return the stored manifest JSON for a specific update version."""
    rec = (
        db.query(UpdateHistory)
        .filter(UpdateHistory.to_version == version)
        .order_by(UpdateHistory.started_at.desc())
        .first()
    )
    if not rec or not rec.manifest_json:
        raise HTTPException(status_code=404, detail=f"No manifest stored for version {version}")
    return json.loads(rec.manifest_json)


# ── POST /updates/apply ────────────────────────────────────────────────────────

class ApplyRequest(BaseModel):
    version: Optional[str] = None   # if None → apply available update


@router.post("/apply")
async def apply_update_endpoint(
    req: ApplyRequest = ApplyRequest(),
    db: Session = Depends(get_db),
):
    """Start update process. Returns immediately; poll /progress/{id} for status."""
    reconcile_inflight_updates()

    # Guard 1: in-memory active update check (fast path)
    active_id = get_active_update_id()
    if active_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Update #{active_id} is already in progress",
        )

    # Guard 2: DB-level check (catches orphaned records after unexpected restart
    # before cleanup_orphaned_updates runs, and race conditions between workers)
    active_db = _get_active_in_db(db)
    if active_db:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Update #{active_db.id} is already in progress "
                f"(db status: {active_db.status.value})"
            ),
        )

    current = get_current_version()
    channel = _get_channel(db)

    manifest, error = await check_for_update(current, channel, force=True)
    if error:
        raise HTTPException(status_code=400, detail=f"Cannot check for updates: {error}")
    if manifest is None:
        raise HTTPException(status_code=400, detail="No update available — already up to date")

    # Guard 3: version must be strictly newer (prevent downgrade / same-version re-apply)
    if not is_newer(manifest["version"], current):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Version {manifest['version']} is not newer than current {current} "
                "— update rejected"
            ),
        )

    # Guard 4: version compatibility
    min_ver = manifest.get("minimum_supported_version", "0.0.0")
    if _parse_version(current) < _parse_version(min_ver):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Update {manifest['version']} requires minimum version {min_ver}, "
                f"but current version is {current}"
            ),
        )

    # Guard 5: explicit version match if caller specified one
    if req.version and manifest["version"] != req.version:
        raise HTTPException(
            status_code=400,
            detail=f"Requested version {req.version} differs from available {manifest['version']}",
        )

    update_id = await apply_update(manifest, started_by="admin", db=db)
    logger.info("Update started: id=%d %s→%s", update_id, current, manifest["version"])

    return {
        "update_id":    update_id,
        "status":       "in_progress",
        "from_version": current,
        "to_version":   manifest["version"],
    }


# ── GET /updates/progress/{id} ────────────────────────────────────────────────

@router.get("/progress/{update_id}")
async def update_progress(update_id: int, db: Session = Depends(get_db)):
    """Poll update/rollback progress. Returns live dict or DB record if completed."""
    reconcile_inflight_updates()
    progress = get_progress(update_id)
    if progress:
        return progress

    # Not in memory — load from DB (update completed or API was restarted during apply)
    rec = db.get(UpdateHistory, update_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Update not found")
    _mark_stale_progress_failed(rec, db)

    # Map DB status to a consistent response shape
    status_val = rec.status.value if rec.status else "unknown"
    is_terminal = rec.status in (
        UpdateStatus.SUCCESS, UpdateStatus.FAILED, UpdateStatus.ROLLED_BACK
    )

    # For non-terminal records (API restarted during apply): try to read live apply.log
    log_lines = rec.log.splitlines() if rec.log else []
    if not is_terminal and rec.backup_path:
        from pathlib import Path
        apply_log = Path(rec.backup_path) / "apply.log"
        if apply_log.exists():
            try:
                log_lines = apply_log.read_text(errors="replace").splitlines()
            except Exception:
                pass

    return {
        "update_id":   update_id,
        "status":      status_val,
        "step_number": 11 if is_terminal else None,
        "step":        "Completed" if rec.status == UpdateStatus.SUCCESS else status_val,
        "total_steps": 11,
        "log":         log_lines,
        "started_at":  rec.started_at.isoformat() if rec.started_at else None,
        "error":       rec.error_message,
        "from_db":     True,   # hint to frontend that this is a historical record
        "last_step":   rec.last_step,
    }


# ── POST /updates/rollback/{id} ────────────────────────────────────────────────

@router.post("/rollback/{update_id}")
async def rollback_update_endpoint(update_id: int, db: Session = Depends(get_db)):
    """Roll back a completed update using its pre-update backup."""
    reconcile_inflight_updates()

    # Guard 1: no active update
    active_id = get_active_update_id()
    if active_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Update #{active_id} is already in progress — cannot start rollback",
        )

    # Guard 2: DB-level check
    active_db = _get_active_in_db(db)
    if active_db:
        raise HTTPException(
            status_code=409,
            detail=f"Update #{active_db.id} is in progress (db) — cannot start rollback",
        )

    rec = db.get(UpdateHistory, update_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Update not found")

    if not rec.rollback_available:
        raise HTTPException(
            status_code=400,
            detail="Rollback not available for this update (backup not recorded or already used)",
        )

    # Guard 3: verify backup files exist on disk before even trying
    if rec.backup_path:
        backup_dir = Path(rec.backup_path)
        if not backup_dir.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Rollback backup directory not found on disk: {rec.backup_path}",
            )
        if not (backup_dir / "code.tar.gz").exists():
            raise HTTPException(
                status_code=400,
                detail=f"Rollback backup archive missing: {rec.backup_path}/code.tar.gz",
            )
    else:
        raise HTTPException(status_code=400, detail="No backup path recorded for this update")

    try:
        rollback_id = await rollback_update(update_id, started_by="admin")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "rollback_id":  rollback_id,
        "status":       "in_progress",
        "from_version": rec.to_version,
        "to_version":   rec.from_version,
    }


# ── GET /updates/channel ──────────────────────────────────────────────────────

@router.get("/channel")
async def get_update_channel(db: Session = Depends(get_db)):
    return {"channel": _get_channel(db)}


class ChannelRequest(BaseModel):
    channel: str   # stable | test


@router.post("/channel")
async def set_update_channel(req: ChannelRequest, db: Session = Depends(get_db)):
    if req.channel not in ("stable", "test"):
        raise HTTPException(status_code=400, detail="channel must be 'stable' or 'test'")
    from src.database.models import SystemConfig
    cfg = db.query(SystemConfig).filter_by(key="update_channel").first()
    if cfg:
        cfg.value = req.channel
    else:
        db.add(SystemConfig(key="update_channel", value=req.channel, value_type="string"))
    db.commit()
    from src.modules.updates.checker import invalidate_cache
    invalidate_cache()   # force re-fetch from new channel
    logger.info("Update channel changed to: %s", req.channel)
    return {"channel": req.channel}


# ── POST /updates/restart ──────────────────────────────────────────────────────

def _detect_service_prefix() -> str:
    """Detect systemd service prefix (vpnmanager / spongebot) from .env or unit files."""
    env_file = _INSTALL_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            for key in ("API_SERVICE=", "ADMIN_BOT_SERVICE="):
                if line.startswith(key):
                    val = line[len(key):].strip().strip("'\"")
                    val = val.removesuffix("-api").removesuffix("-admin-bot")
                    if val:
                        return val
    # fallback: check systemd unit files
    try:
        out = subprocess.check_output(["systemctl", "list-unit-files"], text=True, timeout=5)
        if "vpnmanager-api" in out:
            return "vpnmanager"
        if "spongebot-api" in out:
            return "spongebot"
    except Exception:
        pass
    return "vpnmanager"


@router.post("/restart")
async def restart_services():
    """
    Trigger a service restart to apply the last update.
    Spawns a detached bash process (sleep 2 + systemctl restart) and returns
    immediately so the HTTP response reaches the client before the API restarts.
    """
    prefix = _detect_service_prefix()
    services = [
        f"{prefix}-api",
        f"{prefix}-worker",
        f"{prefix}-admin-bot",
        f"{prefix}-client-bot",
        f"{prefix}-client-portal",
    ]
    cmd = "sleep 2 && systemctl restart " + " ".join(services)
    subprocess.Popen(
        ["bash", "-c", cmd],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("Restart triggered for services: %s", ", ".join(services))
    return {"message": "Restart initiated", "services": services}
