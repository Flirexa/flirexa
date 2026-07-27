"""
System Routes — status, logs, configuration, branding
"""

from typing import Optional, List, Literal, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import platform
import psutil
import os
import uuid
from pathlib import Path
import shutil
import subprocess
import re

from ...database.connection import get_db, check_db_connection
from ...database.models import AuditLog, AuditAction
from ...core.management import ManagementCore
from ...modules.branding import get_all_branding, set_branding, get_app_name, BRANDING_DEFAULTS
from ...modules.operational_mode import (
    build_mode_banner,
    resolve_operational_mode_from_db,
)
from ...modules.system_status.collector import collect_system_status
from ...utils.runtime_paths import get_app_version
from ..middleware.license_gate import require_license_feature


router = APIRouter()

# Feature-gated dependencies for paid-tier endpoints in this router.
_white_label_gate = Depends(require_license_feature("white_label_basic"))
_auto_backup_gate = Depends(require_license_feature("auto_backup"))


# ============================================================================
# SCHEMAS
# ============================================================================

class SystemStatusResponse(BaseModel):
    """System status response"""
    status: str
    version: str
    uptime: Optional[str]
    database: dict
    servers: dict
    clients: dict
    system: dict
    traffic: Optional[dict] = None
    expiry: Optional[dict] = None


class AuditLogResponse(BaseModel):
    """Audit log entry response"""
    id: int
    user_id: Optional[int]
    user_type: str
    action: str
    target_type: Optional[str]
    target_id: Optional[int]
    target_name: Optional[str]
    details: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class OperationalModeResponse(BaseModel):
    mode: str
    reason: Optional[str] = None
    banner_severity: str
    allowed_actions: dict
    degraded_reasons: List[str] = Field(default_factory=list)


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/status", response_model=SystemStatusResponse)
def get_system_status(
    db: Session = Depends(get_db)
):
    """
    Get overall system status including servers, clients, and resources.

    Declared `def` (not `async`): the body is all blocking work — sync
    SQLAlchemy aggregates + psutil + check_db_connection. As `async def` these
    ran on the single event loop, so the frequently-polled dashboard status
    endpoint serialized against every other async request. As a sync def it
    runs in the threadpool. Paired with the DB-side traffic aggregate in
    ManagementCore.get_system_status (no more per-client Fernet decrypt), this
    keeps the dashboard fast regardless of client count.
    """
    core = ManagementCore(db)

    # Get system info
    system_status = core.get_system_status()

    # Get system resources
    cpu_percent = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # Database status
    db_connected = check_db_connection()

    return SystemStatusResponse(
        status="healthy" if db_connected else "degraded",
        version=get_app_version(),
        uptime=None,  # Would track app start time
        database={
            "connected": db_connected,
            "type": "postgresql",
        },
        servers=system_status["servers"],
        clients=system_status["clients"],
        system={
            "platform": platform.system(),
            "python_version": platform.python_version(),
            "cpu_percent": cpu_percent,
            "memory_total_gb": round(memory.total / (1024**3), 2),
            "memory_used_gb": round(memory.used / (1024**3), 2),
            "memory_percent": memory.percent,
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_percent": round(disk.percent, 1),
        },
        traffic=system_status.get("traffic"),
        expiry=system_status.get("expiry"),
    )


@router.get("/dashboard")
def get_dashboard_batch(db: Session = Depends(get_db)):
    """
    ONE round-trip for the admin dashboard's initial load.

    The dashboard used to fire 5 parallel requests (status / clients /
    servers / revenue / charts). Each carried its own HTTP+auth+DB-session
    overhead, and the whole screen waited for the slowest. This endpoint
    reuses the exact same handler functions on a single DB session, so the
    payload shapes are byte-identical to the individual endpoints (which
    stay available for everything else).

    `revenue`/`charts` degrade to empty defaults on error instead of
    failing the whole dashboard — mirrors the frontend's old per-call
    `.catch()` guards. `status`/`clients`/`servers` are the core: if those
    fail, a 500 here is correct (the old Promise.all failed the same way).

    Declared `def`: everything inside is sync (SQLAlchemy + psutil), so it
    belongs on the threadpool, not the event loop.
    """
    from loguru import logger
    from .clients import list_clients as _list_clients
    from .servers import list_servers as _list_servers

    status = get_system_status(db=db)
    clients = _list_clients(
        server_id=None, enabled_only=False, q=None, limit=10, offset=0, db=db
    )
    servers = _list_servers(include_offline=True, limit=100, offset=0, db=db)

    revenue: dict = {}
    charts: dict = {
        "revenue_trend": [], "user_trend": [],
        "sub_distribution": {}, "payment_methods": {},
    }
    try:
        from .portal_users import get_revenue_stats as _rev
        revenue = _rev(db=db)
    except Exception as e:
        logger.warning(f"dashboard batch: revenue stats failed: {e}")
    try:
        from .portal_users import get_chart_data as _charts
        charts = _charts(db=db)
    except Exception as e:
        logger.warning(f"dashboard batch: chart data failed: {e}")

    return {
        "status": status,
        "clients": clients,
        "servers": servers,
        "revenue": revenue,
        "charts": charts,
    }


@router.get("/operational-mode", response_model=OperationalModeResponse)
async def get_operational_mode(db: Session = Depends(get_db)):
    status = collect_system_status(db_session=db)
    resolved = resolve_operational_mode_from_db(db, degraded=bool(status.failed_reasons or status.degraded_reasons))
    reason = resolved.maintenance_reason
    if not reason and status.failed_reasons:
        reason = "; ".join(status.failed_reasons[:3])
    elif not reason and status.degraded_reasons:
        reason = "; ".join(status.degraded_reasons[:3])
    banner = build_mode_banner(resolved.mode, reason=reason)
    payload = banner.to_dict()
    payload["degraded_reasons"] = status.degraded_reasons
    return payload


@router.get("/logs", response_model=List[AuditLogResponse])
def get_audit_logs(
    action: Optional[str] = Query(None, description="Filter by action type"),
    target_type: Optional[str] = Query(None, description="Filter by target type"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Get audit logs with optional filtering
    """
    query = db.query(AuditLog)

    if action:
        try:
            action_enum = AuditAction(action)
            query = query.filter(AuditLog.action == action_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    if target_type:
        query = query.filter(AuditLog.target_type == target_type)

    logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    return logs


@router.get("/logs/actions")
async def get_audit_action_types():
    """
    Get list of available audit action types
    """
    return {
        "actions": [action.value for action in AuditAction]
    }


@router.get("/app-logs")
async def get_app_logs(
    component: Literal["api", "worker", "agent"] = Query("api", description="Log component"),
    lines: int = Query(100, ge=1, le=1000, description="Number of lines to return"),
    errors_only: bool = Query(False, description="Return only ERROR/CRITICAL entries"),
):
    """
    Get recent structured application logs from /var/log/vpnmanager/{component}.log.
    Returns up to *lines* most recent JSON log entries (oldest first).
    """
    from ...modules.log_config import get_recent_logs
    entries = get_recent_logs(component=component, lines=lines, errors_only=errors_only)
    return {"component": component, "lines": len(entries), "entries": entries}


@router.get("/app-logs/errors")
async def get_app_logs_errors(
    component: Literal["api", "worker", "agent"] = Query("api", description="Log component"),
    lines: int = Query(100, ge=1, le=1000, description="Number of error entries to return"),
):
    """
    Get recent ERROR and CRITICAL log entries from /var/log/vpnmanager/{component}.log.
    Convenience shortcut for /app-logs?errors_only=true.
    """
    from ...modules.log_config import get_recent_logs
    entries = get_recent_logs(component=component, lines=lines, errors_only=True)
    return {"component": component, "lines": len(entries), "entries": entries}


@router.get("/info")
async def get_system_info(db: Session = Depends(get_db)):
    """
    Get system information
    """
    return {
        "name": get_app_name(db),
        "version": get_app_version(),
        "api_version": "v1",
        "platform": platform.system(),
        "platform_release": platform.release(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "architecture": platform.machine(),
    }


@router.get("/health")
def health_check(
    db: Session = Depends(get_db)
):
    """
    Detailed health check
    """
    checks = {
        "database": False,
        "wireguard": False,
    }

    # Check database
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass

    # Check WireGuard
    try:
        import subprocess
        result = subprocess.run(
            ["wg", "show"],
            capture_output=True,
            timeout=5
        )
        checks["wireguard"] = result.returncode == 0
    except Exception:
        pass

    all_healthy = all(checks.values())

    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "checks": checks,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/stats/traffic")
async def get_traffic_stats(
    server_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get traffic statistics summary
    """
    core = ManagementCore(db)
    return core.traffic.get_traffic_summary(server_id)


@router.get("/stats/expiry")
async def get_expiry_stats(
    server_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get expiry statistics summary
    """
    core = ManagementCore(db)
    return core.timers.get_expiry_summary(server_id)


@router.post("/check-limits")
async def trigger_limit_check(
    db: Session = Depends(get_db)
):
    """
    Manually trigger limit checking (expiry and traffic)
    """
    core = ManagementCore(db)
    result = core.check_all_limits()

    return {
        "message": "Limit check completed",
        "expired_clients": result["expired_clients"],
        "traffic_exceeded_clients": result["traffic_exceeded_clients"],
        "total_disabled": result["total_disabled"],
    }


@router.get("/expiring-soon")
async def get_expiring_soon(
    days: int = Query(7, ge=1, le=90),
    server_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get clients expiring within specified days
    """
    core = ManagementCore(db)
    clients = core.timers.get_expiring_soon(within_days=days, server_id=server_id)

    return {
        "within_days": days,
        "count": len(clients),
        "clients": [
            {
                "id": c.id,
                "name": c.name,
                "expiry_date": c.expiry_date.isoformat() if c.expiry_date else None,
            }
            for c in clients
        ]
    }


@router.get("/config")
async def get_config():
    """
    Get non-sensitive configuration
    """
    from ..routes import client_portal
    return {
        "api": {
            "version": "v1",
            "port": int(os.getenv("API_PORT", 10086)),
        },
        "wireguard": {
            "default_interface": os.getenv("WG_INTERFACE", "wg0"),
            "config_path": os.getenv("WG_CONFIG_PATH", "/etc/wireguard/wg0.conf"),
        },
        "features": {
            "payment_enabled": os.getenv("PAYMENT_ENABLED", "false").lower() == "true",
            "client_bot_enabled": os.getenv("CLIENT_BOT_ENABLED", "false").lower() == "true",
            "license_check_enabled": os.getenv("LICENSE_CHECK_ENABLED", "true").lower() == "true",
        },
        "cryptopay": {
            "configured": client_portal.cryptopay_adapter is not None,
            "testnet": os.getenv("CRYPTOPAY_TESTNET", "false").lower() == "true",
        }
    }


# ============================================================================
# LICENSE
# ============================================================================

@router.get("/activation")
async def get_activation_info():
    """
    Public endpoint — returns machine hardware ID (activation code).
    No authentication required so the activation screen can display it
    before the user has entered a license key.
    """
    from ...modules.license.manager import get_license_manager
    mgr = get_license_manager()
    return {
        "activation_code": mgr.get_server_id(),
        "instructions": (
            "Send this activation code to your vendor. "
            "You will receive a license key bound to this machine."
        ),
    }


@router.get("/license")
def get_license_status(db: Session = Depends(get_db)):
    """Get current license status with usage counters and activation info."""
    from ...modules.license.manager import get_license_manager
    from ...database.models import Client, Server
    mgr = get_license_manager()
    status = mgr.get_status()

    # Normalize: add `type` alias for `license_type` so the frontend can use either
    status["type"] = status.get("license_type", "trial")

    # Current usage from DB (for compliance bars in UI)
    try:
        status["current_clients"] = db.query(Client).count()
        status["current_servers"] = db.query(Server).count()
    except Exception:
        status["current_clients"] = 0
        status["current_servers"] = 0

    # Activation code used (stored in env) — masked for display
    raw_code = os.getenv("ACTIVATION_CODE", "")
    if raw_code:
        # Show first group, mask the rest: ABCD-****-****-****
        parts = raw_code.replace("-", "")
        if len(parts) >= 4:
            status["activation_code_masked"] = parts[:4] + "-****-****-****"
        else:
            status["activation_code_masked"] = "****-****-****-****"
    else:
        status["activation_code_masked"] = ""

    return status


class LicenseActivateRequest(BaseModel):
    license_key: str


@router.post("/license")
async def activate_license(data: LicenseActivateRequest):
    """Activate the panel.

    Accepts EITHER a full RSA-signed license key (long base64.signature
    blob) OR a short activation code (XXXX-XXXX-XXXX-XXXX). For codes
    we round-trip the license server's POST /api/activate to exchange
    the code for a license key bound to this machine's hardware id,
    then persist it the same way the legacy path does.

    Previously this endpoint took only `license_key`, fed garbage to
    LicenseManager, fell through to a FREE fallback, and the
    `type == "trial"` guard never matched — so ANY input came back as
    `{"status":"activated"}`. Both classes of input now go through a
    real signature check (locally for keys, server-side for codes).
    """
    from ...modules.license.manager import LicenseManager, reset_license_manager

    raw = (data.license_key or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="License key or activation code is required.")

    # ── Branch on input shape ────────────────────────────────────────
    # Activation codes normalise to exactly 16 uppercase alphanumeric
    # chars (see license_server _normalize_code). A signed license key
    # always contains a '.' separator AND is many hundreds of chars
    # long, so the two are unambiguous.
    code_norm = re.sub(r"[^A-Z0-9]", "", raw.upper())
    looks_like_code = (
        "." not in raw
        and len(code_norm) == 16
        and len(raw) <= 64
    )

    if looks_like_code:
        # Round-trip /api/activate on the license server.
        import httpx
        from ...modules.license.online_validator import get_hardware_id
        from ...modules.license.server_config import get_server_urls

        primary, backup = get_server_urls()
        if not primary and not backup:
            raise HTTPException(status_code=503, detail="License server not configured.")

        hw_id   = get_hardware_id()
        payload = {
            "activation_code": code_norm,
            "hardware_id":     hw_id,
            "client_version":  os.environ.get("APP_VERSION", ""),
        }
        last_error = None
        license_key_from_server = None
        for base_url in (primary, backup):
            if not base_url:
                continue
            url = f"{base_url.rstrip('/')}/api/activate"
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    license_key_from_server = (resp.json() or {}).get("license_key")
                    if license_key_from_server:
                        break
                    last_error = "License server returned no key"
                else:
                    # Surface the server's error verbatim so the user sees
                    # "Code already used" / "Code expired" / etc instead
                    # of a generic 400.
                    detail = ""
                    try: detail = (resp.json() or {}).get("detail") or ""
                    except Exception: pass
                    last_error = detail or f"License server returned {resp.status_code}"
                    # 4xx is terminal — code is bad. Don't bother with backup.
                    if 400 <= resp.status_code < 500:
                        raise HTTPException(status_code=400, detail=last_error)
            except HTTPException:
                raise
            except Exception as exc:
                last_error = f"Could not reach {base_url}: {exc}"
                continue
        if not license_key_from_server:
            raise HTTPException(status_code=502, detail=last_error or "Activation failed.")
        actual_key = license_key_from_server
    else:
        actual_key = raw

    # ── Validate the resolved key locally ────────────────────────────
    mgr  = LicenseManager(actual_key)
    info = mgr.validate_license()
    msg  = info.validation_message or ""
    if "Invalid" in msg or "invalid" in msg:
        raise HTTPException(status_code=400, detail=msg or "Invalid license key")
    # Belt-and-suspenders: if validation silently fell back to FREE,
    # the key was rejected even if the message is friendly.
    if info.type.value == "free":
        raise HTTPException(status_code=400, detail=msg or "License key rejected")
    data.license_key = actual_key

    # Save to .env
    env_path = _find_env_file()
    _update_env_file(env_path, {"LICENSE_KEY": data.license_key, "LICENSE_CHECK_ENABLED": "true"})
    os.environ["LICENSE_KEY"] = data.license_key
    os.environ["LICENSE_CHECK_ENABLED"] = "true"

    # Reset global manager to pick up new key
    reset_license_manager()

    # Reconcile fleet to the new tier — un-suspends servers that were parked
    # because of a previous downgrade, or suspends excess if the new key is
    # somehow narrower than the old one (e.g. switched from Business to FREE).
    try:
        from ...modules.license.enforcement import reconcile as _lic_reconcile
        _lic_reconcile()
    except Exception as exc:
        from loguru import logger
        logger.warning("License enforcement reconcile after activation failed: {}", exc)

    return {
        "status": "activated",
        "license": mgr.get_status(),
    }


class LicenseReplayRequest(BaseModel):
    activation_code: str


@router.post("/license/replay")
async def replay_license(data: LicenseReplayRequest):
    """
    Re-fetch the license key for a previously activated code.

    Use case: customer's original activation succeeded server-side but the
    license_key didn't land in .env (network blip, lost stdout, crash). With
    matching hardware_id the license-server returns the same payload with a
    fresh signature. No code is consumed.

    Server-side guards: HW-binding check, per-code 3/24h rate limit, License
    must be active and not revoked. See /api/activate/replay on license-server.
    """
    import httpx
    from ...modules.license.online_validator import get_hardware_id
    from ...modules.license.server_config import get_server_urls
    from ...modules.license.manager import LicenseManager, reset_license_manager

    activation_code = (data.activation_code or "").strip()
    if not activation_code:
        raise HTTPException(status_code=422, detail="Activation code is required.")

    primary, backup = get_server_urls()
    if not primary and not backup:
        raise HTTPException(status_code=503, detail="License server not configured.")

    hw_id   = get_hardware_id()
    payload = {"activation_code": activation_code, "hardware_id": hw_id}

    # Try primary, then backup. Both must speak /api/activate/replay.
    last_error = None
    for base_url in (primary, backup):
        if not base_url:
            continue
        url = f"{base_url.rstrip('/')}/api/activate/replay"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                resp_json = resp.json()
                license_key = resp_json.get("license_key")
                if not license_key:
                    last_error = "License server returned no key"
                    continue

                # Validate signature locally before persisting. Same
                # bug as /license used to have — falls back to FREE on
                # invalidity, so we check the message + final type.
                mgr  = LicenseManager(license_key)
                info = mgr.validate_license()
                _m = info.validation_message or ""
                if "Invalid" in _m or "invalid" in _m or info.type.value == "free":
                    raise HTTPException(status_code=400, detail=_m or "License key rejected")

                env_path = _find_env_file()
                _update_env_file(env_path, {
                    "LICENSE_KEY":           license_key,
                    "LICENSE_CHECK_ENABLED": "true",
                    "ACTIVATION_CODE":       activation_code,
                })
                os.environ["LICENSE_KEY"]           = license_key
                os.environ["LICENSE_CHECK_ENABLED"] = "true"
                os.environ["ACTIVATION_CODE"]      = activation_code

                reset_license_manager()

                try:
                    from ...modules.license.enforcement import reconcile as _lic_reconcile
                    _lic_reconcile()
                except Exception as exc:
                    from loguru import logger
                    logger.warning("License enforcement reconcile after replay failed: {}", exc)

                return {
                    "status":  "replayed",
                    "license": mgr.get_status(),
                    "source":  base_url,
                }

            # Non-200 — surface the server's error for actionable UI message
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text or f"HTTP {resp.status_code}"
            # 403/404/409/429 are user-actionable — bubble them up directly
            if resp.status_code in (403, 404, 409, 422, 429):
                raise HTTPException(status_code=resp.status_code, detail=detail)
            last_error = f"{base_url}: HTTP {resp.status_code} — {detail}"
        except HTTPException:
            raise
        except Exception as exc:
            last_error = f"{base_url}: {exc}"
            continue

    raise HTTPException(
        status_code=502,
        detail=last_error or "Could not reach license server.",
    )


# ── License Server ────────────────────────────────────────────────────────────

@router.get("/license-server")
async def get_license_server_status():
    """Get current license server configuration and online validation state."""
    from ...modules.license.server_config import get_server_info
    from ...modules.license.online_validator import get_online_status, _SERVER_URL, _SERVER_URL_BACKUP
    info   = get_server_info()
    online = get_online_status()
    return {
        **info,
        "server_reachable": online.get("server_reachable", False),
        "last_check":       online.get("last_check"),
        "online_status":    online.get("status"),
    }


class LicenseMigrationRequest(BaseModel):
    code: str


@router.post("/license-migration")
async def apply_license_migration(data: LicenseMigrationRequest):
    """
    Apply a server migration code issued by the vendor.
    Allows pointing the product at new license servers without re-installing.
    The code is RSA-PSS signed (vendor private key), time-limited, nonce-protected.
    """
    from ...modules.license.server_config import apply_migration_code
    from ...modules.license.online_validator import reload_server_urls

    success, message = apply_migration_code(data.code.strip())
    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Reload validator with new URLs immediately
    reload_server_urls()
    return {"status": "applied", "message": message}


# ── Customer self-service license transfer (lifetime_protected) ──────────────
#
# Distinct from /license-migration above: that one re-points the panel at
# new license servers (vendor-issued). These two endpoints let the *customer*
# move their lifetime_protected license to a new HW without contacting us.
#
# Flow:
#   1. Old panel:  POST /license/transfer/initiate   → gets MIGRATE-… code
#                  Old panel starts a 3-day countdown to self-decommission.
#   2. New panel:  POST /license/transfer/apply  + LICENSE_KEY in env
#                  Panel verifies code offline, persists pending receipt,
#                  next heartbeat carries it as proof of legitimate move.

@router.post("/license/transfer/initiate")
async def license_transfer_initiate():
    """Generate a one-time code that authorizes moving this license to a
    new server. Once called, this server self-decommissions in 3 days —
    plan to have the new server up before then.

    Only works for `lifetime_protected` licenses; other types either
    don't move (subscription — contact vendor) or don't need a code
    (lifetime — just copy LICENSE_KEY)."""
    from ...modules.license.migration_code import generate_migration_code, MIGRATION_CODE_TTL_DAYS, OLD_SERVER_DECOMMISSION_DAYS

    mc = generate_migration_code()
    if mc is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "transfer_unavailable",
                "message": (
                    "Self-service transfer is only available for lifetime_protected licenses. "
                    "Either your license type doesn't support this, or no LICENSE_KEY is set."
                ),
            },
        )
    return {
        "code":             mc.code,
        "issued_at":        mc.issued_at.isoformat(),
        "code_expires_at":  mc.expires_at.isoformat(),
        "code_valid_days":  MIGRATION_CODE_TTL_DAYS,
        "this_server_decommissions_in_days": OLD_SERVER_DECOMMISSION_DAYS,
    }


class LicenseTransferApplyRequest(BaseModel):
    code: str


@router.post("/license/transfer/apply")
async def license_transfer_apply(data: LicenseTransferApplyRequest):
    """On the NEW server, verify a transfer code and stage it to ride
    along the next heartbeat. The lic-server records the migration as a
    legitimate fingerprint change (not a clone)."""
    from ...modules.license.migration_code import (
        verify_migration_code, parse_migration_code_metadata, _read_license_payload,
        _license_id_from_payload, save_applied_migration,
    )
    from ...modules.license.instance_manager import save_pending_migration
    from ...modules.license.manager import LicenseManager

    code = data.code.strip().upper()
    ok, msg = verify_migration_code(code)
    if not ok:
        raise HTTPException(status_code=400, detail={"error": "invalid_code", "message": msg})

    payload = _read_license_payload() or {}
    # 1. Permanent local authorization: write the applied-migration record
    #    so the validator accepts THIS hardware for the migrated license
    #    from now on, fully offline. This is what actually makes the move
    #    take effect — without it the panel stays on FREE because the
    #    LICENSE_KEY is bound to the old hardware.
    current_hw = ""
    try:
        current_hw = LicenseManager().get_server_id()
    except Exception:
        pass
    if not save_applied_migration(code=code, current_hw=current_hw):
        # Refused: no license payload, or a second distinct code for the same
        # license already lives here (replay guard). Don't half-apply.
        raise HTTPException(status_code=409, detail={
            "error": "not_applied",
            "message": "Migration could not be applied on this machine "
                       "(no license, or it is already the home of a different "
                       "migration for this license).",
        })
    # 2. Transient receipt for the lic-server (clone-detection bookkeeping),
    #    forwarded + cleared on the next acknowledged heartbeat.
    save_pending_migration(
        code=code,
        from_hw_id=payload.get("hardware_id", ""),
        license_id=_license_id_from_payload(payload),
    )
    # 2b. Immediately fire one heartbeat so the lic-server learns of the move
    #     within seconds instead of up to a full heartbeat interval (≤24h for
    #     lifetime_protected). Best-effort: offline apply still works via the
    #     local applied-migration record, and the receipt rides the next
    #     scheduled heartbeat if this one can't reach the server.
    try:
        from ...modules.license.instance_manager import send_heartbeat
        await send_heartbeat()
    except Exception:
        pass
    # 3. Refresh the cached license so paid features light up without a
    #    restart. validate_license() re-reads the key + now sees the
    #    applied-migration record we just wrote; license enforcement
    #    reconcile picks the new tier up on its next cycle.
    revalidated = None
    try:
        info = LicenseManager().validate_license()
        revalidated = getattr(info, "tier", None) or getattr(info, "type", None)
    except Exception:
        pass
    meta = parse_migration_code_metadata(code) or {}
    return {
        "status":  "applied",
        "message": "Transfer code accepted — this server is now authorized for the migrated license.",
        "tier":            revalidated,
        "code_issued_at":  meta.get("issued_at"),
        "code_expires_at": meta.get("expires_at"),
    }


@router.post("/license/transfer/cancel")
async def license_transfer_cancel():
    """Cancel a pending transfer on THIS server (stops the self-decommission
    countdown). Already-issued codes remain cryptographically valid until
    their TTL — only this server's countdown is cleared."""
    from ...modules.license.migration_code import cancel_migration
    cleared = cancel_migration()
    return {"status": "cancelled" if cleared else "no_pending_transfer"}


@router.post("/license-check")
async def trigger_license_check():
    """Trigger an immediate license server check (runs in background)."""
    import asyncio
    try:
        from ...modules.license.online_validator import _do_check
        asyncio.create_task(_do_check())
        return {"status": "check_triggered"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ============================================================================
# BRANDING (White-Label)
# ============================================================================

@router.get("/branding")
async def get_branding_settings(db: Session = Depends(get_db)):
    """Get all branding settings (public — no auth required for client portal)"""
    return get_all_branding(db)


class BrandingUpdateRequest(BaseModel):
    branding_app_name: Optional[str] = Field(None, max_length=100)
    branding_customer_app_name: Optional[str] = Field(None, max_length=100)
    branding_company_name: Optional[str] = Field(None, max_length=200)
    branding_logo_url: Optional[str] = Field(None, max_length=500)
    branding_customer_logo_url: Optional[str] = Field(None, max_length=500)
    branding_favicon_url: Optional[str] = Field(None, max_length=500)
    branding_primary_color: Optional[str] = Field(None, pattern=r'^#[0-9a-fA-F]{3,8}$')
    branding_login_title: Optional[str] = Field(None, max_length=200)
    branding_support_email: Optional[str] = Field(None, max_length=200)
    branding_support_url: Optional[str] = Field(None, max_length=500)
    branding_footer_text: Optional[str] = Field(None, max_length=500)


@router.post("/branding", dependencies=[_white_label_gate])
async def update_branding_settings(data: BrandingUpdateRequest, db: Session = Depends(get_db)):
    """Update branding settings (admin only)"""
    updates = {k: v for k, v in data.model_dump(exclude_none=True).items() if k in BRANDING_DEFAULTS}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid branding keys provided")

    result = set_branding(updates, db)
    return {"message": "Branding updated", "branding": result}


@router.post("/branding/logo", dependencies=[_white_label_gate])
async def upload_branding_logo(
    file: UploadFile = File(...),
    target: str = "logo",
    db: Session = Depends(get_db)
):
    """Upload a branding image. ``target`` picks which SystemConfig field
    gets the resulting URL:

    - ``logo`` (default) → ``branding_logo_url`` (admin panel logo)
    - ``customer_logo`` → ``branding_customer_logo_url`` (client portal logo)
    - ``favicon`` → ``branding_favicon_url`` (browser tab icon)
    """
    # Validate file type
    allowed_types = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Invalid file type: {file.content_type}. Allowed: png, jpg, svg, webp")

    # Validate size (max 2MB)
    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 2MB)")

    # Save into a PERSISTENT uploads directory so the file survives
    # release swaps. ``src/web/static`` lives inside the release dir
    # (``/opt/vpnmanager/releases/<ver>/src/web/static``) which the
    # `current` symlink points at — that directory is replaced every
    # update, and any branding asset written there silently disappears
    # for the next release. ``/opt/vpnmanager/data/uploads`` is kept
    # outside the release tree and explicitly excluded from rsync /
    # deploy.sh, so it persists. The client portal mounts this same
    # path under ``/uploads/`` (see ``client_portal_main.py``).
    install_dir = os.getenv("INSTALL_DIR", "/opt/vpnmanager")
    uploads_dir = os.path.join(install_dir, "data", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    allowed_exts = {"png", "jpg", "jpeg", "svg", "webp"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "png"
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"Invalid file extension: {ext}")
    filename = f"brand-logo-{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(uploads_dir, filename)
    # Verify path is within uploads directory (path-traversal guard)
    if not os.path.abspath(filepath).startswith(os.path.abspath(uploads_dir)):
        raise HTTPException(status_code=400, detail="Invalid filename")

    with open(filepath, "wb") as f:
        f.write(contents)

    # Save URL to branding config — served by both admin API and the
    # client portal under ``/uploads/``.
    logo_url = f"/uploads/{filename}"
    target_key_map = {
        "logo":          "branding_logo_url",
        "customer_logo": "branding_customer_logo_url",
        "favicon":       "branding_favicon_url",
    }
    target_key = target_key_map.get(target, "branding_logo_url")
    set_branding({target_key: logo_url}, db)

    return {"message": "Logo uploaded", "url": logo_url, "target": target_key}


# ============================================================================
# PAYMENT SETTINGS
# ============================================================================

class PaymentSettingsUpdate(BaseModel):
    cryptopay_api_token: Optional[str] = None
    cryptopay_testnet: bool = False
    paypal_client_id: Optional[str] = None
    paypal_client_secret: Optional[str] = None
    paypal_sandbox: Optional[bool] = None
    paypal_webhook_id: Optional[str] = None
    nowpayments_api_key: Optional[str] = None
    nowpayments_ipn_secret: Optional[str] = None
    nowpayments_sandbox: Optional[bool] = None
    # Plugin providers
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    payme_merchant_id: Optional[str] = None
    payme_secret_key: Optional[str] = None
    mollie_api_key: Optional[str] = None
    razorpay_key_id: Optional[str] = None
    razorpay_key_secret: Optional[str] = None
    razorpay_webhook_secret: Optional[str] = None


def _mask_token(token: str) -> str:
    """Mask a token for display (show first 5 + last 4)"""
    if not token:
        return ""
    if len(token) > 12:
        return token[:5] + "..." + token[-4:]
    return "***configured***"


@router.get("/payment-settings")
async def get_payment_settings():
    """Get current payment configuration status"""
    from ..routes import client_portal

    return {
        # CryptoPay
        "cryptopay_configured": client_portal.cryptopay_adapter is not None,
        "cryptopay_token_masked": _mask_token(os.getenv("CRYPTOPAY_API_TOKEN", "")),
        "cryptopay_testnet": os.getenv("CRYPTOPAY_TESTNET", "false").lower() == "true",
        # PayPal
        "paypal_configured": client_portal.paypal_provider is not None,
        "paypal_client_id_masked": _mask_token(os.getenv("PAYPAL_CLIENT_ID", "")),
        "paypal_sandbox": os.getenv("PAYPAL_SANDBOX", "true").lower() == "true",
        "paypal_webhook_id_masked": _mask_token(os.getenv("PAYPAL_WEBHOOK_ID", "")),
        # NOWPayments
        "nowpayments_configured": client_portal.nowpayments_provider is not None,
        "nowpayments_api_key_masked": _mask_token(os.getenv("NOWPAYMENTS_API_KEY", "")),
        "nowpayments_sandbox": os.getenv("NOWPAYMENTS_SANDBOX", "false").lower() == "true",
        # Plugin providers
        "stripe_configured": getattr(client_portal, 'stripe_provider', None) is not None,
        "stripe_key_masked": _mask_token(os.getenv("STRIPE_SECRET_KEY", "")),
        "payme_configured": getattr(client_portal, 'payme_provider', None) is not None,
        "payme_id_masked": _mask_token(os.getenv("PAYME_MERCHANT_ID", "")),
        "mollie_configured": getattr(client_portal, 'mollie_provider', None) is not None,
        "mollie_key_masked": _mask_token(os.getenv("MOLLIE_API_KEY", "")),
        "razorpay_configured": getattr(client_portal, 'razorpay_provider', None) is not None,
        "razorpay_key_masked": _mask_token(os.getenv("RAZORPAY_KEY_ID", "")),
    }


@router.post("/payment-settings")
async def update_payment_settings(data: PaymentSettingsUpdate):
    """
    Update payment settings. Saves to .env and hot-reloads adapters.
    """
    from ..routes import client_portal
    from ...modules.subscription.cryptopay_adapter import CryptoPayAdapter

    env_path = _find_env_file()
    updates = {}

    # CryptoPay
    if data.cryptopay_api_token is not None:
        updates["CRYPTOPAY_API_TOKEN"] = data.cryptopay_api_token
    if data.cryptopay_testnet is not None:
        updates["CRYPTOPAY_TESTNET"] = "true" if data.cryptopay_testnet else "false"

    # PayPal
    if data.paypal_client_id is not None:
        updates["PAYPAL_CLIENT_ID"] = data.paypal_client_id
    if data.paypal_client_secret is not None:
        updates["PAYPAL_CLIENT_SECRET"] = data.paypal_client_secret
    if data.paypal_sandbox is not None:
        updates["PAYPAL_SANDBOX"] = "true" if data.paypal_sandbox else "false"
    if data.paypal_webhook_id is not None:
        updates["PAYPAL_WEBHOOK_ID"] = data.paypal_webhook_id

    # NOWPayments
    if data.nowpayments_api_key is not None:
        updates["NOWPAYMENTS_API_KEY"] = data.nowpayments_api_key
    if data.nowpayments_ipn_secret is not None:
        updates["NOWPAYMENTS_IPN_SECRET"] = data.nowpayments_ipn_secret
    if data.nowpayments_sandbox is not None:
        updates["NOWPAYMENTS_SANDBOX"] = "true" if data.nowpayments_sandbox else "false"

    # Stripe
    if data.stripe_secret_key is not None:
        updates["STRIPE_SECRET_KEY"] = data.stripe_secret_key
    if data.stripe_webhook_secret is not None:
        updates["STRIPE_WEBHOOK_SECRET"] = data.stripe_webhook_secret

    # Payme
    if data.payme_merchant_id is not None:
        updates["PAYME_MERCHANT_ID"] = data.payme_merchant_id
    if data.payme_secret_key is not None:
        updates["PAYME_SECRET_KEY"] = data.payme_secret_key

    # Mollie
    if data.mollie_api_key is not None:
        updates["MOLLIE_API_KEY"] = data.mollie_api_key

    # Razorpay
    if data.razorpay_key_id is not None:
        updates["RAZORPAY_KEY_ID"] = data.razorpay_key_id
    if data.razorpay_key_secret is not None:
        updates["RAZORPAY_KEY_SECRET"] = data.razorpay_key_secret
    if data.razorpay_webhook_secret is not None:
        updates["RAZORPAY_WEBHOOK_SECRET"] = data.razorpay_webhook_secret

    # Write to .env
    _update_env_file(env_path, updates)

    # Update os.environ
    for key, value in updates.items():
        os.environ[key] = value

    results = {}

    # Hot-reload CryptoPay
    token = os.getenv("CRYPTOPAY_API_TOKEN", "")
    testnet = os.getenv("CRYPTOPAY_TESTNET", "false").lower() == "true"
    if token:
        try:
            client_portal.cryptopay_adapter = CryptoPayAdapter(api_token=token, testnet=testnet)
            results["cryptopay"] = {"connected": True, "message": "CryptoPay activated"}
        except Exception as e:
            client_portal.cryptopay_adapter = None
            results["cryptopay"] = {"connected": False, "message": str(e)}
    else:
        client_portal.cryptopay_adapter = None
        results["cryptopay"] = {"connected": False, "message": "No token"}

    # Hot-reload PayPal
    pp_id = os.getenv("PAYPAL_CLIENT_ID", "")
    pp_secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
    pp_sandbox = os.getenv("PAYPAL_SANDBOX", "true").lower() == "true"
    pp_webhook_id = os.getenv("PAYPAL_WEBHOOK_ID", "")
    if pp_id and pp_secret:
        try:
            from ...modules.payment.providers.paypal import PayPalProvider
            provider = PayPalProvider(client_id=pp_id, client_secret=pp_secret, sandbox=pp_sandbox, webhook_id=pp_webhook_id)
            test = await provider.test_connection()
            if test["connected"]:
                client_portal.paypal_provider = provider
                results["paypal"] = {"connected": True, "message": "PayPal activated"}
            else:
                client_portal.paypal_provider = None
                results["paypal"] = {"connected": False, "message": test["message"]}
        except Exception as e:
            client_portal.paypal_provider = None
            results["paypal"] = {"connected": False, "message": str(e)}
    else:
        client_portal.paypal_provider = None
        results["paypal"] = {"connected": False, "message": "No credentials"}

    # Hot-reload NOWPayments
    np_key = os.getenv("NOWPAYMENTS_API_KEY", "")
    np_secret = os.getenv("NOWPAYMENTS_IPN_SECRET", "")
    np_sandbox = os.getenv("NOWPAYMENTS_SANDBOX", "false").lower() == "true"
    if np_key:
        try:
            # IMPORTANT: must use NOWPaymentsProvider (the new one), not the older
            # CryptoPaymentProvider class. The new one has verify_signature() that
            # the webhook handler relies on; the older class doesn't and would
            # crash on every IPN. main.py boot path uses NOWPaymentsProvider too —
            # this hot-reload must match it 1:1.
            from ...modules.payment.providers.nowpayments import NOWPaymentsProvider
            client_portal.nowpayments_provider = NOWPaymentsProvider(
                api_key=np_key, ipn_secret=np_secret, sandbox=np_sandbox
            )
            results["nowpayments"] = {"connected": True, "message": "NOWPayments activated"}
        except Exception as e:
            client_portal.nowpayments_provider = None
            results["nowpayments"] = {"connected": False, "message": str(e)}
    else:
        client_portal.nowpayments_provider = None
        results["nowpayments"] = {"connected": False, "message": "No API key"}

    # Hot-reload Stripe plugin
    _sk = os.getenv("STRIPE_SECRET_KEY", "")
    if _sk:
        try:
            from plugins.payments.stripe_provider import StripeProvider
            _p = StripeProvider()
            _t = await _p.test_connection()
            if _t["connected"]:
                client_portal.stripe_provider = _p
                results["stripe"] = {"connected": True, "message": "Stripe activated"}
            else:
                client_portal.stripe_provider = None
                results["stripe"] = {"connected": False, "message": _t["message"]}
        except Exception as e:
            client_portal.stripe_provider = None
            results["stripe"] = {"connected": False, "message": str(e)}
    else:
        client_portal.stripe_provider = None
        results["stripe"] = {"connected": False, "message": "No key"}

    # Hot-reload Payme plugin
    _pm = os.getenv("PAYME_MERCHANT_ID", "")
    if _pm:
        try:
            from plugins.payments.payme_provider import PaymeProvider
            _p = PaymeProvider()
            client_portal.payme_provider = _p
            results["payme"] = {"connected": True, "message": "Payme activated"}
        except Exception as e:
            client_portal.payme_provider = None
            results["payme"] = {"connected": False, "message": str(e)}
    else:
        client_portal.payme_provider = None
        results["payme"] = {"connected": False, "message": "No merchant ID"}

    # Hot-reload Mollie plugin
    _mk = os.getenv("MOLLIE_API_KEY", "")
    if _mk:
        try:
            from plugins.payments.mollie_provider import MollieProvider
            _p = MollieProvider()
            _t = await _p.test_connection()
            if _t["connected"]:
                client_portal.mollie_provider = _p
                results["mollie"] = {"connected": True, "message": "Mollie activated"}
            else:
                client_portal.mollie_provider = None
                results["mollie"] = {"connected": False, "message": _t["message"]}
        except Exception as e:
            client_portal.mollie_provider = None
            results["mollie"] = {"connected": False, "message": str(e)}
    else:
        client_portal.mollie_provider = None
        results["mollie"] = {"connected": False, "message": "No key"}

    # Hot-reload Razorpay plugin
    _rk = os.getenv("RAZORPAY_KEY_ID", "")
    _rs = os.getenv("RAZORPAY_KEY_SECRET", "")
    if _rk and _rs:
        try:
            from plugins.payments.razorpay_provider import RazorpayProvider
            _p = RazorpayProvider()
            _t = await _p.test_connection()
            if _t["connected"]:
                client_portal.razorpay_provider = _p
                results["razorpay"] = {"connected": True, "message": "Razorpay activated"}
            else:
                client_portal.razorpay_provider = None
                results["razorpay"] = {"connected": False, "message": _t["message"]}
        except Exception as e:
            client_portal.razorpay_provider = None
            results["razorpay"] = {"connected": False, "message": str(e)}
    else:
        client_portal.razorpay_provider = None
        results["razorpay"] = {"connected": False, "message": "No credentials"}

    # Determine overall status
    any_connected = any(r.get("connected") for r in results.values())

    # The portal process (vpnmanager-client-portal.service) runs as a separate
    # PID with its own copy of the client_portal module. Hot-reloading
    # providers above only updates THIS (admin) process's in-memory state —
    # the portal keeps serving the old (or absent) provider objects until it
    # restarts. So when the admin changes payment settings, kick the portal
    # so the next /client-portal/payments/providers and /payments/invoice
    # calls reflect the new state. Best-effort: a missing systemctl or a
    # non-systemd install (Docker, dev) shouldn't 500 the settings save.
    try:
        import subprocess as _sp
        _sp.run(
            ["systemctl", "restart", "vpnmanager-client-portal.service"],
            check=False, capture_output=True, timeout=10,
        )
        logger.info("payment-settings: requested vpnmanager-client-portal restart so portal picks up new keys")
    except Exception as _re:
        logger.debug(f"could not restart client-portal service: {_re}")

    return {
        "status": "ok",
        "connected": any_connected,
        "message": "Settings updated",
        "providers": results,
    }


# ============================================================================
# PAYMENT TEST — fires same checks as tools/test_webhook_signatures.py against
# the running provider so admins can validate keys without a real charge.
# ============================================================================


async def _payment_test_for_provider(provider_name: str) -> Dict[str, Any]:
    """
    Run sign/verify simulation + API ping for a single provider in-process.

    Returns:
        {
            "provider": "stripe",
            "configured": bool,
            "checks": [{"name": str, "ok": bool, "detail": str}],
            "passed": int,
            "failed": int,
        }
    """
    import json as _json
    import hmac as _hmac
    import hashlib as _hashlib
    import base64 as _base64

    from ..routes import client_portal

    checks: List[Dict[str, Any]] = []

    def _add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    name = (provider_name or "").lower().strip()

    # ── Resolve the live provider object ─────────────────────────────────────
    if name == "cryptopay":
        prov = getattr(client_portal, "cryptopay_adapter", None)
    else:
        prov = getattr(client_portal, f"{name}_provider", None)

    if not prov:
        return {
            "provider": name,
            "configured": False,
            "checks": [{"name": "Provider configured", "ok": False,
                        "detail": "Save the keys above first, then click Test."}],
            "passed": 0, "failed": 1,
        }

    _add("Provider loaded in memory", True, prov.__class__.__name__)

    # ── Optional API ping ────────────────────────────────────────────────────
    if hasattr(prov, "test_connection"):
        try:
            ping = await prov.test_connection()
            ok = bool(ping.get("connected"))
            _add("API connection (test_connection)", ok, ping.get("message", ""))
        except Exception as e:
            _add("API connection (test_connection)", False, str(e))

    # ── Provider-specific signature simulation ───────────────────────────────
    try:
        if name == "nowpayments":
            secret = os.getenv("NOWPAYMENTS_IPN_SECRET", "")
            _add("IPN secret configured", bool(secret),
                 "Without it every webhook is rejected." if not secret else "set")
            if secret:
                body = _json.dumps({
                    "payment_status": "finished", "order_id": "test-np",
                    "payment_id": "1", "price_amount": 10,
                }, separators=(",", ":")).encode()
                sorted_body = _json.dumps(_json.loads(body), sort_keys=True, separators=(",", ":")).encode()
                good = _hmac.new(secret.encode(), sorted_body, _hashlib.sha512).hexdigest()
                _add("HMAC-SHA512 valid signature accepted", prov.verify_signature(body, good))
                _add("Forged signature rejected", not prov.verify_signature(body, "deadbeef" * 16))
                _add("Tampered body rejected",
                     not prov.verify_signature(body.replace(b"finished", b"FINISHED"), good))

        elif name == "stripe":
            wh = os.getenv("STRIPE_WEBHOOK_SECRET", "")
            _add("Webhook secret configured", bool(wh),
                 "Required to verify Stripe webhooks." if not wh else "set")
            if wh:
                # Use the SDK to build a valid signed payload exactly as Stripe would.
                import stripe as _stripe  # noqa: F401
                import time as _time
                body = _json.dumps({
                    "id": "evt_test", "type": "checkout.session.completed",
                    "data": {"object": {"id": "cs_test", "payment_status": "paid",
                                        "metadata": {"invoice_id": "inv-test"}}},
                }, separators=(",", ":")).encode()
                ts = int(_time.time())
                sig_payload = f"{ts}.".encode() + body
                sig = _hmac.new(wh.encode(), sig_payload, _hashlib.sha256).hexdigest()
                sig_header = f"t={ts},v1={sig}"
                res = await prov.process_webhook(body, {"stripe-signature": sig_header})
                _add("Valid Stripe-Signature accepted", bool(res.get("verified")))
                _add("Order ID extracted from metadata", res.get("order_id") == "inv-test")

                bad = await prov.process_webhook(body, {"stripe-signature": "t=1,v1=00"})
                _add("Forged Stripe-Signature rejected", bad.get("verified") is False)

        elif name == "razorpay":
            wh = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
            _add("Webhook secret configured", bool(wh),
                 "Set RAZORPAY_WEBHOOK_SECRET in .env to verify webhooks." if not wh else "set")
            if wh:
                body = _json.dumps({
                    "event": "payment.captured",
                    "payload": {"payment": {"entity": {
                        "id": "pay_test", "order_id": "order_test",
                        "notes": {"invoice_id": "inv-rzp"},
                    }}},
                }, separators=(",", ":")).encode()
                sig = _hmac.new(wh.encode(), body, _hashlib.sha256).hexdigest()
                res = await prov.process_webhook(body, {"x-razorpay-signature": sig})
                _add("Valid X-Razorpay-Signature accepted", bool(res.get("verified")))
                _add("Order ID extracted from notes", res.get("order_id") == "inv-rzp")

                bad = await prov.process_webhook(body, {"x-razorpay-signature": "0" * 64})
                _add("Forged signature rejected", bad.get("verified") is False)

        elif name == "payme":
            secret = os.getenv("PAYME_SECRET_KEY", "")
            _add("Secret key configured", bool(secret),
                 "Required for HTTP Basic auth verification." if not secret else "set")
            if secret:
                body = _json.dumps({
                    "method": "receipts.pay",
                    "params": {"id": "rcpt_test", "account": {"order_id": "inv-payme"}},
                }, separators=(",", ":")).encode()
                good_auth = "Basic " + _base64.b64encode(f"Paycom:{secret}".encode()).decode()
                res = await prov.process_webhook(body, {"authorization": good_auth})
                _add("Valid Basic auth accepted", bool(res.get("verified")))
                _add("Order ID extracted from account", res.get("order_id") == "inv-payme")

                bad_auth = "Basic " + _base64.b64encode(b"Paycom:wrong-secret").decode()
                bad = await prov.process_webhook(body, {"authorization": bad_auth})
                _add("Wrong secret rejected", bad.get("verified") is False)

                no_auth = await prov.process_webhook(body, {})
                _add("Missing Authorization rejected", no_auth.get("verified") is False)

        elif name == "mollie":
            # Mollie has no shared signature — verification is the API call-back
            # (Mollie sends just the payment ID, we ask the API). The realistic
            # offline test is "API key works" + "endpoint is reachable" — both
            # already covered by test_connection() above. Add a parser smoke
            # test so admins see the webhook handler at least parses input.
            body = b"id=tr_test_invalid"
            res = await prov.process_webhook(body, {"content-type": "application/x-www-form-urlencoded"})
            _add("Form-encoded body parsed by handler",
                 isinstance(res, dict),
                 "Mollie verifies via API call-back, not shared signature.")

        elif name == "paypal":
            wh = os.getenv("PAYPAL_WEBHOOK_ID", "")
            _add("Webhook ID configured", bool(wh),
                 "Required in production. Sandbox skips verification." if not wh else "set")
            # PayPal verification is a remote API call against PayPal — we can't
            # easily simulate it offline. test_connection() above already proves
            # OAuth credentials are valid.

        elif name == "cryptopay":
            # CryptoPay verifies HMAC-SHA256 of body using SHA256(api_token) as key.
            from src.modules.subscription.cryptopay_adapter import CryptoPayAdapter  # noqa: F401
            api_token = os.getenv("CRYPTOPAY_API_TOKEN", "")
            _add("API token configured", bool(api_token))
            if api_token:
                body = _json.dumps({"update_type": "invoice_paid",
                                    "payload": {"invoice_id": 123, "status": "paid"}},
                                   separators=(",", ":")).encode()
                key = _hashlib.sha256(api_token.encode()).digest()
                good = _hmac.new(key, body, _hashlib.sha256).hexdigest()
                res_good = await prov.process_webhook(body, {"crypto-pay-api-signature": good})
                _add("Valid CryptoPay signature accepted", res_good is not None)
                res_bad = await prov.process_webhook(body, {"crypto-pay-api-signature": "0" * 64})
                _add("Forged signature rejected", res_bad is None)

        else:
            _add("Provider has no test scenario yet", False,
                 f"'{name}' is loaded but no automated test was implemented.")

    except Exception as e:
        _add("Test execution error", False, f"{type(e).__name__}: {e}")

    passed = sum(1 for c in checks if c["ok"])
    failed = sum(1 for c in checks if not c["ok"])
    return {
        "provider": name,
        "configured": True,
        "checks": checks,
        "passed": passed,
        "failed": failed,
    }


@router.post("/payment-test/{provider_name}")
async def run_payment_test(provider_name: str):
    """
    Run an offline self-test for a single payment provider.

    Validates: configuration is loaded, signing key is present, webhook
    signature accept/reject paths behave correctly, plus an API ping
    where the provider supports it. Does NOT make any real charges.
    """
    return await _payment_test_for_provider(provider_name)


# ============================================================================
# SMTP SETTINGS
# ============================================================================

class SmtpSettingsUpdate(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_tls: Optional[bool] = None
    smtp_from: Optional[str] = None
    smtp_enabled: Optional[bool] = None


@router.get("/device-limits")
async def get_device_limits(db: Session = Depends(get_db)):
    """Read the per-customer device cap (admin-side ``customer_email`` grouping).

    Returns ``{"max_devices_per_customer": N}``. ``0`` means unlimited.
    """
    from ...database.models import SystemConfig
    row = db.query(SystemConfig).filter(SystemConfig.key == "max_devices_per_customer").first()
    val = 0
    if row and row.value:
        try:
            val = int(row.value)
        except Exception:
            val = 0
    return {"max_devices_per_customer": val}


class DeviceLimitsUpdate(BaseModel):
    max_devices_per_customer: int = Field(..., ge=0, le=1000)


@router.post("/device-limits")
async def update_device_limits(data: DeviceLimitsUpdate, db: Session = Depends(get_db)):
    """Set the per-customer device cap. ``0`` disables enforcement.

    Stored in ``system_config`` so the value survives restarts and propagates
    across the whole panel without an env-file rewrite. Enforcement is in
    POST /clients (see clients.py).
    """
    from ...database.models import SystemConfig
    row = db.query(SystemConfig).filter(SystemConfig.key == "max_devices_per_customer").first()
    if row is None:
        row = SystemConfig(
            key="max_devices_per_customer",
            value=str(data.max_devices_per_customer),
            value_type="int",
            description="Maximum active WG/AmneziaWG peers a single customer_email may have. 0 = unlimited.",
        )
        db.add(row)
    else:
        row.value = str(data.max_devices_per_customer)
        row.value_type = "int"
    db.commit()
    return {"max_devices_per_customer": data.max_devices_per_customer}


# ============================================================================
# FREE TIER TOGGLE
# ============================================================================

@router.get("/subscription-settings")
async def get_subscription_settings(db: Session = Depends(get_db)):
    """Read subscription-level admin toggles.

    Today: just the free-tier auto-grant. When disabled, the portal stops
    auto-creating a free subscription for fresh sign-ups so visitors have
    to pick (and pay for) a plan before they can add a device.
    """
    from ...database.models import SystemConfig
    row = db.query(SystemConfig).filter(SystemConfig.key == "enable_free_tier").first()
    enabled = True
    if row is not None and row.value is not None:
        enabled = str(row.value).strip().lower() not in ("0", "false", "no", "off")
    return {"enable_free_tier": enabled}


class SubscriptionSettingsUpdate(BaseModel):
    enable_free_tier: bool


@router.post("/subscription-settings")
async def update_subscription_settings(
    data: SubscriptionSettingsUpdate, db: Session = Depends(get_db)
):
    """Flip the free-tier auto-grant on or off."""
    from ...database.models import SystemConfig
    row = db.query(SystemConfig).filter(SystemConfig.key == "enable_free_tier").first()
    val = "true" if data.enable_free_tier else "false"
    if row is None:
        row = SystemConfig(
            key="enable_free_tier",
            value=val,
            value_type="bool",
            description="Whether new portal users get an auto-created free subscription. When false, every customer must pick a paid plan.",
        )
        db.add(row)
    else:
        row.value = val
        row.value_type = "bool"
    db.commit()
    return {"enable_free_tier": data.enable_free_tier}


@router.get("/smtp-settings")
async def get_smtp_settings():
    """Get current SMTP configuration status"""
    from ..routes import client_portal

    return {
        "smtp_configured": client_portal.email_service is not None,
        "smtp_enabled": os.getenv("SMTP_ENABLED", "false").lower() == "true",
        "smtp_host": os.getenv("SMTP_HOST", ""),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_username": os.getenv("SMTP_USERNAME", ""),
        "smtp_password_set": bool(os.getenv("SMTP_PASSWORD", "")),
        "smtp_tls": os.getenv("SMTP_TLS", "true").lower() == "true",
        "smtp_from": os.getenv("SMTP_FROM", ""),
    }


@router.post("/smtp-settings")
async def update_smtp_settings(data: SmtpSettingsUpdate):
    """Update SMTP settings. Saves to .env and hot-reloads email service."""
    from ..routes import client_portal

    env_path = _find_env_file()
    updates = {}

    if data.smtp_host is not None:
        updates["SMTP_HOST"] = data.smtp_host
    if data.smtp_port is not None:
        updates["SMTP_PORT"] = str(data.smtp_port)
    if data.smtp_username is not None:
        updates["SMTP_USERNAME"] = data.smtp_username
    if data.smtp_password is not None:
        updates["SMTP_PASSWORD"] = data.smtp_password
    if data.smtp_tls is not None:
        updates["SMTP_TLS"] = "true" if data.smtp_tls else "false"
    if data.smtp_from is not None:
        updates["SMTP_FROM"] = data.smtp_from
    if data.smtp_enabled is not None:
        updates["SMTP_ENABLED"] = "true" if data.smtp_enabled else "false"

    _update_env_file(env_path, updates)

    for key, value in updates.items():
        os.environ[key] = value

    # Hot-reload email service
    enabled = os.getenv("SMTP_ENABLED", "false").lower() == "true"
    host = os.getenv("SMTP_HOST", "")

    if enabled and host:
        try:
            from ...modules.email.email_service import EmailService
            service = EmailService(
                host=host,
                port=int(os.getenv("SMTP_PORT", "587")),
                username=os.getenv("SMTP_USERNAME", ""),
                password=os.getenv("SMTP_PASSWORD", ""),
                tls=os.getenv("SMTP_TLS", "true").lower() == "true",
                from_address=os.getenv("SMTP_FROM", ""),
            )
            test = service.test_connection()
            if test["connected"]:
                client_portal.email_service = service
                return {"status": "ok", "connected": True, "message": "SMTP connected"}
            else:
                client_portal.email_service = None
                return {"status": "error", "connected": False, "message": test["message"]}
        except Exception as e:
            client_portal.email_service = None
            return {"status": "error", "connected": False, "message": str(e)}
    else:
        client_portal.email_service = None
        return {"status": "ok", "connected": False, "message": "SMTP disabled"}


@router.post("/smtp-test")
async def test_smtp(db: Session = Depends(get_db)):
    """Send test email using current SMTP settings"""
    from ..routes import client_portal

    if not client_portal.email_service:
        raise HTTPException(status_code=503, detail="SMTP not configured")

    from_addr = os.getenv("SMTP_FROM", os.getenv("SMTP_USERNAME", ""))
    if not from_addr:
        raise HTTPException(status_code=400, detail="No from address configured")

    import asyncio
    sent = await asyncio.get_running_loop().run_in_executor(
        None, client_portal.email_service.send_test_email, from_addr
    )

    if sent:
        return {"status": "ok", "message": f"Test email sent to {from_addr}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send test email")


# ============================================================================
# WEB ACCESS / DOMAINS / TLS
# ============================================================================

class WebAccessSettingsUpdate(BaseModel):
    setup_mode: Literal["none", "portal_admin_ip", "portal_admin_domain"] = "none"
    client_portal_domain: Optional[str] = Field(None, max_length=253)
    admin_panel_domain: Optional[str] = Field(None, max_length=253)
    certbot_email: Optional[str] = Field(None, max_length=200)


def _read_env_value(key: str, default: str = "") -> str:
    env_path = _find_env_file()
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith(f"{key}="):
                    return stripped.split("=", 1)[1]
    return os.getenv(key, default)


def _validate_domain_name(value: str, field: str) -> str:
    value = (value or "").strip().lower()
    if not value:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    if not re.match(r'^([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$', value):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    return value


def _detect_public_ip_hint() -> str:
    endpoint = _read_env_value("SERVER_ENDPOINT", "")
    if endpoint and ":" in endpoint:
        return endpoint.split(":", 1)[0]
    return platform.node() or ""


_public_ip_cache: dict = {}  # {"ip": str, "ts": float}

@router.get("/public-ip")
async def get_public_ip():
    """Return the public IP of this machine (cached 5 min). Used to auto-fill endpoint on server creation."""
    import time
    import httpx as _httpx

    cached = _public_ip_cache
    if cached.get("ip") and (time.time() - cached.get("ts", 0)) < 300:
        return {"public_ip": cached["ip"]}

    services = [
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://icanhazip.com",
    ]
    for url in services:
        try:
            async with _httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                ip = resp.text.strip()
                if ip:
                    _public_ip_cache["ip"] = ip
                    _public_ip_cache["ts"] = time.time()
                    return {"public_ip": ip}
        except Exception:
            continue

    # Fallback: use hint from env
    hint = _detect_public_ip_hint()
    return {"public_ip": hint or ""}


def _find_web_access_script() -> str:
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts", "configure-web-access.sh"),
        "/opt/vpnmanager/scripts/configure-web-access.sh",
        os.path.join(os.getcwd(), "scripts", "configure-web-access.sh"),
    ]
    for path in candidates:
        normalized = os.path.normpath(path)
        if os.path.exists(normalized):
            return normalized
    raise HTTPException(status_code=500, detail="Web access script not found")


def _reload_runtime_env(keys: list[str]):
    env_path = _find_env_file()
    if not os.path.exists(env_path):
        return
    parsed = {}
    with open(env_path, "r") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '=' not in stripped:
                continue
            key, value = stripped.split('=', 1)
            parsed[key] = value
    for key in keys:
        if key in parsed:
            os.environ[key] = parsed[key]


@router.get("/web-access")
async def get_web_access_settings():
    mode = _read_env_value("WEB_SETUP_MODE", "none")
    portal_url = _read_env_value("CLIENT_PORTAL_URL", "")
    admin_url = _read_env_value("ADMIN_PANEL_URL", "")
    return {
        "setup_mode": mode,
        "client_portal_domain": _read_env_value("CLIENT_PORTAL_DOMAIN", ""),
        "admin_panel_domain": _read_env_value("ADMIN_PANEL_DOMAIN", ""),
        "certbot_email": _read_env_value("CERTBOT_EMAIL", ""),
        "admin_access_mode": _read_env_value("ADMIN_ACCESS_MODE", "raw_ports"),
        "client_portal_url": portal_url,
        "admin_panel_url": admin_url,
        "public_ip_hint": _detect_public_ip_hint(),
        "nginx_installed": shutil.which("nginx") is not None,
        "certbot_installed": shutil.which("certbot") is not None,
    }


@router.post("/web-access")
def apply_web_access_settings(data: WebAccessSettingsUpdate):
    mode = data.setup_mode
    portal_domain = (data.client_portal_domain or "").strip()
    admin_domain = (data.admin_panel_domain or "").strip()
    certbot_email = (data.certbot_email or "").strip()

    if mode in {"portal_admin_ip", "portal_admin_domain"}:
        portal_domain = _validate_domain_name(portal_domain, "client_portal_domain")
        if not certbot_email:
            raise HTTPException(status_code=400, detail="certbot_email is required for HTTPS setup")
    if mode == "portal_admin_domain":
        admin_domain = _validate_domain_name(admin_domain, "admin_panel_domain")

    script_path = _find_web_access_script()
    install_dir = os.path.dirname(_find_env_file())
    cmd = [script_path, "--install-dir", install_dir, "--mode", mode]
    if portal_domain:
        cmd += ["--portal-domain", portal_domain]
    if admin_domain:
        cmd += ["--admin-domain", admin_domain]
    if certbot_email:
        cmd += ["--email", certbot_email]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Web access setup timed out")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise HTTPException(status_code=500, detail=detail[-1200:])

    _reload_runtime_env([
        "WEB_SETUP_MODE", "CLIENT_PORTAL_DOMAIN", "ADMIN_PANEL_DOMAIN", "CERTBOT_EMAIL",
        "ADMIN_ACCESS_MODE", "CLIENT_PORTAL_URL", "ADMIN_PANEL_URL"
    ])

    return {
        "status": "ok",
        "message": "Web access updated",
        "output": (result.stdout or "").strip()[-2000:],
        "client_portal_url": os.getenv("CLIENT_PORTAL_URL", ""),
        "admin_panel_url": os.getenv("ADMIN_PANEL_URL", ""),
        "setup_mode": os.getenv("WEB_SETUP_MODE", mode),
    }


# ============================================================================
# HELPERS
# ============================================================================

def _update_env_file(env_path: str, updates: dict):
    """Update .env file with new key=value pairs.

    Uses an exclusive advisory lock (lock file) to prevent TOCTOU races when
    two concurrent requests try to update .env simultaneously (e.g. two license
    activations fired at the same time would otherwise interleave read/write).
    """
    import fcntl

    lock_path = env_path + ".lock"
    with open(lock_path, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            env_lines = []
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    env_lines = f.readlines()

            new_lines = []
            keys_written = set()
            for line in env_lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    key = stripped.split("=", 1)[0].strip()
                    if key in updates:
                        new_lines.append(f"{key}={updates[key]}\n")
                        keys_written.add(key)
                        continue
                new_lines.append(line)

            for key, value in updates.items():
                if key not in keys_written:
                    new_lines.append(f"{key}={value}\n")

            with open(env_path, "w") as f:
                f.writelines(new_lines)
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


@router.get("/notification-settings")
def get_notification_settings(db: Session = Depends(get_db)):
    """Get notification settings + a write-only flag for FCM.

    The FCM Server Key itself is never returned — the admin UI shows a
    masked placeholder when ``fcm_server_key_set=True`` and lets the
    operator paste a new value to replace it.
    """
    from ...database.models import SystemConfig
    keys = [
        "notifications_enabled",
        "admin_telegram_chat_id",
        "notify_admin_new_user",
        "notify_admin_new_payment",
        "notify_admin_subscription_expired",
        "notify_user_expiry_warning",
        "notify_user_traffic_warning",
        "notify_user_payment_confirmed",
        "fcm_server_key",
        # Customer-app integration. When `app_integration_enabled` is
        # false the panel hides the Push Notifications sidebar entry and
        # the corresponding page shows a "first enable apps in Settings"
        # message — so operators without their own branded customer app
        # don't see a push-notifications UI that would be misleading.
        # `app_name` is shown verbatim in the page subtitle (replaces
        # a hard-coded brand string ("<Brand> Android & Windows") which was an
        # operator-specific leak into every operator's panel).
        "app_integration_enabled",
        "app_name",
    ]
    rows = db.query(SystemConfig).filter(SystemConfig.key.in_(keys)).all()
    settings = {r.key: r.value for r in rows}

    public_keys = [k for k in keys if k != "fcm_server_key"]
    out = {k: settings.get(k, "true") for k in public_keys}
    out["fcm_server_key_set"] = bool((settings.get("fcm_server_key") or "").strip())
    # Booleans need defaults that lean "off": new operators see the
    # toggle disabled until they explicitly turn it on.
    out["app_integration_enabled"] = settings.get("app_integration_enabled", "false")
    out["app_name"] = settings.get("app_name", "")
    return out


@router.post("/notification-settings")
def update_notification_settings(data: dict, db: Session = Depends(get_db)):
    """Update notification settings.

    ``fcm_server_key`` is allowed but never echoed back — pass an empty
    string to clear it. Anything else is treated as a literal string
    and stored as-is.
    """
    from ...database.models import SystemConfig
    allowed_keys = [
        "notifications_enabled",
        "admin_telegram_chat_id",
        "notify_admin_new_user",
        "notify_admin_new_payment",
        "notify_admin_subscription_expired",
        "notify_user_expiry_warning",
        "notify_user_traffic_warning",
        "notify_user_payment_confirmed",
        "fcm_server_key",
        "app_integration_enabled",
        "app_name",
    ]
    updated = 0
    for key, value in data.items():
        if key not in allowed_keys:
            continue
        existing = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if existing:
            existing.value = str(value)
        else:
            db.add(SystemConfig(key=key, value=str(value)))
        updated += 1

    db.commit()
    return {"message": f"Updated {updated} notification settings"}


# ============================================================================
# DONATION WALLETS — operator-set crypto addresses shown in the "Support the
# project" modal (designer handoff donate feature). Plain SystemConfig strings.
# ============================================================================
_DONATION_COINS = ["btc", "eth", "ton", "usdt", "usdc"]


def _get_cfg(db, key, default=""):
    from ...database.models import SystemConfig
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    return row.value if row else default


def _set_cfg(db, key, value):
    from ...database.models import SystemConfig
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if row:
        row.value = value
    else:
        db.add(SystemConfig(key=key, value=value))


@router.get("/donation-wallets")
def get_donation_wallets(db: Session = Depends(get_db)):
    """Return donation config: operator crypto addresses + a Paylio card-checkout
    URL + a `hidden` flag (operator opts to hide the Support button — only takes
    effect when the panel is licensed; enforced in the UI + rechecked here)."""
    from ...database.models import SystemConfig
    keys = [f"donation_wallet_{c}" for c in _DONATION_COINS]
    rows = db.query(SystemConfig).filter(SystemConfig.key.in_(keys)).all()
    stored = {r.key: r.value for r in rows}
    out = {c: stored.get(f"donation_wallet_{c}", "") for c in _DONATION_COINS}
    out["card_url"] = _get_cfg(db, "donation_card_url", "")
    out["hidden"] = _get_cfg(db, "donation_hidden", "false") == "true"
    return out


@router.post("/donation-wallets")
def update_donation_wallets(data: dict, db: Session = Depends(get_db)):
    """Save donation config. Accepts {btc,eth,ton,usdt,usdc, card_url, hidden}.
    Unknown keys ignored; empty string clears a value."""
    updated = 0
    for coin in _DONATION_COINS:
        if coin in data:
            _set_cfg(db, f"donation_wallet_{coin}", str(data.get(coin) or "").strip())
            updated += 1
    if "card_url" in data:
        _set_cfg(db, "donation_card_url", str(data.get("card_url") or "").strip())
        updated += 1
    if "hidden" in data:
        _set_cfg(db, "donation_hidden", "true" if data.get("hidden") else "false")
        updated += 1
    db.commit()
    return {"message": f"Updated {updated} donation setting(s)"}


# ============================================================================
# BACKUP — moved to src/api/routes/backup.py in 1.5.83
# ============================================================================
# Settings, mount, test-write, and operations now live together in one router
# (formerly split between system.py and backup.py). See backup.py.

def _find_env_file() -> str:
    """Find the .env file path"""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".env"),
        "/opt/vpnmanager/.env",
        os.path.join(os.getcwd(), ".env"),
    ]
    for path in candidates:
        normalized = os.path.normpath(path)
        if os.path.exists(normalized):
            return normalized
    return os.path.normpath(candidates[0])


# ============================================================================
# PUSH NOTIFICATIONS (Admin)
# ============================================================================

class SendNotificationRequest(BaseModel):
    user_id: Optional[int] = None  # None = broadcast to all
    title: str
    message: str
    notification_type: str = "info"  # info, update, warning, promo


@router.post("/notifications/send")
def send_notification(data: SendNotificationRequest, db: Session = Depends(get_db)):
    """Send a push notification to a user or broadcast to all"""
    from ...database.models import PushNotification

    notif = PushNotification(
        user_id=data.user_id,
        title=data.title,
        message=data.message,
        notification_type=data.notification_type,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    return {"id": notif.id, "status": "sent"}


@router.get("/notifications/list")
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """List recent notifications (admin view)"""
    from ...database.models import PushNotification

    notifications = db.query(PushNotification).order_by(
        PushNotification.created_at.desc()
    ).limit(limit).all()

    return [
        {
            "id": n.id,
            "user_id": n.user_id,
            "title": n.title,
            "message": n.message,
            "type": n.notification_type,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None
        }
        for n in notifications
    ]


# ═══════════════════════════════════════════════════════════════════════════
# METRICS ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db)):
    """
    Internal metrics snapshot.

    Returns key operational counters for dashboards, alerting, and monitoring.

    Metric categories:
        clients  — active, disabled, expired, traffic_exceeded, proxy, ghost
        payments — completed_24h, failed_24h, pending, stale_pending_48h
        subs     — active, expired, free
        errors   — expired_enabled (CRITICAL), orphaned_payments_7d
    """
    import time
    from datetime import datetime, timezone, timedelta
    from ...database.models import Client, ClientStatus, Server, ServerStatus
    from ...modules.subscription.subscription_models import (
        ClientPortalPayment,
        ClientPortalSubscription,
        SubscriptionStatus,
    )

    start = time.monotonic()
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)
    cutoff_48h = now - timedelta(hours=48)

    # ── clients ──────────────────────────────────────────────────────────────
    total_clients = db.query(Client).count()
    active_clients = db.query(Client).filter(
        Client.enabled == True, Client.status == ClientStatus.ACTIVE
    ).count()
    disabled_clients = db.query(Client).filter(Client.enabled == False).count()
    expired_clients = db.query(Client).filter(
        Client.status == ClientStatus.EXPIRED
    ).count()
    traffic_exceeded_clients = db.query(Client).filter(
        Client.status == ClientStatus.TRAFFIC_EXCEEDED
    ).count()
    proxy_clients = db.query(Client).filter(Client.public_key.is_(None)).count()

    # CRITICAL: expired/traffic_exceeded but still enabled
    expired_still_enabled = db.query(Client).filter(
        Client.enabled == True,
        Client.status.in_([ClientStatus.EXPIRED, ClientStatus.TRAFFIC_EXCEEDED]),
    ).count()

    # ── payments ─────────────────────────────────────────────────────────────
    payments_completed_24h = db.query(ClientPortalPayment).filter(
        ClientPortalPayment.status == "completed",
        ClientPortalPayment.completed_at >= cutoff_24h,
    ).count()
    payments_failed_24h = db.query(ClientPortalPayment).filter(
        ClientPortalPayment.status.in_(["failed", "expired"]),
        ClientPortalPayment.updated_at >= cutoff_24h,
    ).count()
    payments_pending = db.query(ClientPortalPayment).filter(
        ClientPortalPayment.status == "pending",
    ).count()
    payments_stale_pending = db.query(ClientPortalPayment).filter(
        ClientPortalPayment.status == "pending",
        ClientPortalPayment.created_at < cutoff_48h,
    ).count()
    payments_inconsistent = db.query(ClientPortalPayment).filter(
        ClientPortalPayment.pipeline_status == "inconsistent",
    ).count()

    # orphaned: completed but no active sub (last 7d)
    recent_completed = db.query(ClientPortalPayment).filter(
        ClientPortalPayment.status == "completed",
        ClientPortalPayment.completed_at >= cutoff_7d,
    ).all()
    orphaned_payments_7d = 0
    for p in recent_completed:
        active = db.query(ClientPortalSubscription).filter(
            ClientPortalSubscription.user_id == p.user_id,
            ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
        ).first()
        if not active:
            orphaned_payments_7d += 1

    # ── subscriptions ────────────────────────────────────────────────────────
    subs_active = db.query(ClientPortalSubscription).filter(
        ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
    ).count()
    subs_expired = db.query(ClientPortalSubscription).filter(
        ClientPortalSubscription.status == SubscriptionStatus.EXPIRED,
    ).count()
    subs_free = db.query(ClientPortalSubscription).filter(
        ClientPortalSubscription.tier == "free",
    ).count()

    # ── servers ──────────────────────────────────────────────────────────────
    servers_total = db.query(Server).count()
    servers_drifted = db.query(Server).filter(Server.drift_detected == True).count()

    elapsed_ms = round((time.monotonic() - start) * 1000)

    return {
        "collected_at": now.isoformat(),
        "elapsed_ms": elapsed_ms,
        "clients": {
            "total": total_clients,
            "active": active_clients,
            "disabled": disabled_clients,
            "expired": expired_clients,
            "traffic_exceeded": traffic_exceeded_clients,
            "proxy": proxy_clients,
            "expired_still_enabled_CRITICAL": expired_still_enabled,
        },
        "payments": {
            "completed_24h": payments_completed_24h,
            "failed_24h": payments_failed_24h,
            "pending": payments_pending,
            "stale_pending_48h": payments_stale_pending,
            "inconsistent_pipeline": payments_inconsistent,
            "orphaned_completed_7d": orphaned_payments_7d,
        },
        "subscriptions": {
            "active": subs_active,
            "expired": subs_expired,
            "free": subs_free,
        },
        "servers": {
            "total": servers_total,
            "drifted": servers_drifted,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# FAIL-SAFE MODE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/failsafe")
def get_failsafe_status():
    """Return current fail-safe state."""
    from ...modules.failsafe import FailSafeManager
    state = FailSafeManager.instance().get_state()
    return {
        "active": state.active,
        "reasons": state.reasons,
        "activated_at": state.activated_at.isoformat() if state.activated_at else None,
        "last_check": state.last_check.isoformat() if state.last_check else None,
    }


@router.post("/failsafe/activate")
def activate_failsafe(reason: str = "manual_admin_activation", db: Session = Depends(get_db)):
    """Manually activate fail-safe mode (blocks new payments). Persists across restarts."""
    from ...modules.failsafe import FailSafeManager
    FailSafeManager.instance().force_activate(reason, db=db)
    return {"status": "activated", "reason": reason}


@router.post("/failsafe/deactivate")
def deactivate_failsafe(db: Session = Depends(get_db)):
    """Manually deactivate fail-safe mode. Persists across restarts."""
    from ...modules.failsafe import FailSafeManager
    FailSafeManager.instance().force_deactivate(db=db)
    return {"status": "deactivated"}


# ═══════════════════════════════════════════════════════════════════════════
# REPAIR ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/repair")
def repair_all(db: Session = Depends(get_db)):
    """
    Run a full system repair:
      1. State reconciler — re-add missing WG peers, remove ghost peers
      2. BusinessValidator (auto_fix=True) — fix all invariant violations
      3. Rebuild proxy configs for all proxy servers

    Returns a summary of all actions taken.
    Use when /health/full shows drift or after infrastructure changes.
    """
    from ...modules.state_reconciler import reconcile_server
    from ...modules.business_validator import BusinessValidator
    from ...core.client_manager import ClientManager
    from ...database.models import Server, ServerStatus

    started_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "started_at": started_at,
        "reconcile": {"servers_checked": 0, "actions": []},
        "business_validator": {"violations": 0, "auto_fixed": 0, "errors": []},
        "proxy_rebuild": {"servers_attempted": 0, "ok": [], "failed": []},
    }

    # ── Step 1: WG state reconciliation ──────────────────────────────────────
    try:
        online_servers = db.query(Server).filter(
            Server.lifecycle_status == "online",
        ).all()
        for server in online_servers:
            if getattr(server, "server_category", None) == "proxy":
                continue
            try:
                result = reconcile_server(server, db)
                db.commit()
                summary["reconcile"]["servers_checked"] += 1
                if result.get("reconciled"):
                    summary["reconcile"]["actions"].extend(
                        [f"{server.name}: {a}" for a in result["reconciled"]]
                    )
                if result.get("issues"):
                    summary["reconcile"]["actions"].extend(
                        [f"{server.name} ISSUE: {i}" for i in result["issues"]]
                    )
            except Exception as exc:
                summary["reconcile"]["actions"].append(
                    f"{server.name}: reconcile error — {exc}"
                )
    except Exception as exc:
        summary["reconcile"]["actions"].append(f"reconciler setup error: {exc}")

    # ── Step 2: Business invariant auto-fix ──────────────────────────────────
    try:
        bv = BusinessValidator(db)
        report = bv.run_all(auto_fix=True)
        summary["business_validator"]["violations"] = len(report.violations)
        summary["business_validator"]["auto_fixed"] = report.auto_fixed
        summary["business_validator"]["errors"] = report.errors_during_check[:10]
    except Exception as exc:
        summary["business_validator"]["errors"].append(str(exc))

    # ── Step 3: Rebuild proxy configs from DB ─────────────────────────────────
    try:
        proxy_servers = db.query(Server).filter(
            Server.server_category == "proxy",
            Server.lifecycle_status == "online",
        ).all()
        cm = ClientManager(db)
        for server in proxy_servers:
            summary["proxy_rebuild"]["servers_attempted"] += 1
            try:
                ok = cm._apply_proxy_config(server)
                if ok:
                    summary["proxy_rebuild"]["ok"].append(server.name)
                else:
                    summary["proxy_rebuild"]["failed"].append(
                        f"{server.name}: apply_proxy_config returned False"
                    )
            except Exception as exc:
                summary["proxy_rebuild"]["failed"].append(f"{server.name}: {exc}")
    except Exception as exc:
        summary["proxy_rebuild"]["failed"].append(f"proxy rebuild setup error: {exc}")

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()

    total_actions = (
        len(summary["reconcile"]["actions"])
        + summary["business_validator"]["auto_fixed"]
        + len(summary["proxy_rebuild"]["ok"])
    )
    summary["total_actions_taken"] = total_actions
    logger.info("[REPAIR] System repair completed: {} actions taken", total_actions)

    return summary
