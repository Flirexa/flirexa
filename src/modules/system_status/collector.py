from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import fcntl
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from src.database.connection import DATABASE_URL, check_db_connection, engine, get_db_context
from src.database.models import SystemConfig, UpdateHistory, UpdateStatus
from src.modules.license.online_validator import get_online_status, is_license_blocked
try:
    from src.modules.license.online_validator import _warmup_from_cache as _license_warmup_from_cache
except ImportError:  # pragma: no cover
    _license_warmup_from_cache = None
from src.modules.operational_mode import (
    ExplicitMaintenanceState,
    get_explicit_maintenance_state,
    resolve_operational_mode,
)
from src.modules.system_status.models import (
    BackupStatusSummary,
    ComponentHealth,
    DatabaseStatusSummary,
    DiskStatusSummary,
    HealthStatusSummary,
    LicenseStatusSummary,
    ServiceStatus,
    SystemStatus,
    UpdateRecordSummary,
    UpdateStatusSummary,
    UptimeSummary,
)
from src.utils.runtime_paths import get_current_link, get_install_root, get_runtime_root


_DEFAULT_INSTALL_ROOT = "/opt/vpnmanager"
_LOW_DISK_MB = int(os.getenv("VPNMANAGER_STATUS_LOW_DISK_MB", "1024"))
_STALE_UPDATE_MINUTES = int(os.getenv("UPDATE_PROGRESS_STALE_MINUTES", "30"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _service_prefix() -> str:
    env_prefix = os.getenv("SERVICE_PREFIX", "").strip()
    if env_prefix:
        return env_prefix
    try:
        for prefix in ("spongebot", "vpnmanager"):
            active_res = subprocess.run(
                ["systemctl", "is-active", f"{prefix}-api"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if active_res.returncode == 0:
                return prefix
    except Exception:
        pass
    install_root = get_install_root(_DEFAULT_INSTALL_ROOT)
    if install_root.name == "spongebot":
        return "spongebot"
    if install_root.name == "vpnmanager":
        return "vpnmanager"
    try:
        out = subprocess.check_output(
            ["systemctl", "list-unit-files"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if "spongebot-api.service" in out:
            return "spongebot"
        if "vpnmanager-api.service" in out:
            return "vpnmanager"
    except Exception:
        pass
    return "vpnmanager"


def _read_version(install_root: Path) -> str:
    try:
        version_file = get_runtime_root(install_root) / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
        return (install_root / "VERSION").read_text().strip()
    except Exception:
        return "0.0.0"


def _current_release_info(install_root: Path) -> tuple[str, str | None, bool]:
    current = get_current_link(install_root)
    if current.exists() or current.is_symlink():
        try:
            target = current.resolve(strict=False)
            target_str = str(target)
            releases_root = install_root / "releases"
            is_release_layout = current.is_symlink() and releases_root.exists() and str(target).startswith(str(releases_root))
            return ("release-layout" if is_release_layout else "compat-inplace", target_str, target.exists())
        except Exception:
            return ("compat-inplace", None, False)
    runtime_root = get_runtime_root(install_root)
    return ("compat-inplace", str(runtime_root), runtime_root.exists())


def _disk_free_mb(path: Path) -> int | None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(path).free // (1024 * 1024)
    except Exception:
        return None


def _service_status(unit: str) -> ServiceStatus:
    enabled = None
    active = False
    substate = None
    status_text = None

    try:
        enabled_res = subprocess.run(
            ["systemctl", "is-enabled", unit],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if enabled_res.returncode == 0:
            enabled = True
        elif enabled_res.stdout.strip() in {"disabled", "masked", "static", "indirect"}:
            enabled = False
    except Exception:
        enabled = None

    try:
        active_res = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=5,
        )
        active = active_res.returncode == 0
        status_text = active_res.stdout.strip() or None
    except Exception:
        active = False

    try:
        show_res = subprocess.run(
            ["systemctl", "show", unit, "-p", "SubState", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if show_res.returncode == 0:
            substate = show_res.stdout.strip() or None
    except Exception:
        substate = None

    return ServiceStatus(
        name=unit,
        unit=unit,
        enabled=enabled,
        active=active,
        substate=substate,
        status_text=status_text,
    )


def _expected_services(prefix: str) -> list[str]:
    base = [
        f"{prefix}-api",
        f"{prefix}-admin-bot",
        f"{prefix}-client-bot",
        f"{prefix}-worker",
        f"{prefix}-client-portal",
        "postgresql",
        "nginx",
    ]
    return base


def _collect_services(prefix: str) -> list[ServiceStatus]:
    return [_service_status(unit) for unit in _expected_services(prefix)]


def _component_from_http(url: str) -> ComponentHealth:
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
            resp = client.get(url)
        if resp.status_code == 200:
            return ComponentHealth(status="ok", message="HTTP 200", details={"status_code": 200})
        return ComponentHealth(
            status="failed",
            message=f"HTTP {resp.status_code}",
            details={"status_code": resp.status_code},
        )
    except Exception as exc:
        return ComponentHealth(status="failed", message=str(exc), details={})


def _collect_db_status() -> DatabaseStatusSummary:
    if not check_db_connection():
        return DatabaseStatusSummary(connected=False, error="database connection failed")

    try:
        with engine.connect() as conn:
            current_revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()

        project_root = Path(__file__).resolve().parents[3]
        head_revision = _discover_head_revision(project_root / "alembic" / "versions")

        return DatabaseStatusSummary(
            connected=True,
            current_revision=current_revision,
            head_revision=head_revision,
            matches_head=(current_revision == head_revision),
        )
    except Exception as exc:
        return DatabaseStatusSummary(
            connected=True,
            error=str(exc),
        )


def _discover_head_revision(versions_dir: Path) -> str | None:
    revisions: dict[str, list[str | None]] = {}
    referenced: set[str] = set()

    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        rev_match = re.search(r"revision\s*=\s*['\"]([^'\"]+)['\"]", text)
        if not rev_match:
            continue
        revision = rev_match.group(1)

        down_match = re.search(r"down_revision\s*=\s*(.+)", text)
        down_revisions: list[str | None] = []
        if down_match:
            raw = down_match.group(1).strip()
            if raw in {"None", "null"}:
                down_revisions = [None]
            else:
                quoted = re.findall(r"['\"]([^'\"]+)['\"]", raw)
                down_revisions = quoted or [None]
        revisions[revision] = down_revisions
        referenced.update([rev for rev in down_revisions if rev])

    heads = sorted(set(revisions) - referenced)
    return heads[0] if heads else None


def _summary_record_from_mapping(rec: dict | None) -> UpdateRecordSummary | None:
    if not rec:
        return None
    return UpdateRecordSummary(
        id=rec["id"],
        from_version=rec["from_version"],
        to_version=rec["to_version"],
        status=rec["status"] or "unknown",
        started_at=rec["started_at"].isoformat() if rec.get("started_at") else None,
        completed_at=rec["completed_at"].isoformat() if rec.get("completed_at") else None,
        is_rollback=bool(rec.get("is_rollback")),
        error_message=rec.get("error_message"),
    )


def _staging_dirs(staging_root: Path) -> list[str]:
    if not staging_root.exists():
        return []
    return sorted([p.name for p in staging_root.iterdir() if p.is_dir()])


def _update_lock_is_held(lock_path: Path) -> bool:
    if not lock_path.exists():
        return False
    try:
        with lock_path.open("a+") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            finally:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
    except OSError:
        return True
    return False


def _collect_backup_summary() -> BackupStatusSummary:
    install_root = get_install_root(_DEFAULT_INSTALL_ROOT)
    backup_root = install_root / "backups" / "update_backups"
    if not backup_root.exists():
        return BackupStatusSummary()
    candidates = sorted(
        [p for p in backup_root.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return BackupStatusSummary()
    last = candidates[0]
    return BackupStatusSummary(
        last_backup_at=datetime.fromtimestamp(last.stat().st_mtime, tz=timezone.utc).isoformat(),
        last_backup_path=str(last),
        last_update_backup_path=str(last),
    )


def _collect_update_summary(db_ok: bool, db_session: Session | None = None) -> UpdateStatusSummary:
    install_root = get_install_root(_DEFAULT_INSTALL_ROOT)
    lock_present = _update_lock_is_held(install_root / "update-lock" / "update.lock")
    staging_dirs = _staging_dirs(install_root / "staging")

    if not db_ok:
        return UpdateStatusSummary(
            active=False,
            lock_present=lock_present,
            staging_dirs=staging_dirs,
            consistency_ok=not lock_present,
            consistency_message=None if not lock_present else "update lock present while DB is unavailable",
        )

    if db_session is not None:
        db = db_session
        close_db = False
    else:
        ctx = get_db_context()
        db = ctx.__enter__()
        close_db = True
    try:
        active_statuses = [
            UpdateStatus.DOWNLOADING.name,
            UpdateStatus.DOWNLOADED.name,
            UpdateStatus.VERIFIED.name,
            UpdateStatus.READY_TO_APPLY.name,
            UpdateStatus.APPLYING.name,
            UpdateStatus.ROLLING_BACK.name,
            UpdateStatus.ROLLBACK_REQUIRED.name,
        ]
        try:
            rows = db.execute(
                text(
                    """
                    SELECT id, from_version, to_version, status::text AS status,
                           started_at, completed_at, is_rollback, error_message
                    FROM update_history
                    ORDER BY started_at DESC
                    LIMIT 50
                    """
                )
            ).mappings().all()
        except SQLAlchemyError as exc:
            return UpdateStatusSummary(
                active=False,
                last_update=None,
                last_rollback=None,
                lock_present=lock_present,
                staging_dirs=staging_dirs,
                consistency_ok=not lock_present,
                consistency_message=(
                    "update metadata unavailable due to schema drift"
                    if not lock_present
                    else f"update lock present and metadata unavailable: {exc}"
                ),
            )

        active = next((row for row in rows if (row.get("status") or "").upper() in active_statuses), None)
        last_update = next((row for row in rows if not bool(row.get("is_rollback"))), None)
        last_rollback = next((row for row in rows if bool(row.get("is_rollback"))), None)

        consistency_ok = True
        consistency_message = None
        active_kind = None
        active_id = None

        if active:
            active_id = active["id"]
            active_status = (active.get("status") or "").upper()
            active_kind = "rollback" if active.get("is_rollback") or active_status == UpdateStatus.ROLLING_BACK.name else "update"
            started_at = active.get("started_at")
            if started_at and started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            age_minutes = None
            if started_at:
                age_minutes = (datetime.now(timezone.utc) - started_at).total_seconds() / 60
            if active_status == UpdateStatus.ROLLBACK_REQUIRED.name:
                consistency_ok = False
                consistency_message = f"update {active_id} requires rollback"
            elif age_minutes and age_minutes > _STALE_UPDATE_MINUTES:
                consistency_ok = False
                consistency_message = f"active update {active_id} looks stale ({age_minutes:.0f} min)"
        elif lock_present:
            consistency_ok = False
            consistency_message = "dangling update lock without active DB record"

        return UpdateStatusSummary(
            active=active is not None,
            active_kind=active_kind,
            active_id=active_id,
            last_update=_summary_record_from_mapping(last_update),
            last_rollback=_summary_record_from_mapping(last_rollback),
            lock_present=lock_present,
            staging_dirs=staging_dirs,
            consistency_ok=consistency_ok,
            consistency_message=consistency_message,
        )
    finally:
        if close_db:
            ctx.__exit__(None, None, None)


def _worker_heartbeat(db_ok: bool, db_session: Session | None = None) -> tuple[str | None, float | None]:
    if not db_ok:
        return None, None
    if db_session is not None:
        value = (
            db_session.query(SystemConfig.value)
            .filter(SystemConfig.key == "worker_last_heartbeat")
            .scalar()
        )
    else:
        with get_db_context() as db:
            value = (
                db.query(SystemConfig.value)
                .filter(SystemConfig.key == "worker_last_heartbeat")
                .scalar()
            )
    if not value:
        return None, None
    try:
        ts = datetime.fromisoformat(value)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds() / 60
        return value, age
    except Exception:
        return value, None


def _license_summary(api_active: bool) -> LicenseStatusSummary:
    if _license_warmup_from_cache is not None:
        try:
            _license_warmup_from_cache()
        except Exception:
            pass
    if not os.getenv("LICENSE_KEY", "").strip():
        return LicenseStatusSummary(
            mode="normal",
            status="not_activated",
            plan=None,
            grace=False,
            readonly=False,
            validator_running=api_active,
            last_check_at=None,
            server_reachable=None,
            message="License not activated",
        )
    raw = get_online_status()
    blocked, blocked_reason = is_license_blocked()
    status = raw.get("status") or "unknown"
    reachable = raw.get("server_reachable")
    message = blocked_reason or raw.get("message")
    grace = status == "ok" and reachable is False
    readonly = blocked
    mode = "license_expired_readonly" if readonly else ("license_grace" if grace else "normal")

    return LicenseStatusSummary(
        mode=mode,
        status=status,
        plan=raw.get("tier") or None,
        grace=grace,
        readonly=readonly,
        validator_running=api_active,
        last_check_at=raw.get("last_check"),
        server_reachable=reachable,
        message=message,
    )


def _health_from_services(services: list[ServiceStatus]) -> ComponentHealth:
    critical_units = {svc.unit for svc in services if svc.unit in {"postgresql"} or svc.unit.endswith("-api")}
    failed = [svc.unit for svc in services if svc.unit in critical_units and not svc.active]
    degraded = [svc.unit for svc in services if svc.enabled and not svc.active and svc.unit not in critical_units]
    if failed:
        return ComponentHealth(status="failed", message="required services inactive", details={"failed": failed})
    if degraded:
        return ComponentHealth(status="degraded", message="non-critical services inactive", details={"inactive": degraded})
    return ComponentHealth(status="ok", message="services active", details={})


def _worker_heartbeat_expected(services: list[ServiceStatus]) -> bool:
    worker_service = next((svc for svc in services if svc.unit.endswith("-worker")), None)
    if not worker_service:
        return False
    return worker_service.active or worker_service.enabled is True


def collect_system_status(db_session: Session | None = None) -> SystemStatus:
    install_root = get_install_root(_DEFAULT_INSTALL_ROOT)
    version = _read_version(install_root)
    layout_mode, current_release, current_ok = _current_release_info(install_root)
    prefix = _service_prefix()
    services = _collect_services(prefix)
    api_service = next((svc for svc in services if svc.unit.endswith("-api")), None)

    db = _collect_db_status()
    backup = _collect_backup_summary()
    update = _collect_update_summary(db.connected, db_session=db_session)
    license_summary = _license_summary(api_active=bool(api_service and api_service.active))
    worker_last_heartbeat, worker_age_minutes = _worker_heartbeat(db.connected, db_session=db_session)

    api_health = _component_from_http("http://localhost:10086/health?detail=true")
    portal_service = next((svc for svc in services if svc.unit.endswith("-client-portal")), None)
    if portal_service and portal_service.enabled is False:
        portal_health = ComponentHealth(status="unknown", message="portal disabled", details={})
    else:
        portal_health = _component_from_http("http://localhost:10090/health")

    disk = DiskStatusSummary(
        install_root_free_mb=_disk_free_mb(install_root),
        backups_free_mb=_disk_free_mb(install_root / "backups"),
        staging_free_mb=_disk_free_mb(install_root / "staging"),
    )
    disk.install_root_ok = None if disk.install_root_free_mb is None else disk.install_root_free_mb >= _LOW_DISK_MB
    disk.backups_ok = None if disk.backups_free_mb is None else disk.backups_free_mb >= _LOW_DISK_MB
    disk.staging_ok = None if disk.staging_free_mb is None else disk.staging_free_mb >= _LOW_DISK_MB

    if not db.connected:
        db_health = ComponentHealth(status="failed", message=db.error or "database unreachable", details={})
    else:
        db_health = ComponentHealth(status="ok", message="database connected", details={})

    if not db.connected:
        alembic_health = ComponentHealth(status="failed", message="database unavailable", details={})
    elif db.matches_head is True:
        alembic_health = ComponentHealth(
            status="ok",
            message="schema at head",
            details={"current_revision": db.current_revision, "head_revision": db.head_revision},
        )
    else:
        alembic_health = ComponentHealth(
            status="failed",
            message=db.error or "alembic revision mismatch",
            details={"current_revision": db.current_revision, "head_revision": db.head_revision},
        )

    services_health = _health_from_services(services)

    update_system_details = {
        "active": update.active,
        "active_id": update.active_id,
        "lock_present": update.lock_present,
        "staging_dirs": update.staging_dirs,
        "current_release": current_release,
        "layout_mode": layout_mode,
    }
    if not current_ok:
        update_system_health = ComponentHealth(
            status="failed",
            message="current runtime path is invalid",
            details=update_system_details,
        )
    elif update.consistency_ok:
        update_system_health = ComponentHealth(status="ok", message="update state consistent", details=update_system_details)
    else:
        update_system_health = ComponentHealth(
            status="failed",
            message=update.consistency_message or "update state inconsistent",
            details=update_system_details,
        )

    if license_summary.readonly:
        license_health = ComponentHealth(status="failed", message=license_summary.message or "license blocked", details={})
    elif license_summary.grace:
        license_health = ComponentHealth(status="degraded", message=license_summary.message or "license grace", details={})
    else:
        license_health = ComponentHealth(status="ok", message=license_summary.message or "license OK", details={})

    disk_fail = any(flag is False and free is not None and free < 256 for flag, free in [
        (disk.install_root_ok, disk.install_root_free_mb),
        (disk.backups_ok, disk.backups_free_mb),
        (disk.staging_ok, disk.staging_free_mb),
    ])
    disk_degraded = any(flag is False for flag in [disk.install_root_ok, disk.backups_ok, disk.staging_ok] if flag is not None)
    if disk_fail:
        disk_health = ComponentHealth(status="failed", message="disk critically low", details=disk.__dict__)
    elif disk_degraded:
        disk_health = ComponentHealth(status="degraded", message="disk below threshold", details=disk.__dict__)
    else:
        disk_health = ComponentHealth(status="ok", message="disk OK", details=disk.__dict__)

    failed_reasons: list[str] = []
    degraded_reasons: list[str] = []

    if api_health.status == "failed":
        failed_reasons.append(f"API health failed: {api_health.message}")
    if db_health.status == "failed":
        failed_reasons.append(f"DB failed: {db_health.message}")
    if alembic_health.status == "failed":
        failed_reasons.append(f"Alembic failed: {alembic_health.message}")
    if services_health.status == "failed":
        failed_reasons.append(f"Services failed: {services_health.message}")
    if update_system_health.status == "failed":
        failed_reasons.append(f"Update system failed: {update_system_health.message}")
    if license_health.status == "failed":
        failed_reasons.append(f"License failed: {license_health.message}")
    if disk_health.status == "failed":
        failed_reasons.append(f"Disk failed: {disk_health.message}")

    if portal_health.status == "failed":
        degraded_reasons.append(f"Portal degraded: {portal_health.message}")
    if services_health.status == "degraded":
        degraded_reasons.append(f"Services degraded: {services_health.message}")
    if disk_health.status == "degraded":
        degraded_reasons.append(disk_health.message or "disk degraded")
    if license_health.status == "degraded":
        degraded_reasons.append(license_health.message or "license degraded")
    if _worker_heartbeat_expected(services):
        if worker_age_minutes and worker_age_minutes > 15:
            degraded_reasons.append(f"Worker heartbeat stale: {worker_age_minutes:.0f} min")
        elif worker_last_heartbeat is None:
            degraded_reasons.append("Worker heartbeat unknown")

    health = HealthStatusSummary(
        api=api_health,
        portal=portal_health,
        db=db_health,
        alembic=alembic_health,
        services=services_health,
        disk=disk_health,
        update_system=update_system_health,
        license=license_health,
    )

    maintenance_state = None
    if db.connected:
        if db_session is not None:
            maintenance_state = get_explicit_maintenance_state(db_session)
        else:
            with get_db_context() as db_for_maintenance:
                maintenance_state = get_explicit_maintenance_state(db_for_maintenance)
    else:
        maintenance_state = ExplicitMaintenanceState()
    resolved_mode = resolve_operational_mode(
        maintenance=maintenance_state,
        update_active=update.active,
        update_kind=update.active_kind,
        license_mode=license_summary.mode,
        degraded=bool(failed_reasons or degraded_reasons),
    )
    mode = resolved_mode.mode

    result = "failed" if failed_reasons else ("degraded" if degraded_reasons else "ok")

    try:
        with open("/proc/uptime", "r", encoding="utf-8") as fh:
            host_uptime = int(float(fh.read().split()[0]))
    except Exception:
        host_uptime = None

    return SystemStatus(
        collected_at=_now_iso(),
        result=result,
        version=version,
        mode=mode,
        maintenance_reason=resolved_mode.maintenance_reason,
        layout_mode=layout_mode,
        install_root=str(install_root),
        current_release=current_release,
        services=services,
        license=license_summary,
        update=update,
        backup=backup,
        health=health,
        disk=disk,
        uptime=UptimeSummary(host_seconds=host_uptime),
        db=db,
        degraded_reasons=degraded_reasons,
        failed_reasons=failed_reasons,
    )
