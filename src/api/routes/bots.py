"""
VPN Management Studio API - Bot Management Routes
Telegram bot status and control
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import subprocess
import os
import re
from pathlib import Path

from ...database.connection import get_db
from ...database.models import SystemConfig, AuditLog, AuditAction
from ..middleware.license_gate import require_license_feature


router = APIRouter()

# Client Telegram bot is a Business+ feature. Admin bot stays in FREE.
_client_bot_gate = Depends(require_license_feature("telegram_client_bot"))

# Service names — configurable via env vars to support different install prefixes
# (e.g. "spongebot-admin-bot" on legacy installs, "vpnmanager-admin-bot" on new ones)
_ADMIN_BOT_SERVICE  = os.getenv("ADMIN_BOT_SERVICE",  "vpnmanager-admin-bot")
_CLIENT_BOT_SERVICE = os.getenv("CLIENT_BOT_SERVICE", "vpnmanager-client-bot")


# ============================================================================
# SCHEMAS
# ============================================================================

class BotStatusResponse(BaseModel):
    """Bot status response"""
    bot_type: str
    is_running: bool
    pid: Optional[int]
    uptime: Optional[str]
    status: str


class BotConfigUpdate(BaseModel):
    """Bot configuration update"""
    token: Optional[str] = Field(None, description="Telegram bot token")
    allowed_users: Optional[list] = Field(None, description="List of allowed user IDs")


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
    """Get systemd service status"""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True
        )
        is_active = result.stdout.strip() == "active"

        pid = None
        uptime = None

        if is_active:
            # Get PID
            pid_result = subprocess.run(
                ["systemctl", "show", service_name, "-p", "MainPID", "--value"],
                capture_output=True,
                text=True
            )
            try:
                pid = int(pid_result.stdout.strip())
            except ValueError:
                pass

            # Get uptime from systemctl status output
            try:
                uptime_result = subprocess.run(
                    ["systemctl", "status", service_name, "--no-pager"],
                    capture_output=True,
                    text=True
                )
                for line in uptime_result.stdout.splitlines():
                    if 'Active:' in line and 'since' in line:
                        parts = line.split(';')
                        if len(parts) >= 2:
                            uptime = parts[-1].strip()
                        break
            except Exception:
                pass

        return {
            "is_running": is_active,
            "pid": pid,
            "uptime": uptime,
            "status": "running" if is_active else "stopped"
        }

    except Exception as e:
        return {
            "is_running": False,
            "pid": None,
            "uptime": None,
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


TOKEN_PATTERN = re.compile(r"^\d+:[A-Za-z0-9_-]+$")

ENV_FILE_PATH = Path(__file__).resolve().parents[3] / ".env"


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

    # Append any keys not found in the file
    for key, value in updates.items():
        if key not in keys_updated:
            new_lines.append(f"{key}={value}")

    # Atomic write: write to temp file in same directory, then rename
    content = "\n".join(new_lines) + "\n"
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(env_path.parent), suffix=".tmp")
    try:
        os.write(tmp_fd, content.encode())
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


# ============================================================================
# CONFIG ENDPOINTS
# ============================================================================

@router.get("/config")
async def get_bot_config(db: Session = Depends(get_db)):
    """Get current bot configuration (tokens masked)"""
    admin_token = os.getenv("ADMIN_BOT_TOKEN", "")
    admin_users = os.getenv("ADMIN_BOT_ALLOWED_USERS", "")
    client_token = os.getenv("CLIENT_BOT_TOKEN", "")
    client_enabled = os.getenv("CLIENT_BOT_ENABLED", "false").lower() == "true"

    return {
        "admin_bot_token_masked": mask_token(admin_token) if admin_token else "",
        "admin_allowed_users": admin_users,
        "client_bot_token_masked": mask_token(client_token) if client_token else "",
        "client_bot_enabled": client_enabled,
    }


@router.post("/config")
async def update_bot_config(config: BotConfigRequest, db: Session = Depends(get_db)):
    """Update bot configuration — writes to .env and saves to SystemConfig"""
    env_updates = {}
    changes = {}

    # Validate and prepare admin bot token
    if config.admin_bot_token:
        if not TOKEN_PATTERN.match(config.admin_bot_token):
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
            cleaned = ",".join(parts)
        env_updates["ADMIN_BOT_ALLOWED_USERS"] = cleaned
        changes["admin_allowed_users"] = cleaned

    # Validate client bot token
    if config.client_bot_token:
        if not TOKEN_PATTERN.match(config.client_bot_token):
            raise HTTPException(
                status_code=400,
                detail="Invalid client bot token format. Expected: digits:alphanumeric"
            )
        env_updates["CLIENT_BOT_TOKEN"] = config.client_bot_token
        changes["client_bot_token"] = mask_token(config.client_bot_token)

    # Client bot enabled toggle
    if config.client_bot_enabled is not None:
        env_updates["CLIENT_BOT_ENABLED"] = str(config.client_bot_enabled).lower()
        changes["client_bot_enabled"] = config.client_bot_enabled

    if not env_updates:
        raise HTTPException(status_code=400, detail="No configuration changes provided")

    # Update .env file
    update_env_file(env_updates)

    # Update current process environment so GET /config returns fresh values
    for key, value in env_updates.items():
        os.environ[key] = value

    # Save to SystemConfig for persistence
    for key, value in env_updates.items():
        existing = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if existing:
            existing.value = value
        else:
            db.add(SystemConfig(key=key, value=value, value_type="string"))

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
    if "CLIENT_BOT_TOKEN" in env_updates or "CLIENT_BOT_ENABLED" in env_updates:
        restart_results["client_bot"] = "restarted" if control_service(_CLIENT_BOT_SERVICE, "restart") else "restart_failed"

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
    status = get_service_status(_ADMIN_BOT_SERVICE)
    return BotStatusResponse(
        bot_type="admin",
        **status
    )


@router.post("/admin/start")
async def start_admin_bot():
    """
    Start the admin Telegram bot
    """
    if not control_service(_ADMIN_BOT_SERVICE, "start"):
        raise HTTPException(status_code=500, detail="Failed to start admin bot")

    return {"message": "Admin bot started", "status": "running"}


@router.post("/admin/stop")
async def stop_admin_bot():
    """
    Stop the admin Telegram bot
    """
    if not control_service(_ADMIN_BOT_SERVICE, "stop"):
        raise HTTPException(status_code=500, detail="Failed to stop admin bot")

    return {"message": "Admin bot stopped", "status": "stopped"}


@router.post("/admin/restart")
async def restart_admin_bot():
    """
    Restart the admin Telegram bot
    """
    if not control_service(_ADMIN_BOT_SERVICE, "restart"):
        raise HTTPException(status_code=500, detail="Failed to restart admin bot")

    return {"message": "Admin bot restarted", "status": "running"}


# ============================================================================
# CLIENT BOT ENDPOINTS
# ============================================================================

@router.get("/client/status", response_model=BotStatusResponse)
async def get_client_bot_status():
    """
    Get client bot status
    """
    status = get_service_status(_CLIENT_BOT_SERVICE)
    return BotStatusResponse(
        bot_type="client",
        **status
    )


@router.post("/client/start", dependencies=[_client_bot_gate])
async def start_client_bot():
    """
    Start the client Telegram bot
    """
    if not control_service(_CLIENT_BOT_SERVICE, "start"):
        raise HTTPException(status_code=500, detail="Failed to start client bot")

    return {"message": "Client bot started", "status": "running"}


@router.post("/client/stop", dependencies=[_client_bot_gate])
async def stop_client_bot():
    """
    Stop the client Telegram bot
    """
    if not control_service(_CLIENT_BOT_SERVICE, "stop"):
        raise HTTPException(status_code=500, detail="Failed to stop client bot")

    return {"message": "Client bot stopped", "status": "stopped"}


@router.post("/client/restart", dependencies=[_client_bot_gate])
async def restart_client_bot():
    """
    Restart the client Telegram bot
    """
    if not control_service(_CLIENT_BOT_SERVICE, "restart"):
        raise HTTPException(status_code=500, detail="Failed to restart client bot")

    return {"message": "Client bot restarted", "status": "running"}


# ============================================================================
# COMBINED ENDPOINTS
# ============================================================================

@router.get("/status")
async def get_all_bots_status():
    """
    Get status of all bots
    """
    admin_status = get_service_status(_ADMIN_BOT_SERVICE)
    client_status = get_service_status(_CLIENT_BOT_SERVICE)

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
async def restart_all_bots():
    """
    Restart all bots
    """
    admin_result = control_service(_ADMIN_BOT_SERVICE, "restart")
    client_result = control_service(_CLIENT_BOT_SERVICE, "restart")

    return {
        "admin_bot": "restarted" if admin_result else "failed",
        "client_bot": "restarted" if client_result else "failed"
    }
