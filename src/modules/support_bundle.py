from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import tarfile
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.database.connection import get_db_context
from src.database.models import SystemConfig, UpdateHistory
from src.modules.support_bundle_sanitizer import sanitize_env_text, sanitize_mapping
from src.modules.system_status.collector import collect_system_status
from src.utils.runtime_paths import get_current_link, get_install_root


DEFAULT_OUTPUT_DIR = "/tmp"
DEFAULT_UPDATE_HISTORY_LIMIT = 20


@dataclass
class BundleSectionResult:
    name: str
    included: bool
    error: str | None = None
    files: list[str] = field(default_factory=list)


@dataclass
class SupportBundleResult:
    success: bool
    archive_path: str
    bundle_size_bytes: int
    sections_included: list[str]
    sections_failed: list[dict[str, str]]
    manifest_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_collect(name: str, collector, sections: list[BundleSectionResult]):
    try:
        result = collector()
        section = BundleSectionResult(name=name, included=True)
        sections.append(section)
        return result, section
    except Exception as exc:
        sections.append(BundleSectionResult(name=name, included=False, error=str(exc)))
        return None, None


def _read_os_release() -> dict[str, str]:
    data: dict[str, str] = {}
    path = Path("/etc/os-release")
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        data[key] = value.strip().strip('"')
    return data


def _system_info(status) -> dict[str, Any]:
    os_release = _read_os_release()
    return {
        "collected_at": _now_iso(),
        "hostname": socket.gethostname(),
        "platform": platform.system(),
        "platform_release": platform.release(),
        "kernel": platform.version(),
        "architecture": platform.machine(),
        "os_release": os_release,
        "uptime_seconds": status.uptime.host_seconds,
        "install_root": status.install_root,
        "layout_mode": status.layout_mode,
        "version": status.version,
        "current_release": status.current_release,
    }


def _disk_usage(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    usage = shutil.disk_usage(path)
    return {
        "path": str(path),
        "exists": True,
        "total_mb": usage.total // (1024 * 1024),
        "used_mb": usage.used // (1024 * 1024),
        "free_mb": usage.free // (1024 * 1024),
    }


def _list_dir(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for entry in sorted(path.iterdir(), key=lambda p: p.name):
        stat = entry.stat()
        items.append(
            {
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size_bytes": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return items


def _query_update_rows(db: Session, limit: int) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT id,
                   from_version,
                   to_version,
                   status::text AS status,
                   started_at,
                   completed_at,
                   started_by,
                   is_rollback,
                   error_message
            FROM update_history
            ORDER BY started_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": row.get("id"),
                "from_version": row.get("from_version"),
                "to_version": row.get("to_version"),
                "status": row.get("status"),
                "channel": None,
                "started_at": row.get("started_at").isoformat() if row.get("started_at") else None,
                "completed_at": row.get("completed_at").isoformat() if row.get("completed_at") else None,
                "started_by": row.get("started_by"),
                "is_rollback": row.get("is_rollback"),
                "rollback_of_id": None,
                "backup_path": None,
                "staging_path": None,
                "package_path": None,
                "last_step": None,
                "error_message": row.get("error_message"),
            }
        )
    return result


def _query_system_config(db: Session, *, strict: bool) -> list[dict[str, Any]]:
    rows = db.query(SystemConfig).order_by(SystemConfig.key.asc()).all()
    payload = []
    for row in rows:
        payload.append(
            sanitize_mapping(
                {
                    "key": row.key,
                    "value": row.value,
                    "value_type": row.value_type,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                },
                strict=strict,
            )
        )
    return payload


def _collect_journal(unit: str, *, since: str | None) -> str:
    cmd = ["journalctl", "-u", unit, "-n", "200", "--no-pager", "--output=short-iso"]
    if since:
        cmd.extend(["--since", since])
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if res.returncode not in {0, 1}:
        raise RuntimeError(res.stderr.strip() or f"journalctl failed for {unit}")
    return res.stdout


def _collect_apply_log(status, *, include_update_logs: bool) -> tuple[str | None, str | None]:
    if not include_update_logs:
        return None, None
    candidates: list[Path] = []
    if status.update.last_update and status.backup.last_update_backup_path:
        candidates.append(Path(status.backup.last_update_backup_path) / "apply.log")
    if status.backup.last_backup_path:
        candidates.append(Path(status.backup.last_backup_path) / "apply.log")
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace"), str(path)
    return None, None


def _sanitize_env_file(path: Path, *, strict: bool) -> str:
    if not path.exists():
        return ""
    return sanitize_env_text(path.read_text(encoding="utf-8", errors="replace"), strict=strict)


def _archive_directory(source_dir: Path, archive_path: Path) -> int:
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(source_dir, arcname=source_dir.name)
    return archive_path.stat().st_size


def create_support_bundle(
    *,
    output_dir: str | None = None,
    since: str | None = None,
    include_journal: bool = False,
    include_update_logs: bool = False,
    redact_strict: bool = False,
    update_history_limit: int = DEFAULT_UPDATE_HISTORY_LIMIT,
) -> SupportBundleResult:
    install_root = get_install_root("/opt/vpnmanager")
    status = collect_system_status()
    timestamp = _now().strftime("%Y%m%d-%H%M%S")
    bundle_name = f"vpnmanager-support-bundle-{timestamp}"
    target_dir = Path(output_dir or DEFAULT_OUTPUT_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    archive_path = target_dir / f"{bundle_name}.tar.gz"

    sections: list[BundleSectionResult] = []
    with tempfile.TemporaryDirectory(prefix="vpnmanager-support-bundle-") as tmp:
        bundle_root = Path(tmp) / bundle_name
        bundle_root.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "created_at": _now_iso(),
            "bundle_name": bundle_name,
            "version": status.version,
            "mode": status.mode,
            "install_root": status.install_root,
            "layout_mode": status.layout_mode,
            "sections": [],
            "errors": [],
        }

        info, section = _safe_collect("system_info", lambda: _system_info(status), sections)
        if info is not None and section is not None:
            _write_json(bundle_root / "system" / "system_info.json", info)
            section.files.append("system/system_info.json")

        status_payload = status.to_dict()
        section = BundleSectionResult(name="status", included=True, files=["status.json", "health.json"])
        sections.append(section)
        _write_json(bundle_root / "status.json", status_payload)
        _write_json(
            bundle_root / "health.json",
            {
                "result": status.result,
                "mode": status.mode,
                "maintenance_reason": status.maintenance_reason,
                "health": asdict(status.health),
                "degraded_reasons": status.degraded_reasons,
                "failed_reasons": status.failed_reasons,
            },
        )

        updates_section = BundleSectionResult(name="updates", included=True)
        sections.append(updates_section)
        update_state_payload = {
            "active": status.update.active,
            "active_kind": status.update.active_kind,
            "active_id": status.update.active_id,
            "lock_present": status.update.lock_present,
            "staging_dirs": status.update.staging_dirs,
            "consistency_ok": status.update.consistency_ok,
            "consistency_message": status.update.consistency_message,
            "last_update": asdict(status.update.last_update) if status.update.last_update else None,
            "last_rollback": asdict(status.update.last_rollback) if status.update.last_rollback else None,
        }
        layout_payload = {
            "current_link": str(get_current_link(install_root)),
            "current_target": status.current_release,
            "backups_root": str(install_root / "backups"),
            "staging_root": str(install_root / "staging"),
        }
        _write_json(bundle_root / "updates" / "update_state.json", update_state_payload)
        _write_json(bundle_root / "updates" / "layout_info.json", layout_payload)
        updates_section.files.extend(["updates/update_state.json", "updates/layout_info.json"])
        try:
            with get_db_context() as db:
                history_payload = _query_update_rows(db, update_history_limit)
            _write_json(bundle_root / "updates" / "update_history.json", history_payload)
            updates_section.files.append("updates/update_history.json")
        except Exception as exc:
            updates_section.error = str(exc)
        apply_log_text, apply_log_source = _collect_apply_log(status, include_update_logs=include_update_logs)
        if apply_log_text is not None:
            _write_text(bundle_root / "updates" / "last_apply.log", apply_log_text)
            _write_json(
                bundle_root / "updates" / "last_apply_meta.json",
                {"source_path": apply_log_source, "included": True},
            )
            updates_section.files.extend(["updates/last_apply.log", "updates/last_apply_meta.json"])

        storage_payload = {
            "disk_usage": {
                "install_root": _disk_usage(install_root),
                "backups": _disk_usage(install_root / "backups"),
                "staging": _disk_usage(install_root / "staging"),
            },
            "layout": {
                "current_link": str(get_current_link(install_root)),
                "current_target": status.current_release,
                "layout_mode": status.layout_mode,
            },
            "listings": {
                "backups": _list_dir(install_root / "backups"),
                "staging": _list_dir(install_root / "staging"),
                "releases": _list_dir(install_root / "releases"),
            },
        }
        section = BundleSectionResult(name="storage", included=True, files=["storage/storage.json"])
        sections.append(section)
        _write_json(bundle_root / "storage" / "storage.json", storage_payload)

        config_section = BundleSectionResult(name="config", included=True)
        sections.append(config_section)
        _write_text(
            bundle_root / "config" / "dotenv.sanitized",
            _sanitize_env_file(install_root / ".env", strict=redact_strict),
        )
        config_section.files.append("config/dotenv.sanitized")
        try:
            with get_db_context() as db:
                system_config_payload = _query_system_config(db, strict=redact_strict)
            _write_json(
                bundle_root / "config" / "system_config.json",
                {"system_config": system_config_payload},
            )
            config_section.files.append("config/system_config.json")
        except Exception as exc:
            config_section.error = str(exc)

        license_payload = {
            "summary": sanitize_mapping(status.license.__dict__, strict=redact_strict),
            "mode": status.mode,
            "maintenance_reason": status.maintenance_reason,
        }
        section = BundleSectionResult(name="license", included=True, files=["system/license_summary.json"])
        sections.append(section)
        _write_json(bundle_root / "system" / "license_summary.json", license_payload)

        if include_journal:
            journal_section = BundleSectionResult(name="journal", included=True)
            sections.append(journal_section)
            for service in status.services:
                try:
                    content = _collect_journal(service.unit, since=since)
                    if not content.strip():
                        continue
                    rel = f"logs/{service.unit}.journal.log"
                    _write_text(bundle_root / rel, content)
                    journal_section.files.append(rel)
                except Exception as exc:
                    journal_section.included = bool(journal_section.files)
                    journal_section.error = f"{service.unit}: {exc}"
            if not journal_section.files and not journal_section.error:
                journal_section.error = "journal collection produced no output"
                journal_section.included = False

        for section in sections:
            manifest["sections"].append(
                {
                    "name": section.name,
                    "included": section.included,
                    "files": section.files,
                    "error": section.error,
                }
            )
            if section.error:
                manifest["errors"].append({"section": section.name, "error": section.error})

        manifest_path = bundle_root / "manifest.json"
        _write_json(manifest_path, manifest)
        size = _archive_directory(bundle_root, archive_path)

    return SupportBundleResult(
        success=True,
        archive_path=str(archive_path),
        bundle_size_bytes=size,
        sections_included=[section.name for section in sections if section.included],
        sections_failed=[{"section": section.name, "error": section.error or "unknown error"} for section in sections if section.error],
        manifest_path="manifest.json",
    )
