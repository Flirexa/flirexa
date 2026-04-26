from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ComponentState = Literal["ok", "degraded", "failed", "unknown"]
ResultState = Literal["ok", "degraded", "failed"]


@dataclass
class ServiceStatus:
    name: str
    unit: str
    enabled: bool | None
    active: bool
    substate: str | None = None
    status_text: str | None = None


@dataclass
class LicenseStatusSummary:
    mode: str
    status: str
    plan: str | None = None
    grace: bool = False
    readonly: bool = False
    validator_running: bool | None = None
    last_check_at: str | None = None
    server_reachable: bool | None = None
    message: str | None = None


@dataclass
class UpdateRecordSummary:
    id: int
    from_version: str
    to_version: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    is_rollback: bool = False
    error_message: str | None = None


@dataclass
class UpdateStatusSummary:
    active: bool
    active_kind: str | None = None
    active_id: int | None = None
    last_update: UpdateRecordSummary | None = None
    last_rollback: UpdateRecordSummary | None = None
    lock_present: bool = False
    staging_dirs: list[str] = field(default_factory=list)
    consistency_ok: bool = True
    consistency_message: str | None = None


@dataclass
class BackupStatusSummary:
    last_backup_at: str | None = None
    last_backup_path: str | None = None
    last_update_backup_path: str | None = None


@dataclass
class ComponentHealth:
    status: ComponentState
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthStatusSummary:
    api: ComponentHealth
    portal: ComponentHealth
    db: ComponentHealth
    alembic: ComponentHealth
    services: ComponentHealth
    disk: ComponentHealth
    update_system: ComponentHealth
    license: ComponentHealth


@dataclass
class DiskStatusSummary:
    install_root_free_mb: int | None = None
    backups_free_mb: int | None = None
    staging_free_mb: int | None = None
    install_root_ok: bool | None = None
    backups_ok: bool | None = None
    staging_ok: bool | None = None


@dataclass
class UptimeSummary:
    host_seconds: int | None = None


@dataclass
class DatabaseStatusSummary:
    connected: bool
    current_revision: str | None = None
    head_revision: str | None = None
    matches_head: bool | None = None
    error: str | None = None


@dataclass
class SystemStatus:
    collected_at: str
    result: ResultState
    version: str
    mode: str
    maintenance_reason: str | None
    layout_mode: str
    install_root: str
    current_release: str | None
    services: list[ServiceStatus]
    license: LicenseStatusSummary
    update: UpdateStatusSummary
    backup: BackupStatusSummary
    health: HealthStatusSummary
    disk: DiskStatusSummary
    uptime: UptimeSummary
    db: DatabaseStatusSummary
    degraded_reasons: list[str] = field(default_factory=list)
    failed_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
