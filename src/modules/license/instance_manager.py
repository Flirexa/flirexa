"""
Instance Manager — persistent registration and periodic heartbeat.

Sends POST /instance/heartbeat to the license server every 5 minutes,
regardless of license status (none / trial / active / expired / revoked).

Each installation gets a permanent instance_id (UUID4) stored in .env.
The heartbeat is HMAC-SHA256 signed with a key derived from machine_id + instance_id.
The server responds with the current primary and backup server list,
which the client saves locally for failover.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import socket
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
import certifi

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 300   # 5 minutes
_REQUEST_TIMEOUT    = 10    # seconds per server attempt

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

# Module-level start time (uptime counter)
_start_time = time.time()
_heartbeat_task: Optional[asyncio.Task] = None


# ── .env helpers ──────────────────────────────────────────────────────────────

def _find_env_file() -> Optional[str]:
    candidates = [
        os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".env")),
        "/opt/vpnmanager/.env",
        "/opt/vpnmanager/.env",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _save_env(key: str, value: str) -> None:
    path = _find_env_file()
    if not path:
        return
    try:
        with open(path) as f:
            content = f.read()
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        else:
            if not content.endswith("\n"):
                content += "\n"
            content += f"{replacement}\n"
        with open(path, "w") as f:
            f.write(content)
    except Exception as e:
        logger.debug("Could not save %s to .env: %s", key, e)


# ── Instance ID ───────────────────────────────────────────────────────────────

def get_instance_id() -> str:
    """Return the persistent instance UUID (generate and save on first call)."""
    env_id = os.getenv("INSTANCE_ID", "").strip()
    if env_id and len(env_id) >= 8:
        return env_id
    new_id = str(uuid.uuid4())
    os.environ["INSTANCE_ID"] = new_id
    _save_env("INSTANCE_ID", new_id)
    logger.info("Generated new instance ID: %s", new_id)
    return new_id


# ── Hardware ID ───────────────────────────────────────────────────────────────

def _get_hardware_id() -> str:
    """Same fingerprint as LicenseManager.get_server_id()."""
    import platform
    try:
        components = [platform.node(), platform.machine(), str(uuid.getnode())]
        try:
            if os.path.exists("/etc/machine-id"):
                with open("/etc/machine-id") as f:
                    components.append(f.read().strip())
        except Exception:
            pass
        return hashlib.sha256("|".join(components).encode()).hexdigest()[:32]
    except Exception:
        return hashlib.sha256(b"unknown").hexdigest()[:32]


# ── License status ────────────────────────────────────────────────────────────

def _get_license_status() -> tuple:
    """Return (status_str, masked_activation_code, license_id_prefix)."""
    try:
        from .manager import get_license_manager
        from .online_validator import get_online_status

        mgr  = get_license_manager()
        info = mgr.get_license_info()
        online = get_online_status()  # "ok" / "revoked" / "suspended" / None / ...

        if online == "revoked" or online == "suspended":
            status = "revoked"
        elif not info.is_valid:
            status = "expired"
        elif info.type.value == "trial":
            status = "trial"
        elif online == "ok":
            status = "active"
        elif info.is_expired():
            status = "expired"
        else:
            status = "none"

    except Exception:
        status = "none"

    raw_code = os.getenv("ACTIVATION_CODE", "")
    masked = ""
    if raw_code:
        parts = raw_code.replace("-", "")
        masked = (parts[:4] + "-****-****-****") if len(parts) >= 4 else "****"

    license_key = os.getenv("LICENSE_KEY", "")
    license_id  = hashlib.sha256(license_key.encode()).hexdigest()[:16] if license_key else ""

    return status, masked, license_id


# ── HMAC signature ────────────────────────────────────────────────────────────

def _sign_heartbeat(body: dict, machine_id: str, instance_id: str) -> str:
    key = hashlib.sha256((machine_id + ":" + instance_id).encode()).digest()
    msg = json.dumps(
        {k: v for k, v in sorted(body.items())},
        separators=(",", ":"),
    ).encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


# ── Server list management ────────────────────────────────────────────────────

_DYN_PATH = Path(__file__).parent.parent.parent.parent / "data" / "hb_servers.json"
_DYN_MAX_AGE = 86400 * 30   # 30 days


def _get_server_urls() -> list:
    """
    Priority:
      1. Dynamic list saved from last successful heartbeat (if < 30 days old, HMAC verified)
      2. Signed license server config
      3. Env vars (dev/test)
    """
    try:
        if _DYN_PATH.exists():
            data = json.loads(_DYN_PATH.read_text())
            if time.time() - data.get("saved_at", 0) < _DYN_MAX_AGE:
                stored_hmac = data.get("hmac", "")
                if stored_hmac:
                    expected = _hmac_server_list(data)
                    if not hmac.compare_digest(stored_hmac, expected):
                        logger.warning(
                            "hb_servers.json HMAC mismatch — ignoring (possible MITM or stale file)"
                        )
                    else:
                        urls = [data.get("primary")] + data.get("backups", [])
                        result = [u for u in urls if u]
                        if result:
                            return result
                else:
                    # Old format without HMAC — skip, will be regenerated on next heartbeat
                    logger.debug("hb_servers.json has no HMAC — will be refreshed on next heartbeat")
    except Exception:
        pass

    try:
        from .server_config import get_server_urls
        primary, backup = get_server_urls()
        return [u for u in [primary, backup] if u]
    except Exception:
        pass

    urls = []
    for key in ("LICENSE_SERVER_URL", "LICENSE_SERVER_URL_BACKUP"):
        v = os.getenv(key, "").strip()
        if v:
            urls.append(v)
    return urls


def _hmac_server_list(data: dict) -> str:
    """HMAC-SHA256 over sorted server list fields (excluding the 'hmac' key itself)."""
    machine_id  = _get_hardware_id()
    instance_id = get_instance_id()
    key = hashlib.sha256((machine_id + ":" + instance_id).encode()).digest()
    payload = {k: v for k, v in data.items() if k != "hmac"}
    msg = json.dumps({k: payload[k] for k in sorted(payload)}, separators=(",", ":")).encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def _save_server_list(primary: str, backups: list) -> None:
    try:
        data = {
            "primary":  primary,
            "backups":  backups,
            "saved_at": int(time.time()),
        }
        data["hmac"] = _hmac_server_list(data)
        _DYN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DYN_PATH.write_text(json.dumps(data))
    except Exception as e:
        logger.debug("Could not save server list: %s", e)


# ── HTTP send ─────────────────────────────────────────────────────────────────

async def _send_one(client: httpx.AsyncClient, url: str, body: dict, sig: str) -> Optional[dict]:
    try:
        resp = await client.post(
            url.rstrip("/") + "/instance/heartbeat",
            json=body,
            headers={"X-Heartbeat-Sig": sig},
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug("Heartbeat to %s failed: %s", url, e)
    return None


async def send_heartbeat() -> bool:
    """Send one heartbeat to the first reachable server. Return True on success."""
    instance_id = get_instance_id()
    machine_id  = _get_hardware_id()
    license_status, activation_code, license_id = _get_license_status()

    hostname = ""
    try:
        hostname = socket.gethostname()[:255]
    except Exception:
        pass

    body = {
        "instance_id":     instance_id,
        "machine_id":      machine_id,
        "hostname":        hostname,
        "app_version":     APP_VERSION,
        "license_status":  license_status,
        "activation_code": activation_code,
        "license_id":      license_id,
        "uptime_seconds":  int(time.time() - _start_time),
        "timestamp":       int(time.time()),
    }
    sig = _sign_heartbeat(body, machine_id, instance_id)

    servers = _get_server_urls()
    if not servers:
        logger.debug("No heartbeat servers configured — skipping")
        return False

    async with httpx.AsyncClient(verify=certifi.where()) as client:
        for url in servers:
            result = await _send_one(client, url, body, sig)
            if result and result.get("status") == "ok":
                primary = result.get("primary_license_server", "")
                backups = result.get("backup_license_servers", [])
                if primary:
                    _save_server_list(primary, backups)
                return True

    logger.debug("Heartbeat failed: all %d server(s) unreachable", len(servers))
    return False


# ── Background loop ───────────────────────────────────────────────────────────

async def _heartbeat_loop():
    # Small delay so the API is fully started before first heartbeat
    await asyncio.sleep(20)
    while True:
        try:
            await send_heartbeat()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug("Heartbeat error: %s", e)
        try:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
        except asyncio.CancelledError:
            break


def start_heartbeat_task() -> asyncio.Task:
    """Create and return the background heartbeat asyncio task."""
    global _heartbeat_task
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())
    logger.info("Instance heartbeat started (interval: %ds)", _HEARTBEAT_INTERVAL)
    return _heartbeat_task
