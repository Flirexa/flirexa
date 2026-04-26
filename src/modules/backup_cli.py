from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from src.database.connection import get_db_context
from src.modules.backup_manager import BackupManager
from src.modules.system_status.collector import collect_system_status
from src.utils.runtime_paths import get_install_root


BackupType = Literal["full", "db-only"]


@dataclass
class BackupCommandResult:
    success: bool
    action: str
    backup_type: BackupType
    archive_path: str | None = None
    size_bytes: int | None = None
    version: str | None = None
    mode: str | None = None
    included_sections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _resolve_output(output: str | None) -> tuple[Path, str | None]:
    if not output:
        return Path(get_install_root("/opt/vpnmanager")) / "backups", None
    raw = Path(output)
    if raw.suffixes[-2:] == [".tar", ".gz"]:
        return raw.parent, raw.name
    return raw, None


def _ensure_writable_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise RuntimeError(f"Backup destination is not a directory: {path}")
    if not os.access(path, os.W_OK):
        raise RuntimeError(f"Backup destination is not writable: {path}")


def _required_free_mb(backup_type: BackupType) -> int:
    return 300 if backup_type == "full" else 100


def _included_sections(backup_type: BackupType) -> list[str]:
    if backup_type == "db-only":
        return ["db", "system"]
    return ["db", "env", "wireguard", "servers", "system"]


def create_backup_command(
    *,
    backup_type: BackupType = "full",
    output: str | None = None,
    name: str | None = None,
) -> BackupCommandResult:
    status = collect_system_status()

    if not Path(status.install_root).exists():
        return BackupCommandResult(
            success=False,
            action="backup_create",
            backup_type=backup_type,
            version=status.version,
            mode=status.mode,
            error=f"Install root does not exist: {status.install_root}",
        )

    if status.mode in {"update_in_progress", "rollback_in_progress"} or status.update.active:
        return BackupCommandResult(
            success=False,
            action="backup_create",
            backup_type=backup_type,
            version=status.version,
            mode=status.mode,
            error="Backup is blocked while update or rollback is active",
        )

    if not status.db.connected:
        return BackupCommandResult(
            success=False,
            action="backup_create",
            backup_type=backup_type,
            version=status.version,
            mode=status.mode,
            error=status.db.error or "Database is unavailable",
        )

    output_dir, archive_name = _resolve_output(output)
    try:
        _ensure_writable_dir(output_dir)
    except Exception as exc:
        return BackupCommandResult(
            success=False,
            action="backup_create",
            backup_type=backup_type,
            version=status.version,
            mode=status.mode,
            error=str(exc),
        )

    free_mb = shutil.disk_usage(output_dir).free // (1024 * 1024)
    if free_mb < _required_free_mb(backup_type):
        return BackupCommandResult(
            success=False,
            action="backup_create",
            backup_type=backup_type,
            version=status.version,
            mode=status.mode,
            error=f"Insufficient free space in backup destination: {free_mb} MB",
        )

    warnings: list[str] = []
    if status.mode != "maintenance":
        warnings.append("Backup is created without maintenance mode; consistency level is online snapshot")

    try:
        with get_db_context() as db:
            mgr = BackupManager(db, backup_dir=str(output_dir))
            if backup_type == "db-only":
                metadata = mgr.create_database_backup(
                    archive_name=archive_name,
                    label=name,
                    audit_user_type="admin",
                    audit_source="cli",
                    audit_actor="vpnmanager",
                )
            else:
                metadata = mgr.create_full_backup(
                    archive_name=archive_name,
                    label=name,
                    audit_user_type="admin",
                    audit_source="cli",
                    audit_actor="vpnmanager",
                )
    except Exception as exc:
        return BackupCommandResult(
            success=False,
            action="backup_create",
            backup_type=backup_type,
            version=status.version,
            mode=status.mode,
            warnings=warnings,
            error=str(exc),
        )

    if metadata.get("errors"):
        return BackupCommandResult(
            success=False,
            action="backup_create",
            backup_type=backup_type,
            archive_path=metadata.get("archive_path"),
            size_bytes=metadata.get("archive_size_bytes"),
            version=status.version,
            mode=status.mode,
            included_sections=_included_sections(backup_type),
            warnings=warnings,
            error="; ".join(str(item) for item in metadata["errors"]),
        )

    return BackupCommandResult(
        success=True,
        action="backup_create",
        backup_type=backup_type,
        archive_path=metadata.get("archive_path"),
        size_bytes=metadata.get("archive_size_bytes"),
        version=status.version,
        mode=status.mode,
        included_sections=_included_sections(backup_type),
        warnings=warnings,
    )
