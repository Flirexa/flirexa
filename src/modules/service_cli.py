from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field

from src.database.connection import get_db_context
from src.database.models import AuditAction, AuditLog
from src.modules.operational_mode import allowed_actions_for_mode
from src.modules.system_status.collector import collect_system_status


@dataclass
class ServiceRestartResult:
    success: bool
    action: str
    requested_scope: str
    restarted_units: list[str] = field(default_factory=list)
    version: str | None = None
    mode: str | None = None
    health_summary: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_HEALTH_RETRIES = 8
_HEALTH_INTERVAL_SECONDS = 2
_SYSTEMCTL_RESTART_TIMEOUT_SECONDS = 90


def _resolve_prefix(units: list[str]) -> str:
    for unit in units:
        if unit.endswith("-api"):
            return unit[: -len("-api")]
    return "vpnmanager"


def _restartable_units(status, scope: str) -> list[str]:
    service_map = {svc.unit: svc for svc in status.services}
    prefix = _resolve_prefix(list(service_map))

    candidates_by_scope = {
        "api": [f"{prefix}-api"],
        "portal": [f"{prefix}-client-portal"],
        "worker": [f"{prefix}-worker"],
        "bots": [f"{prefix}-admin-bot", f"{prefix}-client-bot"],
        "all": [
            f"{prefix}-api",
            f"{prefix}-worker",
            f"{prefix}-admin-bot",
            f"{prefix}-client-bot",
            f"{prefix}-client-portal",
        ],
    }

    units: list[str] = []
    for unit in candidates_by_scope[scope]:
        svc = service_map.get(unit)
        if not svc:
            continue
        if svc.enabled is True or svc.active:
            units.append(unit)
    return units


def _collect_health_summary(status) -> dict[str, str]:
    return {
        "api": status.health.api.status,
        "portal": status.health.portal.status,
        "db": status.health.db.status,
        "services": status.health.services.status,
        "license": status.health.license.status,
        "result": status.result,
    }


def create_services_restart_command(*, scope: str = "all") -> ServiceRestartResult:
    status = collect_system_status()

    if not shutil.which("systemctl"):
        return ServiceRestartResult(
            success=False,
            action="services_restart",
            requested_scope=scope,
            version=status.version,
            mode=status.mode,
            error="systemctl is not available",
        )

    if not allowed_actions_for_mode(status.mode).restart_services:
        return ServiceRestartResult(
            success=False,
            action="services_restart",
            requested_scope=scope,
            version=status.version,
            mode=status.mode,
            error=f"Service restart is blocked in mode '{status.mode}'",
        )

    units = _restartable_units(status, scope)
    if not units:
        return ServiceRestartResult(
            success=False,
            action="services_restart",
            requested_scope=scope,
            version=status.version,
            mode=status.mode,
            error=f"No managed services matched restart scope '{scope}'",
        )

    restarted: list[str] = []
    try:
        for unit in units:
            subprocess.run(
                ["systemctl", "restart", unit],
                check=True,
                capture_output=True,
                text=True,
                timeout=_SYSTEMCTL_RESTART_TIMEOUT_SECONDS,
            )
            restarted.append(unit)
    except subprocess.CalledProcessError as exc:
        return ServiceRestartResult(
            success=False,
            action="services_restart",
            requested_scope=scope,
            restarted_units=restarted,
            version=status.version,
            mode=status.mode,
            error=(exc.stderr or exc.stdout or str(exc)).strip(),
        )
    except Exception as exc:
        return ServiceRestartResult(
            success=False,
            action="services_restart",
            requested_scope=scope,
            restarted_units=restarted,
            version=status.version,
            mode=status.mode,
            error=str(exc),
        )

    post_status = None
    for _ in range(_HEALTH_RETRIES):
        time.sleep(_HEALTH_INTERVAL_SECONDS)
        post_status = collect_system_status()
        if post_status.health.services.status != "failed" and post_status.health.api.status != "failed":
            break
    if post_status is None:
        post_status = collect_system_status()

    with get_db_context() as db:
        db.add(
            AuditLog(
                action=AuditAction.CONFIG_CHANGE,
                target_type="services",
                target_name=",".join(restarted),
                details={
                    "operation": "restart",
                    "scope": scope,
                    "restarted_units": restarted,
                    "source": "cli",
                    "actor": "vpnmanager",
                    "mode_before": status.mode,
                    "mode_after": post_status.mode,
                    "health_after": _collect_health_summary(post_status),
                },
            )
        )

    warnings: list[str] = []
    success = post_status.health.services.status != "failed" and post_status.health.api.status != "failed"
    if post_status.result == "degraded":
        warnings.extend(post_status.degraded_reasons)

    return ServiceRestartResult(
        success=success,
        action="services_restart",
        requested_scope=scope,
        restarted_units=restarted,
        version=post_status.version,
        mode=post_status.mode,
        health_summary=_collect_health_summary(post_status),
        warnings=warnings,
        error=None if success else "Post-restart health checks failed",
    )
