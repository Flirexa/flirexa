"""
Flirexa API - Bot Management Routes
Telegram bot status and control
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
import subprocess
import os
import re
import threading
from pathlib import Path

from ...database.connection import get_db
from ...database.models import SystemConfig, AuditLog, AuditAction
from ..middleware.license_gate import require_license_feature


router = APIRouter()

# Client Telegram bot is a Business+ feature. Admin bot stays in FREE.
_client_bot_gate = Depends(require_license_feature("telegram_client_bot"))

# Service names — configurable via env vars to support different install prefixes
# Legacy installs may still use the pre-Flirexa systemd prefix.
_ADMIN_BOT_SERVICE  = os.getenv("ADMIN_BOT_SERVICE",  "vpnmanager-admin-bot")


# ============================================================================
# SCHEMAS
# ============================================================================

class BotStatusResponse(BaseModel):
    """Bot status response"""
    bot_type: str
    is_running: bool
    pid: Optional[int]
    uptime: Optional[str]
    uptime_seconds: Optional[int] = None
    status: str
    service: str
    configured: bool
    enabled: bool


class BotConfigRequest(BaseModel):
    """Full bot configuration update request"""
    admin_bot_token: Optional[str] = None
    admin_allowed_users: Optional[str] = None
    client_bot_token: Optional[str] = None
    client_bot_enabled: Optional[bool] = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_service_status(service_name: str) -> dict:
    """Get a bounded, machine-readable systemd service status snapshot."""
    try:
        result = subprocess.run(
            [
                "systemctl", "show", service_name, "--no-pager",
                "--property=LoadState", "--property=ActiveState",
                "--property=SubState", "--property=MainPID",
                "--property=ActiveEnterTimestampMonotonic",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        props = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                props[key] = value

        is_active = props.get("ActiveState") == "active"
        try:
            raw_pid = int(props.get("MainPID", "0"))
            pid = raw_pid or None
        except ValueError:
            pid = None

        uptime_seconds = None
        if is_active:
            try:
                entered_us = int(props.get("ActiveEnterTimestampMonotonic", "0"))
                boot_seconds = float(Path("/proc/uptime").read_text().split()[0])
                if entered_us > 0:
                    uptime_seconds = max(0, int(boot_seconds - entered_us / 1_000_000))
            except (OSError, ValueError, IndexError):
                pass

        load_state = props.get("LoadState", "unknown")
        if load_state == "not-found":
            status_text = "service_not_found"
        elif is_active:
            status_text = props.get("SubState") or "running"
        else:
            status_text = props.get("ActiveState") or "stopped"

        return {
            "is_running": is_active,
            "pid": pid,
            "uptime": None,
            "uptime_seconds": uptime_seconds,
            "status": status_text,
            "service": service_name,
        }

    except Exception as e:
        return {
            "is_running": False,
            "pid": None,
            "uptime": None,
            "uptime_seconds": None,
            "service": service_name,
            "status": f"error: {str(e)}"
        }


def control_service(service_name: str, action: str) -> bool:
    """Control systemd service (start/stop/restart)"""
    try:
        result = subprocess.run(
            ["systemctl", action, service_name],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False


TOKEN_PATTERN = re.compile(r"^\d{6,14}:[A-Za-z0-9_-]{20,}$")

ENV_FILE_PATH = Path(__file__).resolve().parents[3] / ".env"
_ENV_WRITE_LOCK = threading.Lock()


def mask_token(token: str) -> str:
    """Mask a bot token, showing only first 4 and last 4 characters"""
    if not token or len(token) < 10:
        return "****"
    return token[:4] + ":" + "*" * (len(token) - 9) + token[-4:]


def update_env_file(updates: dict):
    """Update key=value pairs in the .env file (atomic write)"""
    import tempfile

    env_path = ENV_FILE_PATH
    if not env_path.exists():
        raise HTTPException(status_code=500, detail=".env file not found")

    # Serialise writers in this API process. The rename remains atomic for
    # readers, while this lock prevents two simultaneous settings requests
    # from silently discarding one another's keys.
    with _ENV_WRITE_LOCK:
        lines = env_path.read_text().splitlines()
        keys_updated = set()

        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0]
                if key in updates:
                    new_lines.append(f"{key}={updates[key]}")
                    keys_updated.add(key)
                    continue
            new_lines.append(line)

        for key, value in updates.items():
            if key not in keys_updated:
                new_lines.append(f"{key}={value}")

        content = "\n".join(new_lines) + "\n"
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(env_path.parent), suffix=".tmp")
        try:
            os.fchmod(tmp_fd, 0o600)
            os.write(tmp_fd, content.encode())
            os.fsync(tmp_fd)
            os.close(tmp_fd)
            os.replace(tmp_path, str(env_path))
        except Exception:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise


def _bot_runtime_flags(bot_type: str) -> dict:
    if bot_type == "admin":
        return {
            "configured": bool(os.getenv("ADMIN_BOT_TOKEN", "").strip()),
            "enabled": bool(os.getenv("ADMIN_BOT_TOKEN", "").strip()) and bool(
                os.getenv("ADMIN_BOT_ALLOWED_USERS", "").strip()
            ),
        }
    return {
        "configured": bool(os.getenv("CLIENT_BOT_TOKEN", "").strip()),
        "enabled": os.getenv("CLIENT_BOT_ENABLED", "false").lower() == "true",
    }


def _status_payload(bot_type: str, service_name: str) -> dict:
    return {
        **get_service_status(service_name),
        **_bot_runtime_flags(bot_type),
    }


def _audit_control(db: Session, bot_type: str, action: str) -> None:
    audit_action = {
        "start": AuditAction.SYSTEM_START,
        "stop": AuditAction.SYSTEM_STOP,
        "restart": AuditAction.CONFIG_CHANGE,
    }[action]
    db.add(AuditLog(
        user_type="admin",
        action=audit_action,
        target_type="telegram_bot",
        target_name=bot_type,
        details={"channel": "admin_panel", "action": action},
    ))
    db.commit()


def _redact_log_line(line: str) -> str:
    result = line
    for token in (os.getenv("ADMIN_BOT_TOKEN", ""), os.getenv("CLIENT_BOT_TOKEN", "")):
        if token:
            result = result.replace(token, "[REDACTED_BOT_TOKEN]")
    # Defence in depth for a token printed by a dependency or old release.
    return re.sub(r"\b\d{6,14}:[A-Za-z0-9_-]{20,}\b", "[REDACTED_BOT_TOKEN]", result)


def _read_service_logs(service_name: str, limit: int) -> list[dict]:
    try:
        result = subprocess.run(
            [
                "journalctl", "--unit", service_name, "--no-pager",
                "--output=short-iso", "--lines", str(limit),
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Bot logs are unavailable: {exc}")
    if result.returncode != 0:
        raise HTTPException(status_code=503, detail="Bot logs are unavailable")

    entries = []
    for raw_line in result.stdout.splitlines():
        line = _redact_log_line(raw_line.strip())
        if not line or line.startswith("-- No entries --"):
            continue
        lowered = line.lower()
        level = "error" if any(x in lowered for x in (" error", "exception", "traceback", "failed")) else (
            "warning" if any(x in lowered for x in (" warning", "warn:")) else "info"
        )
        entries.append({"message": line[:2000], "level": level})
    return entries


# ============================================================================
# CONFIG ENDPOINTS
# ============================================================================

@router.get("/config")
async def get_bot_config(db: Session = Depends(get_db)):
    """Get current bot configuration (tokens masked)"""
    from ...modules.client_bot_admin import get_client_config

    admin_token = os.getenv("ADMIN_BOT_TOKEN", "")
    admin_users = os.getenv("ADMIN_BOT_ALLOWED_USERS", "")
    result = {
        "admin_bot_token_masked": mask_token(admin_token) if admin_token else "",
        "admin_allowed_users": admin_users,
    }
    result.update(get_client_config(mask_token))
    try:
        from ...modules.license.manager import get_license_manager
        result["client_bot_available"] = get_license_manager().has_feature(
            "telegram_client_bot"
        )
    except Exception:
        result["client_bot_available"] = False
    return result


@router.post("/config")
def update_bot_config(config: BotConfigRequest, db: Session = Depends(get_db)):
    """Update bot configuration — writes to .env and saves to SystemConfig"""
    from ...modules.client_bot_admin import (
        prepare_client_config,
        restart_after_config,
    )

    env_updates = {}
    changes = {}

    # Validate and prepare admin bot token
    if config.admin_bot_token:
        if not TOKEN_PATTERN.fullmatch(config.admin_bot_token):
            raise HTTPException(
                status_code=400,
                detail="Invalid admin bot token format. Expected: digits:alphanumeric"
            )
        env_updates["ADMIN_BOT_TOKEN"] = config.admin_bot_token
        changes["admin_bot_token"] = mask_token(config.admin_bot_token)

    # Validate admin allowed users (comma-separated integers)
    if config.admin_allowed_users is not None:
        cleaned = config.admin_allowed_users.strip()
        if cleaned:
            parts = [p.strip() for p in cleaned.split(",")]
            for part in parts:
                if not part.isdigit():
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid user ID: '{part}'. Must be numeric."
                    )
            cleaned = ",".join(dict.fromkeys(parts))
        env_updates["ADMIN_BOT_ALLOWED_USERS"] = cleaned
        changes["admin_allowed_users"] = cleaned

    client_env, client_changes = prepare_client_config(config, mask_token)
    env_updates.update(client_env)
    changes.update(client_changes)

    candidate_admin_token = env_updates.get(
        "ADMIN_BOT_TOKEN", os.getenv("ADMIN_BOT_TOKEN", "")
    )
    candidate_client_token = env_updates.get(
        "CLIENT_BOT_TOKEN", os.getenv("CLIENT_BOT_TOKEN", "")
    )
    if candidate_admin_token and candidate_admin_token == candidate_client_token:
        raise HTTPException(
            status_code=400,
            detail="Admin bot and client bot must use different Telegram bot tokens",
        )

    if not env_updates:
        raise HTTPException(status_code=400, detail="No configuration changes provided")

    # Update .env file
    update_env_file(env_updates)

    # Update current process environment so GET /config returns fresh values
    for key, value in env_updates.items():
        os.environ[key] = value

    # Save non-secret settings for consumers that use SystemConfig. Bot tokens
    # stay only in the protected .env file; persisting a second plaintext copy
    # in the database needlessly enlarges the secret exposure surface.
    for key, value in env_updates.items():
        if key in {"ADMIN_BOT_TOKEN", "CLIENT_BOT_TOKEN"}:
            continue
        existing = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if existing:
            existing.value = value
        else:
            db.add(SystemConfig(key=key, value=value, value_type="string"))

    db.query(SystemConfig).filter(
        SystemConfig.key.in_([
            "ADMIN_BOT_TOKEN", "admin_bot_token",
            "CLIENT_BOT_TOKEN", "client_bot_token",
        ])
    ).delete(synchronize_session=False)

    # Audit log
    db.add(AuditLog(
        user_type="admin",
        action=AuditAction.CONFIG_CHANGE,
        target_type="bot_config",
        target_name="bot_configuration",
        details=changes,
    ))

    db.commit()

    # Restart bots to pick up new config
    restart_results = {}
    if "ADMIN_BOT_TOKEN" in env_updates or "ADMIN_BOT_ALLOWED_USERS" in env_updates:
        restart_results["admin_bot"] = "restarted" if control_service(_ADMIN_BOT_SERVICE, "restart") else "restart_failed"
    client_restart = restart_after_config(env_updates, control_service)
    if client_restart is not None:
        restart_results["client_bot"] = client_restart

    return {
        "message": "Configuration updated successfully",
        "changes": changes,
        "restarts": restart_results,
    }


# ============================================================================
# ADMIN BOT ENDPOINTS
# ============================================================================

@router.get("/admin/status", response_model=BotStatusResponse)
async def get_admin_bot_status():
    """
    Get admin bot status
    """
    status = _status_payload("admin", _ADMIN_BOT_SERVICE)
    return BotStatusResponse(
        bot_type="admin",
        **status
    )


@router.post("/admin/start")
async def start_admin_bot(db: Session = Depends(get_db)):
    """
    Start the admin Telegram bot
    """
    flags = _bot_runtime_flags("admin")
    if not flags["configured"]:
        raise HTTPException(status_code=400, detail="Configure the admin bot token first")
    if not flags["enabled"]:
        raise HTTPException(status_code=400, detail="Add at least one allowed Telegram user ID first")
    if not control_service(_ADMIN_BOT_SERVICE, "start"):
        raise HTTPException(status_code=500, detail="Failed to start admin bot")

    _audit_control(db, "admin", "start")
    return {"message": "Admin bot started", "status": "running"}


@router.post("/admin/stop")
async def stop_admin_bot(db: Session = Depends(get_db)):
    """
    Stop the admin Telegram bot
    """
    if not control_service(_ADMIN_BOT_SERVICE, "stop"):
        raise HTTPException(status_code=500, detail="Failed to stop admin bot")

    _audit_control(db, "admin", "stop")
    return {"message": "Admin bot stopped", "status": "stopped"}


@router.post("/admin/restart")
async def restart_admin_bot(db: Session = Depends(get_db)):
    """
    Restart the admin Telegram bot
    """
    flags = _bot_runtime_flags("admin")
    if not flags["configured"] or not flags["enabled"]:
        raise HTTPException(status_code=400, detail="Configure the token and allowed user IDs first")
    if not control_service(_ADMIN_BOT_SERVICE, "restart"):
        raise HTTPException(status_code=500, detail="Failed to restart admin bot")

    _audit_control(db, "admin", "restart")
    return {"message": "Admin bot restarted", "status": "running"}


# ============================================================================
# CLIENT BOT ENDPOINTS
# ============================================================================

@router.get("/client/status", response_model=BotStatusResponse)
async def get_client_bot_status():
    """
    Get client bot status
    """
    from ...modules.client_bot_admin import get_client_status

    status = get_client_status(get_service_status)
    status.update(_bot_runtime_flags("client"))
    return BotStatusResponse(
        bot_type="client",
        **status
    )


@router.post("/client/start", dependencies=[_client_bot_gate])
async def start_client_bot(db: Session = Depends(get_db)):
    """
    Start the client Telegram bot
    """
    flags = _bot_runtime_flags("client")
    if not flags["configured"]:
        raise HTTPException(status_code=400, detail="Configure the client bot token first")
    if not flags["enabled"]:
        raise HTTPException(status_code=400, detail="Enable the client bot first")
    from ...modules.client_bot_admin import control_client

    if not control_client("start", control_service):
        raise HTTPException(status_code=500, detail="Failed to start client bot")

    _audit_control(db, "client", "start")
    return {"message": "Client bot started", "status": "running"}


@router.post("/client/stop")
async def stop_client_bot(db: Session = Depends(get_db)):
    """
    Stop the client Telegram bot.

    Stopping a local service remains available even when a paid entitlement is
    unavailable. Operators must always be able to contain a misconfigured bot;
    entitlement is required only to start or restart the commercial service.
    """
    from ...modules.client_bot_admin import control_client

    if not control_client("stop", control_service):
        raise HTTPException(status_code=500, detail="Failed to stop client bot")

    _audit_control(db, "client", "stop")
    return {"message": "Client bot stopped", "status": "stopped"}


@router.post("/client/restart", dependencies=[_client_bot_gate])
async def restart_client_bot(db: Session = Depends(get_db)):
    """
    Restart the client Telegram bot
    """
    flags = _bot_runtime_flags("client")
    if not flags["configured"] or not flags["enabled"]:
        raise HTTPException(status_code=400, detail="Configure and enable the client bot first")
    from ...modules.client_bot_admin import control_client

    if not control_client("restart", control_service):
        raise HTTPException(status_code=500, detail="Failed to restart client bot")

    _audit_control(db, "client", "restart")
    return {"message": "Client bot restarted", "status": "running"}


@router.get("/{bot_type}/logs")
async def get_bot_logs(
    bot_type: str,
    limit: int = Query(100, ge=20, le=300),
):
    """Return a bounded, token-redacted journal tail for one bot service."""
    services = {
        "admin": _ADMIN_BOT_SERVICE,
        "client": os.getenv("CLIENT_BOT_SERVICE", "vpnmanager-client-bot"),
    }
    service = services.get(bot_type)
    if not service:
        raise HTTPException(status_code=404, detail="Unknown bot type")
    return {
        "bot_type": bot_type,
        "service": service,
        "entries": _read_service_logs(service, limit),
    }


# ============================================================================
# COMBINED ENDPOINTS
# ============================================================================

@router.get("/status")
async def get_all_bots_status():
    """
    Get status of all bots
    """
    admin_status = _status_payload("admin", _ADMIN_BOT_SERVICE)
    from ...modules.client_bot_admin import get_client_status

    client_status = get_client_status(get_service_status)
    client_status.update(_bot_runtime_flags("client"))

    return {
        "admin_bot": {
            "bot_type": "admin",
            **admin_status
        },
        "client_bot": {
            "bot_type": "client",
            **client_status
        }
    }


@router.post("/restart-all")
async def restart_all_bots(db: Session = Depends(get_db)):
    """Restart only configured/enabled bots and audit successful actions."""
    admin_flags = _bot_runtime_flags("admin")
    if admin_flags["configured"] and admin_flags["enabled"]:
        admin_ok = control_service(_ADMIN_BOT_SERVICE, "restart")
        admin_result = "restarted" if admin_ok else "failed"
        if admin_ok:
            _audit_control(db, "admin", "restart")
    else:
        admin_result = "not_configured"

    from ...modules.client_bot_admin import restart_client_if_entitled

    client_flags = _bot_runtime_flags("client")
    if client_flags["configured"] and client_flags["enabled"]:
        client_ok = restart_client_if_entitled(control_service)
        client_result = "restarted" if client_ok else "not_available"
        if client_ok:
            _audit_control(db, "client", "restart")
    else:
        client_result = "not_configured"

    return {
        "admin_bot": admin_result,
        "client_bot": client_result,
    }
