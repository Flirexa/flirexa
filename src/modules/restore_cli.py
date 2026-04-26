from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.database.connection import get_db_context
from src.modules.backup_manager import BackupManager
from src.modules.operational_mode import get_explicit_maintenance_state, set_maintenance_mode
from src.modules.system_status.collector import collect_system_status


@dataclass
class RestoreCommandResult:
    success: bool
    action: str
    archive_path: str | None = None
    backup_id: str | None = None
    version: str | None = None
    mode: str | None = None
    restored_sections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    maintenance_reason: str | None = None
    health_summary: dict[str, str] = field(default_factory=dict)
    log_hint: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_REQUIRED_DISK_MB = 300
_POST_RESTORE_HEALTH_RETRIES = 15
_POST_RESTORE_HEALTH_INTERVAL_SECONDS = 2


def _extract_backup_id(archive_path: Path) -> str:
    name = archive_path.name
    prefix = "vpnmanager-backup-"
    suffix = ".tar.gz"
    if not name.startswith(prefix) or not name.endswith(suffix):
        raise RuntimeError("Restore archive must be named vpnmanager-backup-<id>.tar.gz")
    backup_id = name[len(prefix):-len(suffix)]
    if not backup_id:
        raise RuntimeError("Unable to derive backup id from archive name")
    return backup_id


def _resolve_archive(archive: str | None, from_dir: str | None) -> Path:
    if archive:
        raw = Path(archive)
        if from_dir and not raw.is_absolute():
            raw = Path(from_dir) / raw
        if not raw.is_file():
            raise RuntimeError(f"Restore archive not found: {raw}")
        return raw

    if not from_dir:
        raise RuntimeError("Restore archive is required; pass --archive <path>")

    root = Path(from_dir)
    if not root.is_dir():
        raise RuntimeError(f"Restore source directory not found: {root}")

    archives = sorted(root.glob("vpnmanager-backup-*.tar.gz"))
    if not archives:
        raise RuntimeError(f"No restore archive found in {root}")
    if len(archives) > 1:
        raise RuntimeError(f"Multiple restore archives found in {root}; pass --archive explicitly")
    return archives[0]


def _restored_sections(result: dict) -> list[str]:
    sections: list[str] = []
    if result.get("database_restored"):
        sections.append("db")
    if result.get("env_restored"):
        sections.append("env")
    if result.get("wireguard_restored"):
        sections.append("wireguard")
    if result.get("services_restarted"):
        sections.append("services")
    return sections


def _post_restore_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "DATABASE_URL",
        "ASYNC_DATABASE_URL",
        "DB_HOST",
        "DB_PORT",
        "DB_USER",
        "DB_PASSWORD",
        "DB_NAME",
    ):
        env.pop(key, None)
    env["VMS_SUPPRESS_ENCRYPTION_WARNING"] = "1"
    return env


def _collect_post_restore_status_payload() -> dict:
    cmd = [sys.executable, "-m", "src.cli.main", "status", "--json"]
    cwd = str(Path(__file__).resolve().parents[2])
    last_payload: dict = {
        "result": "failed",
        "mode": "degraded",
        "version": None,
        "maintenance_reason": None,
        "degraded_reasons": [],
        "failed_reasons": ["post-restore status probe failed"],
        "health": {},
    }

    for attempt in range(_POST_RESTORE_HEALTH_RETRIES):
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=_post_restore_env(),
            capture_output=True,
            text=True,
        )
        try:
            payload = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            payload = {
                "result": "failed",
                "mode": "degraded",
                "version": None,
                "maintenance_reason": None,
                "degraded_reasons": [],
                "failed_reasons": [(proc.stderr or proc.stdout or "post-restore status probe failed").strip()],
                "health": {},
            }
        last_payload = payload
        if payload.get("result") != "failed":
            return payload
        if attempt < _POST_RESTORE_HEALTH_RETRIES - 1:
            time.sleep(_POST_RESTORE_HEALTH_INTERVAL_SECONDS)
    return last_payload


def create_restore_command(*, archive: str | None = None, from_dir: str | None = None) -> RestoreCommandResult:
    status = collect_system_status()

    if os.geteuid() != 0:
        return RestoreCommandResult(
            success=False,
            action="restore_full",
            version=status.version,
            mode=status.mode,
            error="Restore must be run as root",
        )

    if not Path(status.install_root).exists():
        return RestoreCommandResult(
            success=False,
            action="restore_full",
            version=status.version,
            mode=status.mode,
            error=f"Install root does not exist: {status.install_root}",
        )

    if status.mode in {"update_in_progress", "rollback_in_progress"} or status.update.active:
        return RestoreCommandResult(
            success=False,
            action="restore_full",
            version=status.version,
            mode=status.mode,
            error="Restore is blocked while update or rollback is active",
        )

    try:
        archive_path = _resolve_archive(archive, from_dir)
        backup_id = _extract_backup_id(archive_path)
    except Exception as exc:
        return RestoreCommandResult(
            success=False,
            action="restore_full",
            version=status.version,
            mode=status.mode,
            error=str(exc),
        )

    for tool in ("systemctl", "pg_restore", "gunzip"):
        if shutil.which(tool) is None:
            return RestoreCommandResult(
                success=False,
                action="restore_full",
                archive_path=str(archive_path),
                backup_id=backup_id,
                version=status.version,
                mode=status.mode,
                error=f"Required restore tool is missing: {tool}",
            )

    if not os.access(status.install_root, os.W_OK):
        return RestoreCommandResult(
            success=False,
            action="restore_full",
            archive_path=str(archive_path),
            backup_id=backup_id,
            version=status.version,
            mode=status.mode,
            error=f"Restore destination is not writable: {status.install_root}",
        )

    free_mb = shutil.disk_usage(status.install_root).free // (1024 * 1024)
    if free_mb < _REQUIRED_DISK_MB:
        return RestoreCommandResult(
            success=False,
            action="restore_full",
            archive_path=str(archive_path),
            backup_id=backup_id,
            version=status.version,
            mode=status.mode,
            error=f"Insufficient free space in install root: {free_mb} MB",
        )

    try:
        with get_db_context() as db:
            explicit_maintenance = get_explicit_maintenance_state(db)
    except Exception as exc:
        return RestoreCommandResult(
            success=False,
            action="restore_full",
            archive_path=str(archive_path),
            backup_id=backup_id,
            version=status.version,
            mode=status.mode,
            error=f"Failed to read maintenance state: {exc}",
        )

    maintenance_changed = False
    warnings: list[str] = []
    if not explicit_maintenance.enabled:
        try:
            set_maintenance_mode(
                True,
                reason=f"restore from {archive_path.name}",
                source="cli",
                actor="vpnmanager",
            )
            maintenance_changed = True
        except Exception as exc:
            return RestoreCommandResult(
                success=False,
                action="restore_full",
                archive_path=str(archive_path),
                backup_id=backup_id,
                version=status.version,
                mode=status.mode,
                error=f"Failed to enable maintenance mode: {exc}",
            )
    else:
        warnings.append(f"Maintenance mode already enabled: {explicit_maintenance.reason or 'no reason set'}")

    manager_result: dict | None = None
    try:
        with get_db_context() as db:
            mgr = BackupManager(db, backup_dir=str(archive_path.parent))
            verify = mgr.verify_backup(backup_id)
            if not verify.get("ok"):
                raise RuntimeError("; ".join(verify.get("errors") or ["Backup verification failed"]))
            manager_result = mgr.restore_full_system(
                backup_id,
                restart_services=True,
                stop_services=True,
                audit_user_type="admin",
                audit_source="cli",
                audit_actor="vpnmanager",
            )
    except Exception as exc:
        if maintenance_changed:
            try:
                set_maintenance_mode(
                    True,
                    reason=f"restore failed from {archive_path.name}; manual verification required",
                    source="system",
                    actor="vpnmanager",
                )
            except Exception:
                pass
        return RestoreCommandResult(
            success=False,
            action="restore_full",
            archive_path=str(archive_path),
            backup_id=backup_id,
            version=status.version,
            mode="maintenance",
            warnings=warnings,
            error=str(exc),
            maintenance_reason=f"restore failed from {archive_path.name}; manual verification required",
            log_hint="journalctl -u vpnmanager-api",
        )

    post_status = _collect_post_restore_status_payload()
    health_summary = {
        "api": ((post_status.get("health") or {}).get("api") or {}).get("status", "unknown"),
        "portal": ((post_status.get("health") or {}).get("portal") or {}).get("status", "unknown"),
        "db": ((post_status.get("health") or {}).get("db") or {}).get("status", "unknown"),
        "alembic": ((post_status.get("health") or {}).get("alembic") or {}).get("status", "unknown"),
        "services": ((post_status.get("health") or {}).get("services") or {}).get("status", "unknown"),
        "disk": ((post_status.get("health") or {}).get("disk") or {}).get("status", "unknown"),
        "update_system": ((post_status.get("health") or {}).get("update_system") or {}).get("status", "unknown"),
        "license": ((post_status.get("health") or {}).get("license") or {}).get("status", "unknown"),
    }

    errors = list(manager_result.get("errors") or [])
    if post_status.get("result") == "failed":
        errors.extend(post_status.get("failed_reasons") or ["post-restore health failed"])
    elif post_status.get("result") == "degraded":
        warnings.extend(post_status.get("degraded_reasons") or [])

    success = len(errors) == 0
    final_mode = post_status.get("mode") or "normal"
    maintenance_reason = post_status.get("maintenance_reason")

    if success and maintenance_changed:
        try:
            mode = set_maintenance_mode(False, reason=None, source="cli", actor="vpnmanager")
            final_mode = mode.mode
            maintenance_reason = mode.maintenance_reason
        except Exception as exc:
            success = False
            errors.append(f"Failed to disable maintenance mode after restore: {exc}")
            final_mode = "maintenance"
            maintenance_reason = "restore completed but maintenance cleanup failed"
    elif not success and maintenance_changed:
        try:
            mode = set_maintenance_mode(
                True,
                reason=f"restore failed from {archive_path.name}; manual verification required",
                source="system",
                actor="vpnmanager",
            )
            final_mode = mode.mode
            maintenance_reason = mode.maintenance_reason
        except Exception:
            final_mode = "maintenance"
            maintenance_reason = f"restore failed from {archive_path.name}; manual verification required"

    return RestoreCommandResult(
        success=success,
        action="restore_full",
        archive_path=str(archive_path),
        backup_id=backup_id,
        version=post_status.get("version") if success else status.version,
        mode=final_mode,
        restored_sections=_restored_sections(manager_result),
        warnings=warnings,
        error="; ".join(errors) if errors else None,
        maintenance_reason=maintenance_reason,
        health_summary=health_summary,
        log_hint="journalctl -u vpnmanager-api",
    )
