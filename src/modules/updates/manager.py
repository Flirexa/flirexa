"""
Update Manager — orchestrates the full update / rollback lifecycle.

Flow:
  check_for_update() → apply_update(manifest) → [rollback_update(history_id)]

apply_update():
  1. Preflight: disk space check
  2. Download package
  3. Verify SHA-256
  4. Create DB record (DOWNLOADING)
  5. Create pre-update backup
  6. Call update_apply.sh  (stops services, applies files, runs migrations, restarts, smoke-checks)
  7. On success → update DB record (SUCCESS), write VERSION file
  8. On failure → DB record (FAILED), optionally rollback from backup

Progress is stored in a module-level dict and polled via GET /updates/progress/{id}.
After API restart, in-progress records are cleaned up by cleanup_orphaned_updates().
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy import String, cast

from .checker import verify_package_checksum, check_for_update, invalidate_cache
from src.utils.runtime_paths import (
    get_current_link,
    get_install_root,
    get_releases_root,
    get_version_file,
)

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

_INSTALL_DIR   = get_install_root("/opt/vpnmanager")
_APPLY_SCRIPT  = Path(__file__).resolve().parent.parent.parent.parent / "update_apply.sh"
_VERSION_FILE  = Path(os.getenv("VERSION_FILE", str(get_version_file(_INSTALL_DIR))))
_BACKUP_BASE   = _INSTALL_DIR / "backups" / "update_backups"
_STAGING_BASE  = _INSTALL_DIR / "staging"
_RELEASES_DIR  = get_releases_root(_INSTALL_DIR)
_CURRENT_LINK  = get_current_link(_INSTALL_DIR)
_DOWNLOAD_DIR  = _STAGING_BASE  # retained name for compatibility in some helpers

# Development fallback — use the repo root as install dir
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if not _INSTALL_DIR.exists():
    _INSTALL_DIR  = _REPO_ROOT
    _VERSION_FILE = get_version_file(_REPO_ROOT)
    _BACKUP_BASE  = _REPO_ROOT / "backups" / "update_backups"
    _STAGING_BASE = _REPO_ROOT / "staging"
    _RELEASES_DIR = get_releases_root(_REPO_ROOT)
    _CURRENT_LINK = get_current_link(_REPO_ROOT)
    _APPLY_SCRIPT = _REPO_ROOT / "update_apply.sh"

# ── Disk space constants ───────────────────────────────────────────────────────
# These mirror MIN_UPDATE_FREE_MB in update_apply.sh.
_MIN_DOWNLOAD_MB = 200   # free space needed in /tmp for package download
_MIN_BACKUP_MB   = 500   # free space needed for code backup + DB dump
_MAX_STAGING_AGE_HOURS = int(os.getenv("UPDATE_STAGING_MAX_AGE_HOURS", "24"))
_UPDATE_BACKUP_KEEP_COUNT = int(os.getenv("UPDATE_BACKUP_KEEP_COUNT", "5"))
_UPDATE_BACKUP_KEEP_DAYS = int(os.getenv("UPDATE_BACKUP_KEEP_DAYS", "14"))


# ── In-memory progress ─────────────────────────────────────────────────────────

# update_id → progress_dict
_progress: dict[int, dict] = {}

STEPS = [
    "Downloading package",        # 1
    "Verifying checksum",         # 2
    "Extracting package",         # 3
    "Preparing apply",            # 4
    "Creating backup",            # 5
    "Applying release",           # 6
    "Running DB migrations",      # 7
    "Restarting services",        # 8
    "Running health checks",      # 9
    "Auto rollback",              # 10
    "Finalising",                 # 11
]


def _progress_update(update_id: int, step_number: int, message: str, log_line: str = ""):
    p = _progress.get(update_id)
    if p is None:
        return
    p["step_number"] = step_number
    p["step"] = STEPS[step_number - 1] if 1 <= step_number <= len(STEPS) else message
    p["heartbeat_at"] = datetime.now(timezone.utc).isoformat()
    if log_line:
        p["log"].append(log_line)
    logger.info("[UPDATE %d] S%d %s", update_id, step_number, message)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _write_marker(base: Path, name: str, value: str = ""):
    base.mkdir(parents=True, exist_ok=True)
    (base / name).write_text(value)


def _read_marker(base: Path, name: str) -> Optional[str]:
    path = base / name
    if not path.exists():
        return None
    return path.read_text(errors="replace")


def _cleanup_staging_dir(path: Path):
    try:
        if path.exists():
            shutil.rmtree(path)
    except Exception:
        logger.warning("Could not clean staging dir: %s", path)


def _cleanup_update_artifacts(now: Optional[datetime] = None) -> dict[str, int]:
    """
    Retain only a bounded set of old update backups and stale staging dirs.

    Safety rules:
    - keep recent successful/failed update backups for rollback/debug
    - never delete backups for in-flight updates
    - when a retained update backup is removed, clear rollback_available/backup_path
      on the corresponding UpdateHistory row so the UI/API stay truthful
    - remove only stale staging dirs older than UPDATE_STAGING_MAX_AGE_HOURS
    """
    from src.database.connection import SessionLocal
    from src.database.models import UpdateHistory, UpdateStatus

    now = now or datetime.now(timezone.utc)
    result = {
        "deleted_update_backups": 0,
        "trimmed_update_records": 0,
        "deleted_staging_dirs": 0,
    }

    # Cleanup stale staging dirs regardless of DB state if they are old enough and
    # do not belong to an in-flight update record.
    active_staging_paths: set[Path] = set()
    db = SessionLocal()
    try:
        in_flight = (
            db.query(UpdateHistory)
            .filter(cast(UpdateHistory.status, String).in_([
                UpdateStatus.PENDING.name,
                UpdateStatus.DOWNLOADING.name,
                UpdateStatus.DOWNLOADED.name,
                UpdateStatus.VERIFIED.name,
                UpdateStatus.READY_TO_APPLY.name,
                UpdateStatus.APPLYING.name,
                UpdateStatus.ROLLING_BACK.name,
            ]))
            .all()
        )
        for rec in in_flight:
            if rec.staging_path:
                active_staging_paths.add(Path(rec.staging_path))

        if _STAGING_BASE.exists():
            cutoff_seconds = max(_MAX_STAGING_AGE_HOURS, 1) * 3600
            for entry in _STAGING_BASE.iterdir():
                if not entry.is_dir() or entry in active_staging_paths:
                    continue
                try:
                    age_seconds = now.timestamp() - entry.stat().st_mtime
                except OSError:
                    continue
                if age_seconds < cutoff_seconds:
                    continue
                _cleanup_staging_dir(entry)
                result["deleted_staging_dirs"] += 1

        terminal_statuses = [
            UpdateStatus.SUCCESS.name,
            UpdateStatus.FAILED.name,
            UpdateStatus.ROLLED_BACK.name,
            UpdateStatus.ROLLBACK_REQUIRED.name,
        ]
        candidates = (
            db.query(UpdateHistory)
            .filter(UpdateHistory.is_rollback.is_(False))
            .filter(UpdateHistory.backup_path.isnot(None))
            .filter(cast(UpdateHistory.status, String).in_(terminal_statuses))
            .order_by(UpdateHistory.completed_at.desc(), UpdateHistory.id.desc())
            .all()
        )

        keep_count = max(_UPDATE_BACKUP_KEEP_COUNT, 1)
        keep_days = max(_UPDATE_BACKUP_KEEP_DAYS, 1)
        cutoff = now.timestamp() - keep_days * 86400

        to_delete = []
        kept = 0
        for rec in candidates:
            backup_path = Path(rec.backup_path) if rec.backup_path else None
            if not backup_path:
                continue
            try:
                backup_ts = backup_path.stat().st_mtime if backup_path.exists() else 0
            except OSError:
                backup_ts = 0

            must_keep = kept < keep_count and backup_path.exists()
            too_old = backup_ts and backup_ts < cutoff
            if must_keep and not too_old:
                kept += 1
                continue
            if backup_path.exists():
                to_delete.append((rec, backup_path))
            else:
                rec.rollback_available = False
                rec.backup_path = None
                result["trimmed_update_records"] += 1

        for rec, backup_path in to_delete:
            shutil.rmtree(backup_path, ignore_errors=True)
            rec.rollback_available = False
            rec.backup_path = None
            result["deleted_update_backups"] += 1
            result["trimmed_update_records"] += 1

        if any(result.values()):
            db.commit()
            logger.info(
                "Update artifact cleanup: backups=%d records=%d staging=%d",
                result["deleted_update_backups"],
                result["trimmed_update_records"],
                result["deleted_staging_dirs"],
            )
        else:
            db.rollback()
    except Exception:
        db.rollback()
        logger.exception("Could not clean old update artifacts")
    finally:
        db.close()

    return result


def _validate_extracted_release(extract_root: Path, expected_version: str) -> Optional[str]:
    required = ["VERSION", "requirements.txt", "alembic.ini", "src"]
    missing = [name for name in required if not (extract_root / name).exists()]
    if missing:
        return f"Extracted release missing required files: {missing}"
    try:
        extracted_version = (extract_root / "VERSION").read_text().strip()
    except Exception as exc:
        return f"Could not read extracted VERSION: {exc}"
    if extracted_version != expected_version:
        return (
            f"Extracted VERSION mismatch: expected {expected_version}, "
            f"got {extracted_version}"
        )
    return None


# ── VERSION helpers ────────────────────────────────────────────────────────────

def get_current_version() -> str:
    """Read VERSION file. Returns '0.0.0' if not found."""
    try:
        return _VERSION_FILE.read_text().strip()
    except Exception:
        return "0.0.0"


def _write_version(version: str):
    _VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _VERSION_FILE.write_text(version + "\n")


# ── Disk space check ──────────────────────────────────────────────────────────

def _check_disk_space(path: Path, required_mb: int) -> Optional[str]:
    """
    Check if a directory has enough free disk space.
    Returns an error string if insufficient, None if OK.
    Silently passes if disk usage cannot be determined (don't block update).
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(path)
        available_mb = usage.free // (1024 * 1024)
        if available_mb < required_mb:
            return (
                f"Insufficient disk space at {path}: "
                f"{available_mb}MB available, {required_mb}MB required"
            )
        logger.debug("Disk space OK at %s: %dMB available", path, available_mb)
        return None
    except Exception as e:
        logger.warning("Could not check disk space at %s: %s", path, e)
        return None   # don't block the update if we can't check


# ── Startup orphan cleanup ─────────────────────────────────────────────────────

def _resolve_orphan(rec, now) -> str:
    """
    Try to determine the real outcome of an interrupted update/rollback by
    reading the apply.exitcode file written by update_apply.sh.

    Returns "resolved" if we successfully determined and saved the outcome,
    "running"  if the apply script is still in progress (don't touch),
    "unknown"  if we can't determine outcome (will be marked FAILED).
    """
    from src.database.models import UpdateStatus

    state_dir = None
    if rec.backup_path:
        state_dir = Path(rec.backup_path)
    elif rec.staging_path:
        state_dir = Path(rec.staging_path)
    if not state_dir:
        return "unknown"

    code_file   = state_dir / "apply.exitcode"
    pid_file    = state_dir / "apply.pid"
    log_file    = state_dir / "apply.log"
    marker_migration_started = state_dir / "phase_migration_started"
    marker_migration_complete = state_dir / "phase_migration_complete"
    marker_switch = state_dir / "phase_symlink_switched"
    marker_health = state_dir / "phase_health_ok"
    rollback_pid = state_dir / "rollback.pid"
    rollback_complete = state_dir / "phase_rollback_complete"

    # Check if the script is still running
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # 0 = just check existence
            logger.info("Update %d: apply script PID %d still running", rec.id, pid)
            return "running"
        except (ValueError, ProcessLookupError, PermissionError):
            pass  # Process dead — check exit code file

    # Check if the script wrote its exit code
    if code_file.exists():
        try:
            rc = int(code_file.read_text().strip())
            log_output = log_file.read_text() if log_file.exists() else ""
            started = rec.started_at
            if started and started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            rec.completed_at    = now
            rec.duration_seconds = (now - started).total_seconds() if started else None
            rec.log              = log_output
            if rc == 0:
                rec.status           = UpdateStatus.SUCCESS
                rec.rollback_available = bool(log_file.exists())
                logger.info("Update %d resolved as SUCCESS (exitcode=0)", rec.id)
            elif rc == 2:
                rec.status        = UpdateStatus.FAILED
                rec.error_message = "update_apply.sh failed — auto-rollback was attempted"
                logger.warning("Update %d resolved as FAILED with auto-rollback (exitcode=2)", rec.id)
            else:
                rec.status        = UpdateStatus.FAILED
                rec.error_message = f"update_apply.sh exited with code {rc}"
                logger.warning("Update %d resolved as FAILED (exitcode=%d)", rec.id, rc)
            return "resolved"
        except (ValueError, OSError) as e:
            logger.warning("Update %d: could not read exitcode file: %s", rec.id, e)

    if rollback_pid.exists() and not rollback_complete.exists():
        return "unknown"

    # Crash after migration or after code switch is more severe than a generic failure.
    if marker_migration_started.exists() or marker_migration_complete.exists() or marker_switch.exists():
        if marker_health.exists():
            rec.status = UpdateStatus.SUCCESS
            rec.completed_at = now
            return "resolved"
        rec.status = UpdateStatus.ROLLBACK_REQUIRED
        rec.error_message = (
            "Update interrupted after migration/switch phase — automatic recovery "
            "could not determine a clean outcome"
        )
        rec.completed_at = now
        if not rec.duration_seconds and rec.started_at:
            started = rec.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            rec.duration_seconds = (now - started).total_seconds()
        return "resolved"

    return "unknown"


def reconcile_inflight_updates() -> int:
    """
    Resolve or mark PENDING/DOWNLOADING/APPLYING/ROLLING_BACK records.

    This is safe to call both:
    - on API startup
    - on-demand from update routes after the API has already restarted once

    Returns the number of records processed (resolved or failed).
    """
    from src.database.models import UpdateHistory, UpdateStatus
    from src.database.connection import SessionLocal

    db = SessionLocal()
    try:
        in_flight_statuses = [
            UpdateStatus.PENDING.name,
            UpdateStatus.DOWNLOADING.name,
            UpdateStatus.DOWNLOADED.name,
            UpdateStatus.VERIFIED.name,
            UpdateStatus.READY_TO_APPLY.name,
            UpdateStatus.APPLYING.name,
            UpdateStatus.ROLLING_BACK.name,
        ]
        orphaned = (
            db.query(UpdateHistory)
            .filter(cast(UpdateHistory.status, String).in_(in_flight_statuses))
            .all()
        )
        now = datetime.now(timezone.utc)
        resolved = []
        still_running = []
        failed = []

        for rec in orphaned:
            outcome = _resolve_orphan(rec, now)
            if outcome == "resolved":
                resolved.append(rec.id)
            elif outcome == "running":
                still_running.append(rec.id)
            else:
                rec.status        = UpdateStatus.FAILED
                rec.error_message = (
                    "Server restarted during update — outcome unknown. "
                    "Check system state manually; use rollback if needed."
                )
                rec.completed_at  = now
                if not rec.duration_seconds and rec.started_at:
                    started = rec.started_at
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    rec.duration_seconds = (now - started).total_seconds()
                failed.append(rec.id)

        if resolved or failed:
            db.commit()

        if resolved:
            logger.info("Resolved %d update record(s) from exitcode files: %s", len(resolved), resolved)
        if still_running:
            logger.info("Update(s) still in progress (script running): %s", still_running)
        if failed:
            logger.warning("Marked %d orphaned update record(s) as FAILED: %s", len(failed), failed)

        return len(resolved) + len(failed)
    except Exception as e:
        logger.error("Could not cleanup orphaned updates: %s", e)
        return 0
    finally:
        db.close()


def cleanup_orphaned_updates() -> int:
    """
    Backward-compatible startup hook.
    """
    processed = reconcile_inflight_updates()
    _cleanup_update_artifacts()
    return processed


# ── Download ───────────────────────────────────────────────────────────────────

async def _download_package(url: str, dest: Path) -> Optional[str]:
    """
    Stream-download the update package to dest.

    package_url comes from the signed manifest so it cannot be injected.
    Returns None on success, error string on failure.
    Partial downloads are cleaned up by the caller (finally block in task).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {}
    license_key = os.getenv("LICENSE_KEY", "").strip()
    if license_key:
        headers["X-License-Key"] = license_key
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=15)) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.status_code == 404:
                    return "Package not found on update server"
                if resp.status_code == 403:
                    return "Package download rejected — license key required or invalid"
                if resp.status_code != 200:
                    return f"Download failed: HTTP {resp.status_code}"
                with open(dest, "wb") as f:
                    async for chunk in resp.aiter_bytes(65536):
                        f.write(chunk)
        return None
    except httpx.TimeoutException:
        return "Package download timeout — package may be too large or network is slow"
    except httpx.ConnectError:
        return "Cannot connect to update server for download"
    except Exception as e:
        return f"Download error: {type(e).__name__}: {e}"


# ── Apply script ───────────────────────────────────────────────────────────────

def _run_apply_script(
    package_path: Path,
    backup_dir: Path,
    install_dir: Path,
    update_id: int,
    staging_dir: Optional[Path] = None,
    target_version: str = "",
    expected_package_sha: str = "",
    expected_package_size: int = 0,
    expected_min_version: str = "",
    requires_migration: bool = False,
    requires_restart: bool = True,
) -> tuple[int, str]:
    """
    Run update_apply.sh in a new session so it survives the API service restart.

    update_apply.sh stops the API service (systemctl stop spongebot-api / vpnmanager-api).
    Without start_new_session=True the script is in the same process group as the API,
    so systemd's SIGTERM kills it too (exit code -15). With a new session the script
    is detached and continues running even after the API process dies.

    Progress is written to backup_dir/apply.log.
    The script writes its exit code to backup_dir/apply.exitcode when it finishes.
    cleanup_orphaned_updates() reads these files on the next API startup.
    """
    if not _APPLY_SCRIPT.exists():
        return 1, f"update_apply.sh not found at {_APPLY_SCRIPT}"

    log_file  = backup_dir / "apply.log"
    pid_file  = backup_dir / "apply.pid"
    code_file = backup_dir / "apply.exitcode"

    # Remove stale exitcode from any previous attempt so cleanup won't misread it
    code_file.unlink(missing_ok=True)

    env = os.environ.copy()
    env["UPDATE_PACKAGE"] = str(package_path)
    env["BACKUP_DIR"]     = str(backup_dir)
    env["INSTALL_DIR"]    = str(install_dir)
    env["UPDATE_ID"]      = str(update_id)
    env["STAGING_DIR"]    = str(staging_dir or package_path.parent)
    env["TARGET_VERSION"] = target_version
    env["EXPECTED_PACKAGE_SHA256"] = expected_package_sha
    env["EXPECTED_PACKAGE_SIZE"] = str(expected_package_size or 0)
    env["EXPECTED_MIN_VERSION"] = expected_min_version
    env["REQUIRES_MIGRATION"] = "true" if requires_migration else "false"
    env["REQUIRES_RESTART"] = "true" if requires_restart else "false"

    backup_dir.mkdir(parents=True, exist_ok=True)
    with open(log_file, "w") as logf:
        proc = subprocess.Popen(
            ["bash", str(_APPLY_SCRIPT)],
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,   # ← detach from API process group (SIGTERM safety)
        )
    pid_file.write_text(str(proc.pid))
    logger.info("[UPDATE %d] apply script started, PID=%d session-detached", update_id, proc.pid)

    try:
        rc = proc.wait(timeout=600)
    except subprocess.TimeoutExpired:
        logger.error("[UPDATE %d] update_apply.sh timeout (600s) — killing PID %d", update_id, proc.pid)
        proc.kill()
        rc = 1
    except Exception as exc:
        # This thread may be interrupted if the Python process is shutting down.
        # The script continues running independently; cleanup_orphaned_updates()
        # will resolve the outcome on the next startup via apply.exitcode.
        logger.warning("[UPDATE %d] wait() interrupted (%s) — script may still be running", update_id, exc)
        _poll = proc.poll()
        rc = _poll if _poll is not None else -15

    # Prefer the exit code written by the script itself (more reliable than proc.returncode
    # when Python was restarted mid-wait)
    if code_file.exists():
        try:
            rc = int(code_file.read_text().strip())
        except (ValueError, OSError):
            pass

    output = log_file.read_text() if log_file.exists() else ""
    return rc, output


def _run_rollback_script(backup_dir: Path, install_dir: Path) -> tuple[int, str]:
    """Run update_apply.sh with ROLLBACK=1 env var."""
    if not _APPLY_SCRIPT.exists():
        return 1, "update_apply.sh not found"

    env = os.environ.copy()
    env["ROLLBACK"]    = "1"
    env["BACKUP_DIR"]  = str(backup_dir)
    env["INSTALL_DIR"] = str(install_dir)

    result = subprocess.run(
        ["bash", str(_APPLY_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = result.stdout + ("\n" + result.stderr if result.stderr else "")
    return result.returncode, output


# ── Main: apply update ─────────────────────────────────────────────────────────

async def apply_update(
    manifest: dict,
    started_by: str = "admin",
    db=None,
) -> int:
    """
    Start the update process in the background.
    Returns update_id (UpdateHistory.id) immediately.
    """
    from src.database.models import UpdateHistory, UpdateStatus
    from src.database.connection import SessionLocal

    current_version = get_current_version()
    to_version      = manifest["version"]

    # Create DB record
    db_local = db or SessionLocal()
    try:
        record = UpdateHistory(
            from_version        = current_version,
            to_version          = to_version,
            channel             = manifest.get("channel"),
            update_type         = manifest.get("update_type"),
            status              = UpdateStatus.PENDING,
            started_by          = started_by,
            rollback_available  = False,
            manifest_json       = json.dumps(manifest, sort_keys=True),
            manifest_sha256     = _sha256_text(json.dumps(manifest, sort_keys=True)),
            package_sha256      = manifest.get("sha256") or manifest.get("package_sha256"),
            package_size        = manifest.get("package_size"),
            requires_migration  = bool(manifest.get("requires_migration", manifest.get("has_db_migrations", False))),
            requires_restart    = bool(manifest.get("requires_restart", True)),
            last_step           = "Initialising",
            progress_heartbeat_at = datetime.now(timezone.utc),
        )
        db_local.add(record)
        db_local.commit()
        db_local.refresh(record)
        update_id = record.id
    finally:
        if not db:
            db_local.close()

    # Init progress tracking
    _progress[update_id] = {
        "update_id":    update_id,
        "status":       "in_progress",
        "step_number":  0,
        "step":         "Initialising",
        "total_steps":  len(STEPS),
        "log":          [],
        "started_at":   datetime.now(timezone.utc).isoformat(),
        "error":        None,
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
    }

    asyncio.create_task(_apply_update_task(update_id, manifest, started_by))
    return update_id


async def _apply_update_task(update_id: int, manifest: dict, started_by: str):
    from src.database.models import UpdateHistory, UpdateStatus
    from src.database.connection import SessionLocal

    started_at   = time.monotonic()
    package_path: Optional[Path] = None
    backup_dir:   Optional[Path] = None
    staging_dir:  Optional[Path] = None
    extract_root: Optional[Path] = None
    log_lines:    list[str] = []

    def _log(msg: str):
        log_lines.append(msg)
        p = _progress.get(update_id)
        if p:
            p["log"].append(msg)

    def _db_update(**kwargs):
        s = SessionLocal()
        try:
            rec = s.get(UpdateHistory, update_id)
            if rec:
                kwargs.setdefault("progress_heartbeat_at", datetime.now(timezone.utc))
                for k, v in kwargs.items():
                    setattr(rec, k, v)
                s.commit()
        finally:
            s.close()

    def _set_status(status: UpdateStatus, error: str = None):
        duration = time.monotonic() - started_at
        _db_update(
            status           = status,
            completed_at     = datetime.now(timezone.utc),
            duration_seconds = duration,
            log              = "\n".join(log_lines),
            error_message    = error,
            last_step        = _progress.get(update_id, {}).get("step"),
        )
        p = _progress.get(update_id)
        if p:
            p["status"] = status.value
            if error:
                p["error"] = error

    try:
        to_version   = manifest["version"]
        package_url  = manifest["package_url"]
        expected_sha = manifest.get("sha256") or manifest.get("package_sha256")
        package_size = int(manifest.get("package_size") or 0)
        requires_migration = bool(manifest.get("requires_migration", manifest.get("has_db_migrations", False)))
        requires_restart = bool(manifest.get("requires_restart", True))
        min_supported_version = manifest.get("min_supported_version", manifest.get("minimum_supported_version", "0.0.0"))

        _log(f"Starting update {get_current_version()} → {to_version}")
        logger.info(f"EVENT:UPDATE_START {get_current_version()} → {to_version} (id={update_id})")
        _db_update(status=UpdateStatus.DOWNLOADING)

        # ── Preflight: disk space ──────────────────────────────────────────────
        _log("Checking disk space …")
        dl_err = _check_disk_space(_DOWNLOAD_DIR, _MIN_DOWNLOAD_MB)
        if dl_err:
            _log(f"ERROR: {dl_err}")
            _set_status(UpdateStatus.FAILED, dl_err)
            return
        backup_parent = _BACKUP_BASE.parent
        bk_err = _check_disk_space(backup_parent, _MIN_BACKUP_MB)
        if bk_err:
            _log(f"ERROR: {bk_err}")
            _set_status(UpdateStatus.FAILED, bk_err)
            return
        _log("Disk space OK")

        # ── Step 1: Download ───────────────────────────────────────────────────
        _progress_update(update_id, 1, "Downloading package")
        _log("Downloading update package…")
        staging_dir = _STAGING_BASE / f"update_{update_id}"
        staging_dir.mkdir(parents=True, exist_ok=True)
        _write_marker(staging_dir, "manifest.json", json.dumps(manifest, indent=2))
        filename = package_url.split("/")[-1]
        package_path = staging_dir / "package.tar.gz"
        _db_update(
            staging_path=str(staging_dir),
            package_path=str(package_path),
            package_sha256=expected_sha,
            package_size=package_size,
            requires_migration=requires_migration,
            requires_restart=requires_restart,
            last_step="Downloading package",
        )

        err = await _download_package(package_url, package_path)
        if err:
            _log(f"ERROR: {err}")
            _set_status(UpdateStatus.FAILED, err)
            return
        actual_size = package_path.stat().st_size
        if package_size and actual_size != package_size:
            err = f"Downloaded package size mismatch: expected {package_size}, got {actual_size}"
            _log(f"ERROR: {err}")
            _set_status(UpdateStatus.FAILED, err)
            return
        _write_marker(staging_dir, "phase_downloaded", str(actual_size))
        _db_update(status=UpdateStatus.DOWNLOADED, package_size=actual_size, last_step="Downloading package")
        _log(f"Downloaded: {actual_size // 1024}KB")

        # ── Step 2: Verify checksum ────────────────────────────────────────────
        _progress_update(update_id, 2, "Verifying checksum")
        _log(f"Verifying SHA-256: {expected_sha[:16]}…")
        if not verify_package_checksum(package_path, expected_sha):
            err = "Package SHA-256 mismatch — corrupted download or tampered package, update rejected"
            _log(f"ERROR: {err}")
            _set_status(UpdateStatus.FAILED, err)
            return
        _write_marker(staging_dir, "phase_verified", expected_sha)
        _db_update(status=UpdateStatus.VERIFIED, last_step="Verifying checksum")
        _log("Checksum OK")

        # ── Step 3: Extract ────────────────────────────────────────────────────
        _progress_update(update_id, 3, "Extracting package")
        _log("Extracting package to staging…")
        extract_dir = staging_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(package_path, "r:gz") as tar:
            tar.extractall(extract_dir)
        extract_root = extract_dir
        subdirs = list(extract_dir.iterdir())
        if len(subdirs) == 1 and subdirs[0].is_dir():
            extract_root = subdirs[0]
        err = _validate_extracted_release(extract_root, to_version)
        if err:
            _log(f"ERROR: {err}")
            _set_status(UpdateStatus.FAILED, err)
            return
        _write_marker(staging_dir, "phase_ready_to_apply", str(extract_root))
        _db_update(status=UpdateStatus.READY_TO_APPLY, last_step="Preparing apply")
        _log(f"Staging prepared: {extract_root}")

        # ── Steps 4-11: shell script ───────────────────────────────────────────
        _progress_update(update_id, 4, "Preparing apply")
        _db_update(status=UpdateStatus.APPLYING)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_dir = _BACKUP_BASE / f"pre_{to_version}_{ts}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Persist backup_dir immediately so rollback is possible even if script crashes
        _db_update(
            backup_path        = str(backup_dir),
            rollback_available = True,
            previous_release_path = str(_CURRENT_LINK.resolve()) if _CURRENT_LINK.exists() else None,
            last_step = "Creating backup",
        )

        _log(f"Backup dir: {backup_dir}")
        _log("Running update_apply.sh …")

        loop = asyncio.get_running_loop()
        rc, output = await loop.run_in_executor(
            None,
            lambda: _run_apply_script(
                package_path,
                backup_dir,
                _INSTALL_DIR,
                update_id,
                staging_dir=staging_dir,
                target_version=to_version,
                expected_package_sha=expected_sha,
                expected_package_size=package_size,
                expected_min_version=min_supported_version,
                requires_migration=requires_migration,
                requires_restart=requires_restart,
            ),
        )

        for line in output.splitlines():
            _log(line)

        if rc == 2:
            err = "Update failed — auto-rollback was attempted by update_apply.sh (check log)"
            _log(f"ERROR: {err}")
            logger.error(f"EVENT:UPDATE_FAILURE auto-rollback triggered (id={update_id})")
            _set_status(UpdateStatus.FAILED, err)
            # rollback_available stays True for manual rollback if auto-rollback also failed
            return

        if rc != 0:
            err = f"update_apply.sh exited with code {rc}"
            _log(f"ERROR: {err}")
            logger.error(f"EVENT:UPDATE_FAILURE apply script rc={rc} (id={update_id})")
            _set_status(UpdateStatus.FAILED, err)
            return

        # ── Finalise ───────────────────────────────────────────────────────────
        _progress_update(update_id, 11, "Finalising")
        new_ver = get_current_version()
        _log(f"Update successful: now at {new_ver}")
        logger.info(f"EVENT:UPDATE_SUCCESS → {new_ver} (id={update_id})")
        _set_status(UpdateStatus.SUCCESS)
        invalidate_cache()
        _log("Done.")

    except Exception as e:
        err = f"Unexpected error: {type(e).__name__}: {e}"
        logger.exception("EVENT:UPDATE_FAILURE update task %d failed: %s", update_id, e)
        _set_status(UpdateStatus.FAILED, err)
    finally:
        # Always clean up the downloaded package
        if package_path and package_path.exists():
            try:
                package_path.unlink()
                logger.debug("Cleaned up downloaded package: %s", package_path)
            except Exception:
                pass
        if staging_dir and staging_dir.exists():
            try:
                # Keep staging only if update did not succeed; useful for recovery/debug.
                if _progress.get(update_id, {}).get("status") == UpdateStatus.SUCCESS.value:
                    shutil.rmtree(staging_dir)
            except Exception:
                pass
        _cleanup_update_artifacts()


# ── Rollback ───────────────────────────────────────────────────────────────────

async def rollback_update(original_update_id: int, started_by: str = "admin") -> int:
    """
    Roll back a previous update using its backup.
    Creates a new UpdateHistory record (is_rollback=True).
    Returns rollback_update_id.

    Raises ValueError if rollback is not possible.
    """
    from src.database.models import UpdateHistory, UpdateStatus
    from src.database.connection import SessionLocal

    db = SessionLocal()
    try:
        original = db.get(UpdateHistory, original_update_id)
        if not original:
            raise ValueError(f"Update #{original_update_id} not found")
        if not original.rollback_available:
            raise ValueError("Rollback not available for this update (rollback_available=False)")
        if not original.backup_path:
            raise ValueError("Rollback not available: no backup_path recorded")
        if original.status not in (UpdateStatus.SUCCESS, UpdateStatus.FAILED):
            raise ValueError(f"Cannot roll back update in status '{original.status.value}'")

        # Verify backup files exist on disk before starting
        backup_path = Path(original.backup_path)
        if not backup_path.exists():
            raise ValueError(
                f"Backup directory not found on disk: {backup_path}. "
                "Backup may have been deleted — rollback not possible."
            )
        if not (backup_path / "code.tar.gz").exists():
            raise ValueError(
                f"Backup archive missing: {backup_path}/code.tar.gz. "
                "Backup is incomplete — rollback not possible."
            )

        rollback_rec = UpdateHistory(
            from_version       = original.to_version,
            to_version         = original.from_version,
            update_type        = "rollback",
            status             = UpdateStatus.PENDING,
            started_by         = started_by,
            rollback_available = False,
            is_rollback        = True,
            rollback_of_id     = original_update_id,
        )
        db.add(rollback_rec)
        db.commit()
        db.refresh(rollback_rec)
        rollback_id = rollback_rec.id
    finally:
        db.close()

    _progress[rollback_id] = {
        "update_id":   rollback_id,
        "status":      "in_progress",
        "step_number": 0,
        "step":        "Initialising rollback",
        "total_steps": 5,
        "log":         [],
        "started_at":  datetime.now(timezone.utc).isoformat(),
        "error":       None,
    }

    asyncio.create_task(_rollback_task(rollback_id, original_update_id))
    return rollback_id


async def _rollback_task(rollback_id: int, original_update_id: int):
    from src.database.models import UpdateHistory, UpdateStatus
    from src.database.connection import SessionLocal

    started_at = time.monotonic()
    log_lines: list[str] = []

    def _log(msg):
        log_lines.append(msg)
        p = _progress.get(rollback_id)
        if p:
            p["log"].append(msg)

    def _db_update(**kwargs):
        s = SessionLocal()
        try:
            rec = s.get(UpdateHistory, rollback_id)
            if rec:
                for k, v in kwargs.items():
                    setattr(rec, k, v)
                s.commit()
        finally:
            s.close()

    def _set_status(status: UpdateStatus, error: str = None):
        _db_update(
            status           = status,
            completed_at     = datetime.now(timezone.utc),
            duration_seconds = time.monotonic() - started_at,
            log              = "\n".join(log_lines),
            error_message    = error,
        )
        p = _progress.get(rollback_id)
        if p:
            p["status"] = status.value
            if error:
                p["error"] = error

    try:
        db = SessionLocal()
        try:
            original    = db.get(UpdateHistory, original_update_id)
            backup_path = Path(original.backup_path)
            from_ver    = original.to_version
            to_ver      = original.from_version
        finally:
            db.close()

        _log(f"Rolling back {from_ver} → {to_ver}")
        logger.info(f"EVENT:ROLLBACK_START {from_ver} → {to_ver} (id={rollback_id})")
        _log(f"Backup: {backup_path}")
        _db_update(status=UpdateStatus.ROLLING_BACK)

        loop = asyncio.get_running_loop()
        rc, output = await loop.run_in_executor(
            None,
            lambda: _run_rollback_script(backup_path, _INSTALL_DIR),
        )
        for line in output.splitlines():
            _log(line)

        if rc != 0:
            err = f"Rollback script exited with code {rc} — system may be in inconsistent state"
            _log(f"ERROR: {err}")
            _log("CRITICAL: Manual intervention may be required. Check system state.")
            logger.error(f"EVENT:ROLLBACK_FAILURE rc={rc} (id={rollback_id})")
            _set_status(UpdateStatus.FAILED, err)
            return

        _log("Rollback successful")
        logger.info(f"EVENT:ROLLBACK_SUCCESS {from_ver} → {to_ver} (id={rollback_id})")
        _set_status(UpdateStatus.ROLLED_BACK)

        # Mark original update as rolled_back
        s = SessionLocal()
        try:
            orig = s.get(UpdateHistory, original_update_id)
            if orig:
                orig.status             = UpdateStatus.ROLLED_BACK
                orig.rollback_available = False
                s.commit()
        finally:
            s.close()

        invalidate_cache()
        _cleanup_update_artifacts()

    except Exception as e:
        err = f"Unexpected rollback error: {type(e).__name__}: {e}"
        logger.exception("Rollback task %d failed", rollback_id)
        _set_status(UpdateStatus.FAILED, err)


# ── Progress query ─────────────────────────────────────────────────────────────

def get_progress(update_id: int) -> Optional[dict]:
    return _progress.get(update_id)


def get_active_update_id() -> Optional[int]:
    """Return update_id of any currently running update/rollback (in-memory)."""
    for uid, p in _progress.items():
        if p["status"] == "in_progress":
            return uid
    return None
