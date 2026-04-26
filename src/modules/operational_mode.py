from __future__ import annotations

import os

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import String, bindparam, cast, text
from sqlalchemy.orm import Session

from src.database.connection import get_db_context
from src.database.models import AuditAction, AuditLog, SystemConfig, UpdateHistory, UpdateStatus
from src.modules.license.online_validator import get_online_status, is_license_blocked
try:
    from src.modules.license.online_validator import _warmup_from_cache as _license_warmup_from_cache
except ImportError:  # pragma: no cover
    _license_warmup_from_cache = None


OperationalMode = Literal[
    "normal",
    "maintenance",
    "update_in_progress",
    "rollback_in_progress",
    "degraded",
    "license_grace",
    "license_expired_readonly",
]
RequestClass = Literal["readonly", "auth", "recovery", "support", "business_mutation", "system_mutation"]


@dataclass
class ExplicitMaintenanceState:
    enabled: bool = False
    reason: str | None = None
    updated_at: str | None = None


@dataclass
class ResolvedOperationalMode:
    mode: OperationalMode
    maintenance_reason: str | None = None
    source: str = "resolver"


@dataclass
class AllowedActions:
    mutate_business: bool
    run_updates: bool
    restart_services: bool
    backup: bool
    restore: bool
    support_bundle: bool
    toggle_maintenance: bool


@dataclass
class ModeBanner:
    mode: OperationalMode
    reason: str | None
    banner_severity: Literal["info", "warning", "critical"]
    allowed_actions: AllowedActions

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "banner_severity": self.banner_severity,
            "allowed_actions": asdict(self.allowed_actions),
        }


_ACTIVE_UPDATE_STATES = [
    UpdateStatus.DOWNLOADING.name,
    UpdateStatus.DOWNLOADED.name,
    UpdateStatus.VERIFIED.name,
    UpdateStatus.READY_TO_APPLY.name,
    UpdateStatus.APPLYING.name,
    UpdateStatus.ROLLING_BACK.name,
    UpdateStatus.ROLLBACK_REQUIRED.name,
]

_RECOVERY_MUTATING_PREFIXES = (
    "/api/v1/updates",
    "/api/v1/system/restart",
    "/api/v1/system/license",
    "/api/v1/system/activation",
    "/api/v1/backup",
)

_AUTH_MUTATING_PREFIXES = (
    "/api/v1/auth/",
    "/client-portal/auth/",
)

_SYSTEM_MUTATION_PREFIXES = (
    "/api/v1/system/",
)


def get_explicit_maintenance_state(db: Session) -> ExplicitMaintenanceState:
    rows = (
        db.query(SystemConfig)
        .filter(SystemConfig.key.in_(["maintenance_mode", "maintenance_reason", "maintenance_updated_at"]))
        .all()
    )
    kv = {row.key: row.value for row in rows}
    enabled = (kv.get("maintenance_mode") or "").lower() in {"1", "true", "yes", "on"}
    return ExplicitMaintenanceState(
        enabled=enabled,
        reason=kv.get("maintenance_reason") or None,
        updated_at=kv.get("maintenance_updated_at") or None,
    )


def get_active_update_state(db: Session) -> tuple[bool, str | None, int | None]:
    stmt = text(
        """
        SELECT id,
               CAST(status AS TEXT) AS status,
               is_rollback
        FROM update_history
        WHERE CAST(status AS TEXT) IN :states
        ORDER BY started_at DESC
        LIMIT 1
        """
    ).bindparams(bindparam("states", expanding=True))
    row = db.execute(stmt, {"states": list(_ACTIVE_UPDATE_STATES)}).mappings().first()
    if not row:
        return False, None, None
    status = row.get("status")
    kind = "rollback" if row.get("is_rollback") or status == UpdateStatus.ROLLING_BACK.name else "update"
    return True, kind, row.get("id")


def derive_license_mode() -> str:
    # No LICENSE_KEY → FREE (open-core) mode, treated as normal.
    if not os.getenv("LICENSE_KEY", "").strip():
        return "normal"

    # If LicenseManager fell back to FREE (e.g. invalid key), treat as normal.
    # FREE never has license_grace/license_expired_readonly states.
    try:
        from src.modules.license.manager import get_license_manager
        if get_license_manager().is_free():
            return "normal"
    except Exception:
        pass

    if _license_warmup_from_cache is not None:
        try:
            _license_warmup_from_cache()
        except Exception:
            pass
    raw = get_online_status()
    blocked, _ = is_license_blocked()
    if blocked:
        return "license_expired_readonly"
    if raw.get("status") == "ok" and raw.get("server_reachable") is False:
        return "license_grace"
    return "normal"


def resolve_operational_mode(
    *,
    maintenance: ExplicitMaintenanceState,
    update_active: bool,
    update_kind: str | None,
    license_mode: str,
    degraded: bool,
) -> ResolvedOperationalMode:
    if update_active and update_kind == "rollback":
        return ResolvedOperationalMode(mode="rollback_in_progress", source="update_state")
    if update_active:
        return ResolvedOperationalMode(mode="update_in_progress", source="update_state")
    if maintenance.enabled:
        return ResolvedOperationalMode(mode="maintenance", maintenance_reason=maintenance.reason, source="system_config")
    if license_mode == "license_expired_readonly":
        return ResolvedOperationalMode(mode="license_expired_readonly", source="license")
    if license_mode == "license_grace":
        return ResolvedOperationalMode(mode="license_grace", source="license")
    if degraded:
        return ResolvedOperationalMode(mode="degraded", source="health")
    return ResolvedOperationalMode(mode="normal", source="default")


def resolve_operational_mode_from_db(db: Session, *, degraded: bool = False) -> ResolvedOperationalMode:
    maintenance = get_explicit_maintenance_state(db)
    update_active, update_kind, _ = get_active_update_state(db)
    license_mode = derive_license_mode()
    return resolve_operational_mode(
        maintenance=maintenance,
        update_active=update_active,
        update_kind=update_kind,
        license_mode=license_mode,
        degraded=degraded,
    )


def set_maintenance_mode(enabled: bool, *, reason: str | None, source: str, actor: str = "cli") -> ResolvedOperationalMode:
    with get_db_context() as db:
        old_mode = resolve_operational_mode_from_db(db, degraded=False)
        state = get_explicit_maintenance_state(db)
        now = datetime.now(timezone.utc).isoformat()

        existing_rows = {
            row.key: row
            for row in db.query(SystemConfig)
            .filter(SystemConfig.key.in_(["maintenance_mode", "maintenance_reason", "maintenance_updated_at"]))
            .all()
        }

        def upsert(key: str, value: str, value_type: str = "string", description: str | None = None):
            row = existing_rows.get(key)
            if row is None:
                row = SystemConfig(key=key, value=value, value_type=value_type, description=description)
                db.add(row)
                existing_rows[key] = row
            else:
                row.value = value
                row.value_type = value_type
                if description is not None:
                    row.description = description

        upsert("maintenance_mode", "true" if enabled else "false", "bool", "Explicit maintenance mode toggle")
        upsert("maintenance_reason", (reason or "") if enabled else "", "string", "Maintenance mode reason")
        upsert("maintenance_updated_at", now, "string", "Last maintenance toggle timestamp")

        new_mode = resolve_operational_mode(
            maintenance=ExplicitMaintenanceState(enabled=enabled, reason=reason if enabled else None, updated_at=now),
            update_active=False,
            update_kind=None,
            license_mode=derive_license_mode(),
            degraded=False,
        )

        db.add(
            AuditLog(
                action=AuditAction.CONFIG_CHANGE,
                target_type="operational_mode",
                target_name="system",
                details={
                    "old_mode": old_mode.mode,
                    "new_mode": new_mode.mode,
                    "reason": reason if enabled else None,
                    "source": source,
                    "actor": actor,
                    "maintenance_enabled": enabled,
                    "previous_reason": state.reason,
                },
            )
        )

    return new_mode


def mode_blocks_mutation(mode: str) -> bool:
    return mode in {"maintenance", "update_in_progress", "rollback_in_progress", "license_expired_readonly"}


def classify_api_request(path: str, method: str) -> RequestClass:
    if method in {"GET", "HEAD", "OPTIONS"}:
        return "readonly"

    if any(path.startswith(prefix) for prefix in _AUTH_MUTATING_PREFIXES):
        return "auth"
    if any(path.startswith(prefix) for prefix in _RECOVERY_MUTATING_PREFIXES):
        return "recovery"
    if any(path.startswith(prefix) for prefix in _SYSTEM_MUTATION_PREFIXES):
        return "system_mutation"
    return "business_mutation"


def allowed_actions_for_mode(mode: OperationalMode) -> AllowedActions:
    if mode == "maintenance":
        return AllowedActions(
            mutate_business=False,
            run_updates=True,
            restart_services=True,
            backup=True,
            restore=True,
            support_bundle=True,
            toggle_maintenance=True,
        )
    if mode in {"update_in_progress", "rollback_in_progress"}:
        return AllowedActions(
            mutate_business=False,
            run_updates=False,
            restart_services=False,
            backup=False,
            restore=False,
            support_bundle=True,
            toggle_maintenance=False,
        )
    if mode == "license_expired_readonly":
        return AllowedActions(
            mutate_business=False,
            run_updates=True,
            restart_services=True,
            backup=True,
            restore=True,
            support_bundle=True,
            toggle_maintenance=True,
        )
    return AllowedActions(
        mutate_business=True,
        run_updates=True,
        restart_services=True,
        backup=True,
        restore=True,
        support_bundle=True,
        toggle_maintenance=True,
    )


def build_mode_banner(mode: OperationalMode, *, reason: str | None = None) -> ModeBanner:
    severity: Literal["info", "warning", "critical"] = "info"
    if mode in {"maintenance", "license_grace", "degraded"}:
        severity = "warning"
    if mode in {"update_in_progress", "rollback_in_progress", "license_expired_readonly"}:
        severity = "critical"
    return ModeBanner(
        mode=mode,
        reason=reason,
        banner_severity=severity,
        allowed_actions=allowed_actions_for_mode(mode),
    )


def is_request_allowed(mode: OperationalMode, path: str, method: str) -> tuple[bool, str | None]:
    request_class = classify_api_request(path, method)
    if request_class in {"readonly", "auth"}:
        return True, None
    if mode in {"normal", "degraded", "license_grace"}:
        return True, None
    if mode in {"maintenance", "update_in_progress", "rollback_in_progress"}:
        if request_class == "recovery":
            return True, None
        return False, f"Operation class '{request_class}' is blocked in mode '{mode}'"
    if mode == "license_expired_readonly":
        if request_class in {"recovery", "support"}:
            return True, None
        return False, f"Operation class '{request_class}' is blocked in mode '{mode}'"
    return True, None
