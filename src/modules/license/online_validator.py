"""
Online License Validator — periodic background check against the central server.

Runs as an asyncio task started from FastAPI lifespan.
Stores the last valid server response in a local cache file so the product
can survive temporary server downtime (up to GRACE_PERIOD_HOURS).
"""

import asyncio
import base64
import dataclasses
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
import certifi
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

_CHECK_INTERVAL  = int(os.getenv("LICENSE_CHECK_INTERVAL",    "14400"))  # 4h default
_RETRY_INTERVAL  = int(os.getenv("LICENSE_CHECK_RETRY",       "900"))    # 15 min on fail
_GRACE_PERIOD_H  = int(os.getenv("LICENSE_GRACE_PERIOD_HOURS", "72"))   # 3 days
_REQUEST_TIMEOUT = 15   # seconds


def _load_server_urls():
    """Load license server URLs from signed config (or env in dev mode)."""
    try:
        from .server_config import get_server_urls
        return get_server_urls()
    except Exception as exc:
        logger.error("Failed to load server URLs from config: %s", exc)
        return "", ""


_SERVER_URL, _SERVER_URL_BACKUP = _load_server_urls()


def reload_server_urls():
    """Reload server URLs — call after applying a migration code."""
    global _SERVER_URL, _SERVER_URL_BACKUP
    _SERVER_URL, _SERVER_URL_BACKUP = _load_server_urls()
    logger.info("License server URLs reloaded: primary=%s backup=%s",
                _SERVER_URL or "—", _SERVER_URL_BACKUP or "—")

# Path to the server response signing public key (committed to repo)
_PUB_KEY_PATH = Path(__file__).parent.parent.parent.parent / "server_verify_public.pem"

# Cache file for last valid server response
_CACHE_PATH = Path(os.getenv("LICENSE_CACHE_PATH",
    str(Path(__file__).parent.parent.parent.parent / "data" / "license_cache.json")
))

# ── License state dataclass ───────────────────────────────────────────────────

@dataclass
class LicenseState:
    """Single source of truth for online license state. Thread-safe via _state_lock."""
    status: Optional[str]          = None   # "ok" / "revoked" / "suspended" / "expired" / ...
    message: Optional[str]         = None
    tier: str                      = ""
    max_clients: int               = 0
    max_servers: int               = 0
    features: list                 = field(default_factory=list)
    expires_at: Optional[str]      = None
    valid_until: Optional[datetime] = None   # cache expiry (server-signed)
    last_check: Optional[datetime] = None
    server_reachable: bool         = True


_state      = LicenseState()
_state_lock = threading.Lock()
_cache_warmed = False


def get_license_state() -> LicenseState:
    """Return a snapshot copy of the current license state (thread-safe)."""
    with _state_lock:
        return dataclasses.replace(_state)


# Legacy aliases — keep module-level names pointing into _state for backward compat
def _get_online_status()    -> Optional[str]: return _state.status
def _get_online_tier()      -> str:           return _state.tier
def _get_server_reachable() -> bool:          return _state.server_reachable

def _get_persistent_instance_id() -> str:
    """Use the persistent INSTANCE_ID from .env (same as instance_manager)."""
    env_id = os.getenv("INSTANCE_ID", "").strip()
    if env_id and len(env_id) >= 8:
        return env_id[:32]
    return str(uuid.uuid4())[:32]

_instance_id = _get_persistent_instance_id()

# ── Security tracking variables ────────────────────────────────────────────────

# First startup time — persisted to disk so restarts cannot reset the grace period clock.
# Without this, "restart process every 72h" would allow indefinite grace period bypass.
_FIRST_STARTUP_FILE = Path(__file__).parent.parent.parent.parent / "data" / "first_startup_at.txt"


def _get_first_startup_time() -> datetime:
    """Return the first-ever startup time, persisting it to disk on first call."""
    try:
        if _FIRST_STARTUP_FILE.exists():
            ts = float(_FIRST_STARTUP_FILE.read_text().strip())
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        pass
    now = datetime.now(timezone.utc)
    try:
        _FIRST_STARTUP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _FIRST_STARTUP_FILE.write_text(str(now.timestamp()))
    except Exception:
        pass
    return now


_startup_time: datetime = _get_first_startup_time()

# Unix wall-clock time of last successful _apply_payload call.
# Used for clock rollback detection: if time.time() < this value,
# the system clock was set backwards.
_last_apply_wall_time: float = 0.0


def get_online_status() -> dict:
    """Return current online validation state (thread-safe read)."""
    _ensure_state_loaded()
    s = get_license_state()
    return {
        "status":        s.status,
        "message":       s.message,
        "tier":          s.tier,
        "max_clients":   s.max_clients,
        "max_servers":   s.max_servers,
        "features":      s.features,
        "expires_at":    s.expires_at,
        "valid_until":   s.valid_until.isoformat() if s.valid_until else None,
        "last_check":    s.last_check.isoformat()  if s.last_check  else None,
        "server_reachable":          s.server_reachable,
        "license_server_url":        _SERVER_URL or None,
        "license_server_url_backup": _SERVER_URL_BACKUP or None,
    }


def is_license_blocked() -> tuple[bool, str]:
    """
    Return (blocked, reason).

    Blocked = True if:
      - Server returned revoked/suspended — always block regardless of cache
      - ok status but cache expired more than GRACE_PERIOD_H ago (server unreachable)
      - Status indicates invalid/expired license AND valid cache window elapsed
      - System clock rolled back (tamper detection)
      - No cache AND startup grace period elapsed
    Blocked = False if:
      - No LICENSE_SERVER_URL (offline mode)
      - Server returned ok AND within valid_until window
      - Server unreachable but still within cache grace window
      - First startup and within GRACE_PERIOD_H from import time
    """
    _ensure_state_loaded()
    s = get_license_state()   # atomic snapshot — no globals needed

    if not os.getenv("LICENSE_KEY", "").strip():
        return False, ""

    if not _SERVER_URL and not _SERVER_URL_BACKUP:
        return False, ""   # No server configured — middleware handles activation check

    # ── 0. Clock rollback detection ─────────────────────────────────────────
    # If wall clock moved backwards by > 5 min since last successful check,
    # attackers may be trying to extend valid_until window via clock manipulation.
    if _last_apply_wall_time > 0 and time.time() < _last_apply_wall_time - 300:
        delta = int(_last_apply_wall_time - time.time())
        logger.error(
            "SECURITY: System clock rollback detected (%ds) — blocking license",
            delta
        )
        _send_tamper_report_sync("clock_rollback", {
            "delta_seconds": delta,
            "last_check_wall": _last_apply_wall_time,
            "current_wall":    time.time(),
        })
        return True, f"System clock rollback detected ({delta}s) — re-verification required"

    # ── 1. Hard blocks — no grace period possible ────────────────────────────
    if s.status in ("revoked", "suspended"):
        return True, s.message or f"License {s.status}"

    # ── 2. Normalise valid_until — handle naive datetimes and corrupt types ──
    now = datetime.now(timezone.utc)
    _vuntil: Optional[datetime] = None
    if isinstance(s.valid_until, datetime):
        _vuntil = s.valid_until
        if _vuntil.tzinfo is None:
            _vuntil = _vuntil.replace(tzinfo=timezone.utc)
    # Non-datetime types (str, int, None) are treated as "no expiry info"

    # ── 3. Within server-signed cache window (valid_until not yet expired) ───
    if _vuntil and now <= _vuntil:
        # Any status — still inside the signed validity window
        return False, ""

    # ── 4. Cache window expired (past valid_until) ───────────────────────────
    if s.status == "ok":
        if not _vuntil:
            # No expiry set in server response — cannot enforce expiry
            return False, ""
        # ok cache expired — allow secondary grace to survive short server outages.
        # This prevents "block server permanently" from immediately locking users out.
        secondary_end = _vuntil + timedelta(hours=_GRACE_PERIOD_H)
        if now <= secondary_end:
            return False, ""
        elapsed_h = int((now - _vuntil).total_seconds() / 3600)
        return True, (
            f"License cache expired {elapsed_h}h ago — "
            f"server unreachable, please restore connectivity to license server"
        )

    if s.status in ("expired", "not_found", "invalid_key"):
        return True, s.message or f"License {s.status}"

    # ── 5. Never successfully checked (status is None) ──────────────────────
    # When last_check is None it means no valid cache was loaded at startup
    # (cache missing or signature invalid). Use BOTH cache mtime AND startup_time:
    # an attacker can "touch" a fake cache file to refresh its mtime, but cannot
    # alter _startup_time which is set at Python import time.
    if s.last_check is None:
        startup_h = (now - _startup_time).total_seconds() / 3600
        if _CACHE_PATH.exists():
            age_h = (time.time() - _CACHE_PATH.stat().st_mtime) / 3600
            # Block if the cache file itself is stale
            if age_h > _GRACE_PERIOD_H:
                return True, (
                    f"License cache is {age_h:.0f}h old "
                    f"(grace period {_GRACE_PERIOD_H}h exceeded) — server unreachable"
                )
            # Cache file is fresh but startup is old — attacker may have touched a fake file
            if startup_h > _GRACE_PERIOD_H:
                return True, (
                    f"License server unreachable since startup "
                    f"({startup_h:.0f}h > {_GRACE_PERIOD_H}h grace period)"
                )
            return False, ""
        # No cache file — use startup time for bounded grace period.
        # Without this bound, "delete cache + block server" = never blocked.
        if startup_h <= _GRACE_PERIOD_H:
            return False, ""
        return True, (
            f"License server unreachable since startup "
            f"({startup_h:.0f}h > {_GRACE_PERIOD_H}h grace period)"
        )

    # ── 5. Was checked before but server now unreachable past valid_until ────
    return True, "License server unreachable and grace period elapsed"


# ── Signature verification ────────────────────────────────────────────────────

def _load_server_pub_key():
    path = Path(os.getenv("SERVER_VERIFY_PUBLIC_KEY_PATH", str(_PUB_KEY_PATH)))
    if not path.exists():
        return None
    try:
        return serialization.load_pem_public_key(path.read_bytes())
    except Exception as exc:
        logger.error("Failed to load server_verify_public.pem: %s", exc)
        return None


def _verify_response(payload_b64: str, sig_b64: str) -> Optional[dict]:
    """
    Verify RSA-PSS signature and return decoded payload dict, or None on failure.

    Security: if the public key file is missing or unreadable, the response is
    REJECTED (returns None) — NOT accepted silently. Accepting unverified responses
    would allow MITM attacks by anyone who can delete the key file and run a fake server.
    """
    pub_key = _load_server_pub_key()
    if pub_key is None:
        # Hard fail — cannot verify without the public key.
        # Silently accepting would allow MITM via key deletion + fake server.
        key_path = os.getenv("SERVER_VERIFY_PUBLIC_KEY_PATH", str(_PUB_KEY_PATH))
        logger.error(
            "TAMPER ALERT: server_verify_public.pem not found at %s — "
            "rejecting server response to prevent MITM attack",
            key_path
        )
        _send_tamper_report_sync("public_key_missing", {"path": key_path})
        return None

    try:
        # Re-pad base64url
        pad = (4 - len(payload_b64) % 4) % 4
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * pad)
        pad2 = (4 - len(sig_b64) % 4) % 4
        sig_bytes = base64.urlsafe_b64decode(sig_b64 + "=" * pad2)

        pub_key.verify(
            sig_bytes,
            payload_b64.encode("ascii"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
    except Exception as exc:
        logger.error("License server response signature INVALID: %s", exc)
        _send_tamper_report_sync("invalid_server_signature", {"error": str(exc)})
        return None

    pad = (4 - len(payload_b64) % 4) % 4
    payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * pad)
    return json.loads(payload_bytes)


# ── Cache ─────────────────────────────────────────────────────────────────────

def _save_cache(payload: dict, payload_b64: str, sig_b64: str):
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps({
            "payload":   payload_b64,
            "signature": sig_b64,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }))
    except Exception as exc:
        logger.warning("Could not save license cache: %s", exc)


def _load_cache() -> Optional[dict]:
    try:
        if not _CACHE_PATH.exists():
            return None
        data = json.loads(_CACHE_PATH.read_text())
        return _verify_response(data["payload"], data["signature"])
    except Exception as exc:
        logger.warning("Could not load license cache: %s", exc)
        return None


def _apply_payload(payload: dict):
    global _last_apply_wall_time

    valid_until: Optional[datetime] = None
    valid_until_str = payload.get("valid_until")
    if valid_until_str:
        try:
            valid_until = datetime.fromisoformat(valid_until_str)
        except Exception:
            pass

    new_state = LicenseState(
        status       = payload.get("status", "invalid_key"),
        message      = payload.get("message", ""),
        tier         = payload.get("tier", ""),
        max_clients  = payload.get("max_clients", 0),
        max_servers  = payload.get("max_servers", 0),
        features     = payload.get("features", []),
        expires_at   = payload.get("expires_at"),
        valid_until  = valid_until,
        last_check   = datetime.now(timezone.utc),
        server_reachable = True,
    )
    with _state_lock:
        # Atomic replacement — all fields updated together
        for f in dataclasses.fields(new_state):
            setattr(_state, f.name, getattr(new_state, f.name))
    _last_apply_wall_time = time.time()   # for clock rollback detection


# ── Hardware ID ───────────────────────────────────────────────────────────────

def get_hardware_id() -> str:
    """Public function — returns machine hardware ID used for license binding."""
    return _get_hardware_id()


def _get_hardware_id() -> str:
    """
    Must produce the same value as LicenseManager.get_server_id() in manager.py,
    because license keys are bound to that ID and the server validates it too.
    Algorithm: sha256(platform.node()|platform.machine()|str(uuid.getnode())[|machine-id])[:32]
    """
    import platform as _platform
    components = [
        _platform.node(),
        _platform.machine(),
        str(uuid.getnode()),
    ]
    try:
        mid_path = Path("/etc/machine-id")
        if mid_path.exists():
            components.append(mid_path.read_text().strip())
    except Exception:
        pass
    return hashlib.sha256("|".join(components).encode()).hexdigest()[:32]


# ── Tamper reporting (synchronous fallback for startup) ───────────────────────

def _send_tamper_report_sync(report_type: str, details: dict):
    urls = [u for u in (_SERVER_URL, _SERVER_URL_BACKUP) if u]
    if not urls:
        return
    license_key = os.getenv("LICENSE_KEY", "").strip()
    body = {
        "license_key": license_key,
        "hardware_id": _get_hardware_id(),
        "instance_id": _instance_id,
        "report_type": report_type,
        "details":     details,
    }
    for url in urls:
        try:
            with httpx.Client(timeout=5, verify=certifi.where()) as client:
                client.post(f"{url}/api/report", json=body)
            return  # sent successfully
        except Exception as exc:
            logger.debug("Tamper report send failed (%s): %s", url, exc)


# ── Main check loop ───────────────────────────────────────────────────────────

async def _try_server(url: str, payload: dict) -> Optional[bool]:
    """
    Try one license server URL.
    Returns True on success, False on bad response, None on network error.
    """
    if url.startswith("http://"):
        logger.warning(
            "SECURITY WARNING: license server URL uses plain HTTP (%s). "
            "License key is transmitted in cleartext. Use HTTPS in production.", url
        )
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, verify=certifi.where()) as client:
            resp = await client.post(f"{url}/api/validate", json=payload)

        if resp.status_code == 200:
            data = resp.json()
            verified = _verify_response(data.get("payload", ""), data.get("signature", ""))
            if verified:
                _apply_payload(verified)
                _save_cache(verified, data["payload"], data["signature"])
                logger.info("Online license check via %s: status=%s tier=%s",
                            url, verified.get("status"), verified.get("tier"))
                return True
            else:
                logger.error("License server %s returned INVALID signature — possible MITM", url)
                asyncio.create_task(_send_tamper_report("invalid_server_signature", {"url": url}))
                return False  # server responded but suspicious
        else:
            logger.warning("License server %s returned HTTP %d", url, resp.status_code)
            return False

    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.warning("License server %s unreachable: %s", url, exc)
        return None  # network error → try backup
    except Exception as exc:
        logger.error("Unexpected error contacting %s: %s", url, exc)
        return None


async def _do_check():
    license_key = os.getenv("LICENSE_KEY", "").strip()
    if not license_key:
        logger.debug("LICENSE_KEY not set — skipping online check")
        return

    hw_id = _get_hardware_id()
    payload = {
        "license_key":    license_key,
        "hardware_id":    hw_id,
        "instance_id":    _instance_id,
        "timestamp":      int(time.time()),
        "client_version": os.getenv("APP_VERSION", ""),
    }

    # Try primary server first
    if _SERVER_URL:
        result = await _try_server(_SERVER_URL, payload)
        if result is not None:          # got a definitive answer (True=ok, False=bad sig)
            with _state_lock:
                _state.server_reachable = True
            return
        # Network error on primary → fall through to backup

    # Try backup server
    if _SERVER_URL_BACKUP:
        logger.info("Primary license server unreachable, trying backup: %s", _SERVER_URL_BACKUP)
        result = await _try_server(_SERVER_URL_BACKUP, payload)
        if result is not None:
            with _state_lock:
                _state.server_reachable = True
            return

    # Both servers unreachable
    with _state_lock:
        _state.server_reachable = False
    logger.warning("All license servers unreachable (primary=%s, backup=%s)",
                   _SERVER_URL or "—", _SERVER_URL_BACKUP or "—")


async def _send_tamper_report(report_type: str, details: dict):
    urls = [u for u in (_SERVER_URL, _SERVER_URL_BACKUP) if u]
    if not urls:
        return
    license_key = os.getenv("LICENSE_KEY", "").strip()
    body = {
        "license_key": license_key,
        "hardware_id": _get_hardware_id(),
        "instance_id": _instance_id,
        "report_type": report_type,
        "details":     details,
    }
    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=5, verify=certifi.where()) as client:
                await client.post(f"{url}/api/report", json=body)
            return  # sent successfully
        except Exception as exc:
            logger.debug("Tamper report send failed (%s): %s", url, exc)


def _warmup_from_cache() -> bool:
    """Load cached signed license state into memory if available."""
    global _cache_warmed
    cached = _load_cache()
    if cached:
        _apply_payload(cached)
        _cache_warmed = True
        logger.info("Loaded cached license status: %s", cached.get("status"))
        return True
    _cache_warmed = True
    return False


def _ensure_state_loaded() -> None:
    global _cache_warmed
    if _cache_warmed:
        return
    with _state_lock:
        already_loaded = _cache_warmed or _state.status is not None or _state.last_check is not None
    if already_loaded:
        _cache_warmed = True
        return
    _warmup_from_cache()


async def run_single_check(*, warm_cache: bool = True) -> bool:
    """
    Run one validation attempt during startup.
    Returns False only when no license server is configured.
    """
    if not _SERVER_URL and not _SERVER_URL_BACKUP:
        logger.info("LICENSE_SERVER_URL not set — online validation disabled")
        return False
    if warm_cache:
        _warmup_from_cache()
    await _do_check()
    return True


async def run_validator_loop():
    """
    Long-running background asyncio task.
    - Loads cache on startup
    - Checks server immediately, then every _CHECK_INTERVAL seconds
    - On failure retries every _RETRY_INTERVAL seconds
    """
    if not _SERVER_URL and not _SERVER_URL_BACKUP:
        logger.info("LICENSE_SERVER_URL not set — online validation disabled")
        return

    _warmup_from_cache()

    await asyncio.sleep(2)   # brief startup delay

    while True:
        await _do_check()

        if _state.server_reachable and _state.status == "ok":
            await asyncio.sleep(_CHECK_INTERVAL)
        else:
            await asyncio.sleep(_RETRY_INTERVAL)
