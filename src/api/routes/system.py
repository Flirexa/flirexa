"""
System Routes — status, logs, configuration, branding
"""

from typing import Optional, List, Literal
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
async def get_system_status(
    db: Session = Depends(get_db)
):
    """
    Get overall system status including servers, clients, and resources
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
        version="5.0.0",
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
async def get_audit_logs(
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
        "version": "5.0.0",
        "api_version": "v1",
        "platform": platform.system(),
        "platform_release": platform.release(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "architecture": platform.machine(),
    }


@router.get("/health")
async def health_check(
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
async def get_license_status(db: Session = Depends(get_db)):
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
    """Activate a license key"""
    from ...modules.license.manager import LicenseManager, reset_license_manager

    # Validate the new key
    mgr = LicenseManager(data.license_key)
    info = mgr.validate_license()

    if info.type.value == "trial" and "Invalid" in info.validation_message:
        raise HTTPException(status_code=400, detail=info.validation_message)

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
        logger.warning("License enforcement reconcile after activation failed: %s", exc)

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

    # Try primary, then backup. Both must speak /api/activate/replay (deployed
    # on flirexa.biz + global-connection.site as of license-server change on
    # 2026-05-01).
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

                # Validate signature locally before persisting
                mgr  = LicenseManager(license_key)
                info = mgr.validate_license()
                if info.type.value == "trial" and "Invalid" in info.validation_message:
                    raise HTTPException(status_code=400, detail=info.validation_message)

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
                    logger.warning("License enforcement reconcile after replay failed: %s", exc)

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
    branding_company_name: Optional[str] = Field(None, max_length=200)
    branding_logo_url: Optional[str] = Field(None, max_length=500)
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
    db: Session = Depends(get_db)
):
    """Upload a branding logo image"""
    # Validate file type
    allowed_types = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Invalid file type: {file.content_type}. Allowed: png, jpg, svg, webp")

    # Validate size (max 2MB)
    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 2MB)")

    # Save to static directory
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web", "static")
    os.makedirs(static_dir, exist_ok=True)

    allowed_exts = {"png", "jpg", "jpeg", "svg", "webp"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "png"
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"Invalid file extension: {ext}")
    filename = f"brand-logo-{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(static_dir, filename)
    # Verify path is within static directory
    if not os.path.abspath(filepath).startswith(os.path.abspath(static_dir)):
        raise HTTPException(status_code=400, detail="Invalid filename")

    with open(filepath, "wb") as f:
        f.write(contents)

    # Save URL to branding config
    logo_url = f"/static/{filename}"
    set_branding({"branding_logo_url": logo_url}, db)

    return {"message": "Logo uploaded", "url": logo_url}


# ============================================================================
# PAYMENT SETTINGS
# ============================================================================

class PaymentSettingsUpdate(BaseModel):
    cryptopay_api_token: Optional[str] = None
    cryptopay_testnet: bool = False
    paypal_client_id: Optional[str] = None
    paypal_client_secret: Optional[str] = None
    paypal_sandbox: Optional[bool] = None
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
            from ...modules.subscription.crypto_payment import CryptoPaymentProvider
            client_portal.nowpayments_provider = CryptoPaymentProvider(
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
    return {
        "status": "ok",
        "connected": any_connected,
        "message": "Settings updated",
        "providers": results,
    }


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
async def apply_web_access_settings(data: WebAccessSettingsUpdate):
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
async def get_notification_settings(db: Session = Depends(get_db)):
    """Get notification settings"""
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
    ]
    rows = db.query(SystemConfig).filter(SystemConfig.key.in_(keys)).all()
    settings = {r.key: r.value for r in rows}

    return {k: settings.get(k, "true") for k in keys}


@router.post("/notification-settings")
async def update_notification_settings(data: dict, db: Session = Depends(get_db)):
    """Update notification settings"""
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
# BACKUP SETTINGS
# ============================================================================

BACKUP_CONFIG_KEYS = [
    "backup_enabled", "backup_interval_hours", "backup_hour_utc",
    "backup_retention_count", "backup_auto_cleanup",
    "backup_storage_type", "backup_path",
    "backup_mount_type", "backup_mount_address",
    "backup_mount_username", "backup_mount_password",
    "backup_mount_point", "backup_mount_options",
]

BACKUP_DEFAULTS = {
    "backup_enabled": "true",
    "backup_interval_hours": "24",
    "backup_hour_utc": "3",
    "backup_retention_count": "7",
    "backup_auto_cleanup": "true",
    "backup_storage_type": "local",
    "backup_path": str(Path(__file__).parent.parent.parent.parent / "backups"),
    "backup_mount_type": "smb",
    "backup_mount_address": "",
    "backup_mount_username": "",
    "backup_mount_password": "",
    "backup_mount_point": "/mnt/vpnmanager-backup",
    "backup_mount_options": "",
}


@router.get("/backup-settings")
async def get_backup_settings(db: Session = Depends(get_db)):
    """Get all backup configuration from SystemConfig"""
    from ...database.models import SystemConfig
    rows = db.query(SystemConfig).filter(SystemConfig.key.in_(BACKUP_CONFIG_KEYS)).all()
    settings = {r.key: r.value for r in rows}

    result = {}
    for key in BACKUP_CONFIG_KEYS:
        val = settings.get(key, BACKUP_DEFAULTS.get(key, ""))
        # Mask password
        if key == "backup_mount_password" and val:
            result[key] = "••••••"
            result["backup_mount_password_set"] = True
        else:
            result[key] = val
    if "backup_mount_password" not in result or not settings.get("backup_mount_password"):
        result["backup_mount_password_set"] = False

    return result


def _validate_backup_path(path: str) -> str:
    """Validate backup path to prevent dangerous locations"""
    import re
    path = path.strip()
    if not path or not path.startswith("/"):
        raise HTTPException(status_code=400, detail="Path must be absolute (start with /)")
    # Normalize and block dangerous paths
    normalized = os.path.normpath(path)
    dangerous = ["/", "/etc", "/usr", "/bin", "/sbin", "/lib", "/boot", "/dev", "/proc", "/sys", "/var", "/root"]
    if normalized in dangerous:
        raise HTTPException(status_code=400, detail=f"Dangerous path: {normalized}")
    # Block path traversal
    if ".." in path:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    return normalized


def _validate_mount_options(options: str) -> str:
    """Validate mount options to prevent injection"""
    import re
    options = options.strip()
    if not options:
        return ""
    # Only allow alphanumeric, dots, commas, equals, underscores, hyphens, slashes
    if not re.match(r'^[a-zA-Z0-9.,=_\-/]+$', options):
        raise HTTPException(status_code=400, detail="Invalid characters in mount options")
    return options


@router.post("/backup-settings")
async def update_backup_settings(data: dict, db: Session = Depends(get_db)):
    """Update backup settings in SystemConfig"""
    from ...database.models import SystemConfig

    # Validate values before saving
    if "backup_path" in data and data["backup_path"]:
        data["backup_path"] = _validate_backup_path(data["backup_path"])
    if "backup_mount_point" in data and data["backup_mount_point"]:
        data["backup_mount_point"] = _validate_backup_path(data["backup_mount_point"])
    if "backup_mount_options" in data:
        data["backup_mount_options"] = _validate_mount_options(data.get("backup_mount_options", ""))
    if "backup_interval_hours" in data:
        try:
            val = int(data["backup_interval_hours"])
            if val not in (6, 12, 24, 48, 168):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid interval_hours, must be 6/12/24/48/168")
    if "backup_hour_utc" in data:
        try:
            val = int(data["backup_hour_utc"])
            if not (0 <= val <= 23):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid hour_utc, must be 0-23")
    if "backup_retention_count" in data:
        try:
            val = int(data["backup_retention_count"])
            if not (1 <= val <= 100):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid retention_count, must be 1-100")

    updated = 0
    for key, value in data.items():
        if key not in BACKUP_CONFIG_KEYS:
            continue
        # Don't overwrite password with mask placeholder
        if key == "backup_mount_password" and value == "••••••":
            continue
        existing = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if existing:
            existing.value = str(value)
        else:
            db.add(SystemConfig(key=key, value=str(value)))
        updated += 1

    db.commit()
    return {"message": f"Updated {updated} backup settings"}


@router.post("/backup-mount", dependencies=[_auto_backup_gate])
async def mount_network_storage(db: Session = Depends(get_db)):
    """Mount network storage using saved settings"""
    from ...database.models import SystemConfig
    import subprocess

    def _get(key):
        row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        return row.value if row else BACKUP_DEFAULTS.get(key, "")

    mount_type = _get("backup_mount_type")
    address = _get("backup_mount_address")
    username = _get("backup_mount_username")
    password = _get("backup_mount_password")
    mount_point = _get("backup_mount_point")
    options = _get("backup_mount_options")

    if not address or not mount_point:
        raise HTTPException(status_code=400, detail="Address and mount point are required")

    # Validate mount point path
    mount_point = _validate_backup_path(mount_point)

    # Validate options
    if options:
        options = _validate_mount_options(options)

    # Create mount point if needed
    os.makedirs(mount_point, exist_ok=True)

    # Build mount command
    if mount_type == "nfs":
        cmd = ["mount", "-t", "nfs"]
        if options:
            cmd += ["-o", options]
        cmd += [address, mount_point]
    else:
        # SMB/CIFS
        opts_parts = []
        if username:
            opts_parts.append(f"username={username}")
        if password:
            opts_parts.append(f"password={password}")
        if options:
            opts_parts.append(options)
        cmd = ["mount", "-t", "cifs"]
        if opts_parts:
            cmd += ["-o", ",".join(opts_parts)]
        cmd += [address, mount_point]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30, text=True)
        if result.returncode == 0:
            return {"status": "ok", "message": f"Mounted {address} at {mount_point}"}
        else:
            raise HTTPException(status_code=500, detail=f"Mount failed: {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Mount timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="mount command not found")


@router.post("/backup-unmount", dependencies=[_auto_backup_gate])
async def unmount_network_storage(db: Session = Depends(get_db)):
    """Unmount network storage"""
    from ...database.models import SystemConfig
    import subprocess

    row = db.query(SystemConfig).filter(SystemConfig.key == "backup_mount_point").first()
    mount_point = row.value if row else BACKUP_DEFAULTS["backup_mount_point"]
    mount_point = _validate_backup_path(mount_point)

    try:
        result = subprocess.run(["umount", mount_point], capture_output=True, timeout=15, text=True)
        if result.returncode == 0:
            return {"status": "ok", "message": f"Unmounted {mount_point}"}
        else:
            raise HTTPException(status_code=500, detail=f"Unmount failed: {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Unmount timed out")


@router.get("/backup-mount-status")
async def get_mount_status(db: Session = Depends(get_db)):
    """Check if network storage is mounted"""
    from ...database.models import SystemConfig
    import subprocess

    row = db.query(SystemConfig).filter(SystemConfig.key == "backup_mount_point").first()
    mount_point = row.value if row else BACKUP_DEFAULTS["backup_mount_point"]

    try:
        result = subprocess.run(["mountpoint", "-q", mount_point], capture_output=True, timeout=5)
        mounted = result.returncode == 0
    except Exception:
        mounted = False

    return {"mounted": mounted, "mount_point": mount_point}


@router.post("/backup-test-write", dependencies=[_auto_backup_gate])
async def test_backup_write(db: Session = Depends(get_db)):
    """Test write access to the backup directory"""
    from ...database.models import SystemConfig

    row = db.query(SystemConfig).filter(SystemConfig.key == "backup_storage_type").first()
    storage_type = row.value if row else "local"

    if storage_type == "network":
        path_row = db.query(SystemConfig).filter(SystemConfig.key == "backup_mount_point").first()
        test_path = path_row.value if path_row else BACKUP_DEFAULTS["backup_mount_point"]
    else:
        path_row = db.query(SystemConfig).filter(SystemConfig.key == "backup_path").first()
        test_path = path_row.value if path_row else BACKUP_DEFAULTS["backup_path"]

    try:
        os.makedirs(test_path, exist_ok=True)
        test_file = os.path.join(test_path, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return {"status": "ok", "message": f"Write OK: {test_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Write failed: {str(e)}")


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
async def send_notification(data: SendNotificationRequest, db: Session = Depends(get_db)):
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
async def list_notifications(
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
    logger.info("[REPAIR] System repair completed: %d actions taken", total_actions)

    return summary
