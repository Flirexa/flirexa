from __future__ import annotations

import json

from src.modules.backup_cli import BackupCommandResult
from src.modules.restore_cli import RestoreCommandResult
from src.modules.service_cli import ServiceRestartResult
from src.modules.support_bundle import SupportBundleResult
from src.modules.system_status.models import SystemStatus


def _service_line(status: SystemStatus) -> list[str]:
    lines = []
    for svc in status.services:
        enabled = "enabled" if svc.enabled else ("disabled" if svc.enabled is False else "unknown")
        state = "active" if svc.active else (svc.status_text or "inactive")
        lines.append(f"  {svc.unit}: {state} ({enabled})")
    return lines


def render_status(status: SystemStatus) -> str:
    result = "SUCCESS" if status.result != "failed" else "FAILED"
    lines = [
        f"RESULT: {result}",
        f"Version: {status.version}",
        f"Mode: {status.mode}",
        *( [f"Maintenance reason: {status.maintenance_reason}"] if status.maintenance_reason else [] ),
        f"Layout: {status.layout_mode}",
        f"Install root: {status.install_root}",
        f"Current release: {status.current_release or 'n/a'}",
        "Services:",
        *_service_line(status),
        f"License: status={status.license.status}, mode={status.license.mode}, plan={status.license.plan or 'n/a'}",
        (
            f"Last update: {status.update.last_update.from_version} -> {status.update.last_update.to_version} "
            f"({status.update.last_update.status})"
            if status.update.last_update
            else "Last update: n/a"
        ),
        f"Last backup: {status.backup.last_backup_path or 'n/a'}",
        (
            f"Disk: install={status.disk.install_root_free_mb}MB, "
            f"backups={status.disk.backups_free_mb}MB, staging={status.disk.staging_free_mb}MB"
        ),
        f"Uptime: host={status.uptime.host_seconds if status.uptime.host_seconds is not None else 'n/a'}s",
    ]
    if status.failed_reasons:
        lines.append("Failed reasons:")
        lines.extend([f"  - {reason}" for reason in status.failed_reasons])
    if status.degraded_reasons:
        lines.append("Degraded reasons:")
        lines.extend([f"  - {reason}" for reason in status.degraded_reasons])
    lines.append("Logs: journalctl -u <service> ; backups/update_backups/*/apply.log")
    return "\n".join(lines)


def render_health(status: SystemStatus) -> str:
    result = "FAILED" if status.result == "failed" else ("DEGRADED" if status.result == "degraded" else "SUCCESS")
    health = status.health
    lines = [
        f"RESULT: {result}",
        f"API: {health.api.status.upper()}",
        f"Portal: {health.portal.status.upper()}",
        f"DB: {health.db.status.upper()}",
        f"Alembic: {health.alembic.status.upper()}",
        f"Services: {health.services.status.upper()}",
        f"Disk: {health.disk.status.upper()}",
        f"Update system: {health.update_system.status.upper()}",
        f"License: {health.license.status.upper()}",
    ]
    if status.failed_reasons:
        lines.append("Failed reasons:")
        lines.extend([f"  - {reason}" for reason in status.failed_reasons])
    if status.degraded_reasons:
        lines.append("Degraded reasons:")
        lines.extend([f"  - {reason}" for reason in status.degraded_reasons])
    return "\n".join(lines)


def render_license_status(status: SystemStatus) -> str:
    license_info = status.license
    result = "FAILED" if license_info.readonly else ("DEGRADED" if license_info.grace else "SUCCESS")
    lines = [
        f"RESULT: {result}",
        f"Status: {license_info.status}",
        f"Mode: {license_info.mode}",
        f"Plan: {license_info.plan or 'n/a'}",
        f"Validator: {'running' if license_info.validator_running else 'not-running' if license_info.validator_running is not None else 'unknown'}",
        f"Server reachable: {license_info.server_reachable if license_info.server_reachable is not None else 'unknown'}",
        f"Last check: {license_info.last_check_at or 'n/a'}",
        f"Grace: {'yes' if license_info.grace else 'no'}",
        f"Readonly: {'yes' if license_info.readonly else 'no'}",
        f"Message: {license_info.message or '-'}",
    ]
    return "\n".join(lines)


def render_services_status(status: SystemStatus) -> str:
    active = sum(1 for svc in status.services if svc.active)
    total = len(status.services)
    result = "FAILED" if status.health.services.status == "failed" else ("DEGRADED" if status.health.services.status == "degraded" else "SUCCESS")
    lines = [
        f"RESULT: {result}",
        f"Mode: {status.mode}",
        f"Services: {active}/{total} active",
    ]
    for svc in status.services:
        enabled = "enabled" if svc.enabled else ("disabled" if svc.enabled is False else "unknown")
        state = "active" if svc.active else (svc.status_text or "inactive")
        extra = f", substate={svc.substate}" if svc.substate else ""
        lines.append(f"- {svc.unit}: {state} ({enabled}{extra})")
    return "\n".join(lines)


def render_services_restart_result(result: ServiceRestartResult) -> str:
    status = "SUCCESS" if result.success else "FAILED"
    lines = [
        f"RESULT: {status}",
        f"Action: {'services restarted' if result.success else 'services restart failed'}",
        f"Scope: {result.requested_scope}",
        f"Restarted: {', '.join(result.restarted_units) if result.restarted_units else '-'}",
        f"Version: {result.version or 'n/a'}",
        f"Mode: {result.mode or 'n/a'}",
        (
            "Health: " + ", ".join(f"{key}={value}" for key, value in result.health_summary.items())
            if result.health_summary else
            "Health: n/a"
        ),
    ]
    if result.warnings:
        lines.append("Warnings:")
        lines.extend([f"  - {warning}" for warning in result.warnings])
    if result.error:
        lines.append(f"Error: {result.error}")
    return "\n".join(lines)


def render_support_bundle_result(result: SupportBundleResult) -> str:
    status = "SUCCESS" if result.success else "FAILED"
    lines = [
        f"RESULT: {status}",
        f"Archive: {result.archive_path}",
        f"Bundle size: {result.bundle_size_bytes} bytes",
        f"Sections included: {', '.join(result.sections_included) if result.sections_included else '-'}",
        f"Sections failed: {len(result.sections_failed)}",
    ]
    if result.sections_failed:
        lines.append("Errors:")
        lines.extend(
            [f"  - {item['section']}: {item['error']}" for item in result.sections_failed]
        )
    return "\n".join(lines)


def render_backup_result(result: BackupCommandResult) -> str:
    status = "SUCCESS" if result.success else "FAILED"
    lines = [
        f"RESULT: {status}",
        f"Action: {'backup created' if result.success else 'backup failed'}",
        f"Type: {result.backup_type}",
        f"Archive: {result.archive_path or 'n/a'}",
        f"Size: {result.size_bytes if result.size_bytes is not None else 'n/a'}",
        f"Version: {result.version or 'n/a'}",
        f"Mode: {result.mode or 'n/a'}",
        f"Included: {', '.join(result.included_sections) if result.included_sections else '-'}",
    ]
    if result.warnings:
        lines.append("Warnings:")
        lines.extend([f"  - {warning}" for warning in result.warnings])
    if result.error:
        lines.append(f"Error: {result.error}")
    return "\n".join(lines)


def render_restore_result(result: RestoreCommandResult) -> str:
    status = "SUCCESS" if result.success else "FAILED"
    lines = [
        f"RESULT: {status}",
        f"Action: {'restore completed' if result.success else 'restore failed'}",
        f"Archive: {result.archive_path or 'n/a'}",
        f"Backup ID: {result.backup_id or 'n/a'}",
        f"Version: {result.version or 'n/a'}",
        f"Mode: {result.mode or 'n/a'}",
        f"Restored: {', '.join(result.restored_sections) if result.restored_sections else '-'}",
        (
            "Health: " + ", ".join(f"{key}={value}" for key, value in result.health_summary.items())
            if result.health_summary else
            "Health: n/a"
        ),
    ]
    if result.maintenance_reason:
        lines.append(f"Maintenance reason: {result.maintenance_reason}")
    if result.warnings:
        lines.append("Warnings:")
        lines.extend([f"  - {warning}" for warning in result.warnings])
    if result.error:
        lines.append(f"Error: {result.error}")
    if result.log_hint:
        lines.append(f"Logs: {result.log_hint}")
    return "\n".join(lines)


def render_json(status: SystemStatus) -> str:
    return json.dumps(status.to_dict(), ensure_ascii=False, indent=2)
