"""
Online License Validator — periodic background check against the central server.

Runs as an asyncio task started from FastAPI lifespan.
Stores the last valid server response in a local cache file so the product
can survive temporary server downtime. Subscriptions use the configured grace
window; Lifetime licences use a vendor-signed 30-day offline lease.
"""

import asyncio
import base64
import dataclasses
import hashlib
import json
from loguru import logger
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

from src.utils.runtime_paths import get_app_version


# ── Configuration ─────────────────────────────────────────────────────────────

_CHECK_INTERVAL  = int(os.getenv("LICENSE_CHECK_INTERVAL",    "14400"))  # 4h default
_RETRY_INTERVAL  = int(os.getenv("LICENSE_CHECK_RETRY",       "900"))    # 15 min on fail
_GRACE_PERIOD_H  = int(os.getenv("LICENSE_GRACE_PERIOD_HOURS", "72"))   # 3 days
_LIFETIME_OFFLINE_DAYS = 30
_REQUEST_TIMEOUT = 15   # seconds


def _local_license_type() -> str:
    """Read `license_type` from the locally-stored LICENSE_KEY without
    verifying its signature.

    Used only for choosing enforcement mode (block vs allow) — signature
    verification still happens elsewhere (LicenseManager) before the
    license is trusted to grant features. Reading the type unverified is
    safe here because every code path returns "subscription" (the strict
    default) on parse failure or when the field is missing.
    """
    raw = os.getenv("LICENSE_KEY", "").strip()
    if not raw or "." not in raw:
        return "subscription"
    try:
        payload_b64 = raw.split(".", 1)[0]
        # Restore base64url padding
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode())
        t = payload.get("license_type", "subscription")
        if t in ("subscription", "lifetime", "lifetime_protected"):
            return t
    except Exception:
        pass
    return "subscription"


def _load_server_urls():
    """Load license server URLs from signed config (or env in dev mode)."""
    try:
        from .server_config import get_server_urls
        return get_server_urls()
    except Exception as exc:
        logger.error("Failed to load server URLs from config: {}", exc)
        return "", ""


_SERVER_URL, _SERVER_URL_BACKUP = _load_server_urls()


def reload_server_urls():
    """Reload server URLs — call after applying a migration code."""
    global _SERVER_URL, _SERVER_URL_BACKUP
    _SERVER_URL, _SERVER_URL_BACKUP = _load_server_urls()
    logger.info("License server URLs reloaded: primary={} backup={}",
                _SERVER_URL or "—", _SERVER_URL_BACKUP or "—")

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
    billing_type: str              = ""
    license_type: str              = ""
    server_time: Optional[datetime] = None
    valid_until: Optional[datetime] = None   # cache expiry (server-signed)
    lease_kind: str                = ""
    license_uid: Optional[str]     = None
    hardware_id: Optional[str]     = None
    instance_id: Optional[str]     = None
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
    """Use the one persistent INSTANCE_ID shared with instance heartbeats.

    The validator used to create an in-memory UUID when ``INSTANCE_ID`` was
    absent.  The heartbeat manager could then persist a different UUID later
    in the same startup, leaving the freshly signed offline lease unreadable
    after a restart.  Delegate creation and persistence to the canonical
    instance manager, while retaining the validator protocol's 32-character
    identifier.
    """
    from .instance_manager import get_instance_id

    return get_instance_id()[:32]

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
        "billing_type":  s.billing_type,
        "license_type":  s.license_type,
        "server_time":   s.server_time.isoformat() if s.server_time else None,
        "valid_until":   s.valid_until.isoformat() if s.valid_until else None,
        "lease_kind":    s.lease_kind or None,
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

    lic_type = _local_license_type()

    # ── 0. Clock rollback detection ─────────────────────────────────────────
    # If wall clock moved backwards by > 5 min since last successful check,
    # attackers may be trying to extend valid_until window via clock manipulation.
    signed_server_ts = s.server_time.timestamp() if s.server_time else 0.0
    rollback_reference = max(_last_apply_wall_time, signed_server_ts)
    if rollback_reference > 0 and time.time() < rollback_reference - 300:
        delta = int(rollback_reference - time.time())
        logger.error(
            "SECURITY: System clock rollback detected ({}s) — blocking license",
            delta
        )
        _send_tamper_report_sync("clock_rollback", {
            "delta_seconds": delta,
            "last_check_wall": rollback_reference,
            "current_wall":    time.time(),
        })
        return True, f"System clock rollback detected ({delta}s) — re-verification required"

    # ── 1. Hard blocks — no grace period possible ────────────────────────────
    if s.status in ("revoked", "suspended", "expired", "not_found", "invalid_key", "invalid_timestamp"):
        return True, s.message or f"License {s.status}"

    # ── 2. Normalise valid_until — handle naive datetimes and corrupt types ──
    now = datetime.now(timezone.utc)
    _vuntil: Optional[datetime] = None
    if isinstance(s.valid_until, datetime):
        _vuntil = s.valid_until
        if _vuntil.tzinfo is None:
            _vuntil = _vuntil.replace(tzinfo=timezone.utc)
    # Non-datetime types (str, int, None) are treated as "no expiry info"

    # ── 3. Lifetime signed offline lease ────────────────────────────────────
    if lic_type in ("lifetime", "lifetime_protected"):
        if s.status in ("ok", "valid_with_warning") and s.server_time:
            # New responses explicitly sign a 30-day valid_until.  A legacy
            # response signed before this protocol used a four-day cache; use
            # its signed server_time as the anchor during the rolling upgrade.
            offline_end = (
                _vuntil
                if s.lease_kind in ("online", "emergency") and _vuntil
                else s.server_time + timedelta(days=_LIFETIME_OFFLINE_DAYS)
            )
            if now <= offline_end:
                return False, ""
            return True, "Lifetime offline allowance expired; online re-verification is required"

        # A missing cache must not grant a fresh window. The background check
        # starts immediately; until it succeeds the paid surface stays
        # readonly instead of creating a restart/reinstall bypass.
        return True, "No valid signed Lifetime offline lease is available"

    # ── 4. Subscription cache window ────────────────────────────────────────
    if s.status in ("ok", "valid_with_warning") and _vuntil and now <= _vuntil:
        return False, ""

    # ── 4. Cache window expired (past valid_until) ───────────────────────────
    if s.status in ("ok", "valid_with_warning"):
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

# Phase C trust anchor — mirror of server_config.py. Only the post-rotation
# server key is accepted; the retired leaked key and editable file fallback are
# intentionally excluded.
_SV_PUB_CURRENT = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA4XHN7ytdeE+padSbGncw
kvL81PYqtG50ohbFd2a6OZJ1GKINXO4WiCuzvKnma00uMRWb0iXvl1bOJNPKSeAG
RVZc8FSiMQHTf9sD3AyuXJBmGokOlZV3Iib0mvVF/WX/R2tYPbjr3CF2hSC2izoE
xtn36wrytfOIR42Hv0/wKGcm/MJ6/gVS1UcKDsQqju3mTMm7JEV7DxzSVGTlnswx
N3lGKb387U6g8MmcRHmIh0DxjfmJku9RvqnFBDhdIX+GY+NoBu37alvS8aNm3vrt
Jg8mJwXUXinZL3fjVmsT2ikvfLAPmUIXPIFjGqr2jSfeYJv7ozXOEqrlXSQUoTTO
3wIDAQAB
-----END PUBLIC KEY-----
"""


def _load_server_pub_keys():
    """Load the single pinned post-rotation server-response trust anchor."""
    keys = []
    try:
        keys.append(serialization.load_pem_public_key(_SV_PUB_CURRENT))
    except Exception as exc:
        logger.error("Pinned server-verify key failed to load: {}", exc)
    return keys


def _verify_response(payload_b64: str, sig_b64: str) -> Optional[dict]:
    """
    Verify RSA-PSS signature and return decoded payload dict, or None on failure.

    Security: if no accepted public key is available, the response is REJECTED
    (returns None) — NOT accepted silently. Accepting unverified responses would
    allow MITM attacks by anyone who can run a fake server.
    """
    pub_keys = _load_server_pub_keys()
    if not pub_keys:
        # Hard fail — cannot verify without a public key.
        logger.error(
            "TAMPER ALERT: pinned server-verify public key unavailable — "
            "rejecting server response to prevent MITM attack"
        )
        _send_tamper_report_sync("public_key_missing", {"source": "embedded"})
        return None

    try:
        # Re-pad base64url
        pad = (4 - len(payload_b64) % 4) % 4
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * pad)
        pad2 = (4 - len(sig_b64) % 4) % 4
        sig_bytes = base64.urlsafe_b64decode(sig_b64 + "=" * pad2)

        verified = False
        for pub_key in pub_keys:
            try:
                pub_key.verify(
                    sig_bytes,
                    payload_b64.encode("ascii"),
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH,
                    ),
                    hashes.SHA256(),
                )
                verified = True
                break
            except Exception:
                continue
        if not verified:
            logger.error("License server response signature INVALID (no accepted key verified)")
            _send_tamper_report_sync("invalid_server_signature", {"error": "no accepted key verified"})
            return None
    except Exception as exc:
        logger.error("License server response signature check error: {}", exc)
        _send_tamper_report_sync("invalid_server_signature", {"error": str(exc)})
        return None

    pad = (4 - len(payload_b64) % 4) % 4
    payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * pad)
    return json.loads(payload_bytes)


# ── Cache ─────────────────────────────────────────────────────────────────────

def _save_cache(payload: dict, payload_b64: str, sig_b64: str):
    """Atomically persist a verified server envelope.

    A power loss must leave either the previous complete lease or the new
    complete lease, never a truncated JSON file that turns a legitimate
    customer into FREE/readonly on restart.
    """
    temp_path: Optional[Path] = None
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = _CACHE_PATH.with_name(f".{_CACHE_PATH.name}.{uuid.uuid4().hex}.tmp")
        data = json.dumps({
            "payload":   payload_b64,
            "signature": sig_b64,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        })
        with temp_path.open("x", encoding="utf-8") as handle:
            os.chmod(temp_path, 0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, _CACHE_PATH)
        dir_fd = os.open(_CACHE_PATH.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception as exc:
        logger.warning("Could not save license cache: {}", exc)
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


def reset_validation_state_for_license_change() -> None:
    """Invalidate the previous key's in-memory and on-disk lease state."""
    global _state, _cache_warmed, _last_apply_wall_time
    with _state_lock:
        _state = LicenseState()
        # Do not warm from the deliberately removed old-key cache. The
        # immediate validation task below is the only way to obtain a lease.
        _cache_warmed = True
        _last_apply_wall_time = 0.0
    try:
        _CACHE_PATH.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Could not remove previous-key license cache: {}", exc)


def _read_local_license_payload() -> dict:
    raw = os.getenv("LICENSE_KEY", "").strip()
    if not raw or "." not in raw:
        return {}
    try:
        payload_b64 = raw.split(".", 1)[0]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64).decode())
    except Exception:
        return {}


def _validate_lease_binding(payload: dict, *, expected_instance_id: str | None = None) -> tuple[bool, str]:
    """Validate additive v1 lease binding after the vendor signature check.

    Responses from the previous server version have no `lease_version` and
    remain accepted during rollout.  Once present, every binding field is
    mandatory and a cache copied to another machine/instance is rejected.
    """
    if payload.get("lease_version") is None:
        return True, "legacy signed response"
    if payload.get("lease_version") != 1:
        return False, "unsupported lease version"

    local_payload = _read_local_license_payload()
    expected_hw = _get_hardware_id()
    if payload.get("hardware_id") != expected_hw:
        return False, "lease hardware binding mismatch"

    lease_kind = payload.get("lease_kind")
    if lease_kind not in ("online", "emergency"):
        return False, "invalid lease kind"
    expected_inst = expected_instance_id or _instance_id
    if payload.get("instance_id") != expected_inst:
        return False, "lease instance binding mismatch"

    local_uid = local_payload.get("lid")
    lease_uid = payload.get("license_uid")
    if local_uid and lease_uid != local_uid:
        return False, "lease license id mismatch"

    try:
        server_time = datetime.fromisoformat(payload["server_time"])
        valid_until = datetime.fromisoformat(payload["valid_until"])
        if server_time.tzinfo is None:
            server_time = server_time.replace(tzinfo=timezone.utc)
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
    except Exception:
        return False, "invalid lease timestamps"
    if valid_until <= server_time:
        return False, "lease validity window is empty"
    if (payload.get("billing_type") == "lifetime" or _local_license_type() in ("lifetime", "lifetime_protected")):
        if valid_until - server_time > timedelta(days=_LIFETIME_OFFLINE_DAYS, minutes=5):
            return False, "Lifetime lease exceeds maximum offline allowance"
    return True, ""


def _load_cache() -> Optional[dict]:
    try:
        if not _CACHE_PATH.exists():
            return None
        data = json.loads(_CACHE_PATH.read_text())
        payload = _verify_response(data["payload"], data["signature"])
        if payload is None:
            return None
        valid, reason = _validate_lease_binding(payload)
        if not valid:
            logger.error("Rejected signed license cache: {}", reason)
            _send_tamper_report_sync("lease_binding_invalid", {"reason": reason})
            return None
        return payload
    except Exception as exc:
        logger.warning("Could not load license cache: {}", exc)
        return None


def _apply_payload(payload: dict):
    global _last_apply_wall_time

    valid_until: Optional[datetime] = None
    server_time: Optional[datetime] = None
    valid_until_str = payload.get("valid_until")
    if valid_until_str:
        try:
            valid_until = datetime.fromisoformat(valid_until_str)
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    server_time_str = payload.get("server_time")
    if server_time_str:
        try:
            server_time = datetime.fromisoformat(server_time_str)
            if server_time.tzinfo is None:
                server_time = server_time.replace(tzinfo=timezone.utc)
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
        billing_type = payload.get("billing_type", ""),
        license_type = payload.get("license_type", ""),
        server_time  = server_time,
        valid_until  = valid_until,
        lease_kind   = payload.get("lease_kind", ""),
        license_uid  = payload.get("license_uid"),
        hardware_id  = payload.get("hardware_id"),
        instance_id  = payload.get("instance_id"),
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
            logger.debug("Tamper report send failed ({}): {}", url, exc)


# ── Main check loop ───────────────────────────────────────────────────────────

async def _try_server(
    url: str,
    payload: dict,
    *,
    accept_negative_status: bool = True,
) -> Optional[bool]:
    """
    Try one license server URL.
    Returns True on success, False on bad response, None on network error.
    """
    if url.startswith("http://"):
        logger.warning(
            "SECURITY WARNING: license server URL uses plain HTTP ({}). "
            "License key is transmitted in cleartext. Use HTTPS in production.", url
        )
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, verify=certifi.where()) as client:
            resp = await client.post(f"{url}/api/validate", json=payload)

        if resp.status_code == 200:
            data = resp.json()
            verified = _verify_response(data.get("payload", ""), data.get("signature", ""))
            if verified:
                if payload.get("license_key") != os.getenv("LICENSE_KEY", "").strip():
                    logger.warning("Discarding validation response for a superseded local key")
                    return None
                binding_ok, binding_reason = _validate_lease_binding(
                    verified, expected_instance_id=payload.get("instance_id")
                )
                if not binding_ok:
                    logger.error("License server {} returned a mis-bound lease: {}", url, binding_reason)
                    asyncio.create_task(_send_tamper_report(
                        "lease_binding_invalid", {"url": url, "reason": binding_reason}
                    ))
                    return False
                if (
                    not accept_negative_status
                    and verified.get("status") in {
                        "revoked", "suspended", "expired", "not_found",
                        "invalid_key", "invalid_timestamp",
                    }
                ):
                    # A fallback origin may be healthy while its licence DB is
                    # stale or still restoring. It may extend availability
                    # with a signed positive record, but it must not overwrite
                    # a good primary lease with a false negative. The primary
                    # remains the revocation authority; the existing bounded
                    # lease governs until it is reachable again.
                    logger.warning(
                        "Ignoring non-authoritative fallback status={} from {}",
                        verified.get("status"), url,
                    )
                    return None
                _apply_payload(verified)
                _save_cache(verified, data["payload"], data["signature"])
                logger.info("Online license check via {}: status={} tier={}",
                            url, verified.get("status"), verified.get("tier"))
                # In-band rotation: if the server's signed response told us
                # the current key is revoked/suspended AND offered a
                # successor JWT (verified active for the same hardware+
                # owner), swap it in and restart so we re-load with the new
                # key. Run AFTER cache save so a botched rotation can be
                # retried on the next tick without losing the latest
                # legitimate server response.
                _maybe_rotate_license(verified)
                return True
            else:
                logger.error("License server {} returned INVALID signature — possible MITM", url)
                asyncio.create_task(_send_tamper_report("invalid_server_signature", {"url": url}))
                return False  # server responded but suspicious
        else:
            logger.warning("License server {} returned HTTP {}", url, resp.status_code)
            return False

    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.warning("License server {} unreachable: {}", url, exc)
        return None  # network error → try backup
    except Exception as exc:
        logger.error("Unexpected error contacting {}: {}", url, exc)
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
        "client_version": get_app_version(),
    }

    # Try primary server first
    if _SERVER_URL:
        result = await _try_server(_SERVER_URL, payload, accept_negative_status=True)
        if result is not None:          # got a definitive answer (True=ok, False=bad sig)
            with _state_lock:
                _state.server_reachable = True
            return
        # Network error on primary → fall through to backup

    # Try backup server
    if _SERVER_URL_BACKUP:
        logger.info("Primary license server unreachable, trying backup: {}", _SERVER_URL_BACKUP)
        result = await _try_server(
            _SERVER_URL_BACKUP, payload, accept_negative_status=False
        )
        if result is not None:
            with _state_lock:
                _state.server_reachable = True
            return

    # Both servers unreachable
    with _state_lock:
        _state.server_reachable = False
    logger.warning("All license servers unreachable (primary={}, backup={})",
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
            logger.debug("Tamper report send failed ({}): {}", url, exc)


def _warmup_from_cache() -> bool:
    """Load cached signed license state into memory if available."""
    global _cache_warmed
    cached = _load_cache()
    if cached:
        _apply_payload(cached)
        _cache_warmed = True
        logger.debug("Loaded cached license status: {}", cached.get("status"))
        return True
    _cache_warmed = True
    return False


def install_offline_lease(envelope: dict) -> tuple[bool, str]:
    """Verify and atomically install a vendor-issued emergency lease.

    The envelope is the same `{payload, signature}` format as `/api/validate`.
    It grants no new entitlement: the signed payload must be an active Lifetime
    lease bound to this machine and to the current signed licence id.
    """
    if not isinstance(envelope, dict):
        return False, "Offline lease must be a JSON object"
    payload_b64 = str(envelope.get("payload") or "")
    signature = str(envelope.get("signature") or "")
    payload = _verify_response(payload_b64, signature)
    if payload is None:
        return False, "Offline lease signature is invalid"
    valid, reason = _validate_lease_binding(payload)
    if not valid:
        return False, reason
    if payload.get("lease_kind") != "emergency":
        return False, "Only an emergency offline lease can be imported"
    if payload.get("status") != "ok" or payload.get("billing_type") != "lifetime":
        return False, "Offline lease is not an active Lifetime entitlement"
    try:
        expires = datetime.fromisoformat(payload["valid_until"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    except Exception:
        return False, "Offline lease expiry is invalid"
    if datetime.now(timezone.utc) >= expires:
        return False, "Offline lease has expired"
    _save_cache(payload, payload_b64, signature)
    _apply_payload(payload)
    return True, f"Emergency offline lease accepted until {expires.isoformat()}"


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

    initial_type = _local_license_type()
    lifetime_interval = int(os.getenv("LICENSE_LIFETIME_CHECK_INTERVAL", "86400"))
    if initial_type in ("lifetime", "lifetime_protected"):
        logger.info("Lifetime signed-lease validator enabled (interval: {}s)", lifetime_interval)

    _warmup_from_cache()

    await asyncio.sleep(2)   # brief startup delay

    while True:
        await _do_check()

        # A key can be activated or rotated without restarting the service, so
        # choose the cadence from the current local key on every iteration.
        lic_type = _local_license_type()
        if _state.server_reachable and _state.status in ("ok", "valid_with_warning"):
            await asyncio.sleep(
                lifetime_interval
                if lic_type in ("lifetime", "lifetime_protected")
                else _CHECK_INTERVAL
            )
        else:
            await asyncio.sleep(_RETRY_INTERVAL)


# ── In-band license rotation ──────────────────────────────────────────────────
#
# When the lic-server tells us the current key is revoked AND points us at a
# newly-issued successor (same hardware_id, same owner_email), the panel can
# verify the offered JWT locally, swap .env, and restart — no operator SSH
# round-trip required. This prevents a re-issued key from leaving an
# installation on stale entitlements.
#
# Safety:
#   1. The offered JWT is signature-verified with license_public.pem before
#      anything else happens. A compromised lic-server cannot forge a key.
#   2. The hardware_id in the new JWT must match the local hardware_id.
#      Even if the server hands us a key for someone else's hwid we refuse
#      it and emit a tamper report.
#   3. owner_email in the new JWT must match the current key's owner_email
#      (when present). Another belt to keep cross-customer accidents off.
#   4. .env is updated atomically (tempfile + os.replace). Mode is preserved.
#   5. systemctl restart is detached so we don't block waiting for our own
#      SIGTERM. systemd's graceful shutdown lets in-flight requests finish.
#
# Disable via env: LICENSE_ROTATION_DISABLED=1 (defensive switch for ops).

_ROTATION_TRIGGERED = False   # process-local guard so we restart once per
                              # successful rotation, not once per /api/validate
                              # tick while the restart is still in flight.
_ROTATION_LOCK = threading.Lock()


def _maybe_rotate_license(payload: dict) -> None:
    """Called from _try_server with the freshly-verified server response.
    Idempotent: a no-op when the server didn't offer a successor, or when
    we've already triggered a restart this process lifetime."""
    if os.getenv("LICENSE_ROTATION_DISABLED", "").lower() in ("1", "true", "yes", "on"):
        return
    new_key = (payload.get("new_license_key") or "").strip()
    if not new_key:
        return
    # Only act when the server explicitly told us the current key is
    # gone. The "ok" path with new_license_key set would be weird (and
    # we'd risk swapping in the middle of a healthy session); be strict.
    if payload.get("status") not in ("revoked", "suspended"):
        return
    if new_key == os.getenv("LICENSE_KEY", "").strip():
        return  # already on this key locally — restart will happen / has happened
    with _ROTATION_LOCK:
        global _ROTATION_TRIGGERED
        if _ROTATION_TRIGGERED:
            return
        ok = _rotate_license_key(new_key)
        if ok:
            _ROTATION_TRIGGERED = True


def _rotate_license_key(new_key: str) -> bool:
    """Verify, persist atomically, and detach a systemctl restart.
    Returns True iff every step succeeded. Never raises."""
    try:
        parts = new_key.split(".")
        if len(parts) != 2:
            logger.error("License rotation: offered key is not in expected payload.signature format")
            return False
        try:
            payload_bytes = base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4))
            new_payload = json.loads(payload_bytes)
            signature_bytes = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        except Exception as e:
            logger.error("License rotation: failed to decode offered key: {}", e)
            return False

        # Local signature verification with the embedded RSA public key.
        from .manager import _find_public_key
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        pub_path = _find_public_key()
        if not pub_path:
            logger.warning("License rotation: license_public.pem not present, skipping")
            return False
        try:
            with open(pub_path, "rb") as f:
                pub_key = load_pem_public_key(f.read())
            pub_key.verify(
                signature_bytes,
                payload_bytes,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                            salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
        except Exception:
            logger.error("License rotation: SIGNATURE INVALID on offered new_license_key — possible MITM")
            _send_tamper_report_sync("rotation_signature_invalid", {
                "offered_hwid": new_payload.get("hardware_id"),
            })
            return False

        # Hardware-id binding: the new key must be for THIS machine.
        local_hwid = _get_hardware_id()
        offered_hwid = (new_payload.get("hardware_id") or "")
        if offered_hwid != local_hwid:
            logger.error(
                "License rotation: hardware_id mismatch (local={} offered={})",
                local_hwid[:12] + "…", offered_hwid[:12] + "…",
            )
            _send_tamper_report_sync("rotation_hwid_mismatch", {
                "local_hwid":   local_hwid,
                "offered_hwid": offered_hwid,
            })
            return False

        # Belt: owner_email continuity. Only enforced when BOTH old and new
        # have one, so legacy keys without email still rotate.
        try:
            cur_raw = os.getenv("LICENSE_KEY", "").strip()
            if cur_raw and "." in cur_raw:
                cur_p64 = cur_raw.split(".", 1)[0]
                cur_p64 += "=" * (-len(cur_p64) % 4)
                cur_payload = json.loads(base64.urlsafe_b64decode(cur_p64).decode())
                cur_email = cur_payload.get("owner_email")
                new_email = new_payload.get("owner_email")
                if cur_email and new_email and cur_email != new_email:
                    logger.error(
                        "License rotation: owner_email mismatch (cur={} new={})",
                        cur_email, new_email,
                    )
                    return False
        except Exception:
            # Current key unparseable — not fatal; the lic-server confirmed
            # the rotation is for our hwid, that's what we really care about.
            pass

        # Atomic .env update.
        env_path = os.getenv("VPNMANAGER_ENV_PATH", "/opt/vpnmanager/.env")
        if not _atomic_env_update(env_path, "LICENSE_KEY", new_key):
            logger.error("License rotation: .env update failed at {}", env_path)
            return False

        logger.warning(
            "License rotated to plan={} tier={} hwid={} — restarting all vpnmanager services",
            new_payload.get("plan"), new_payload.get("tier"), local_hwid[:12] + "…",
        )

        # Detached restart of EVERY active vpnmanager-* unit, not just the api.
        # The validator loop runs only in vpnmanager-api, but client-portal
        # (serves /client-portal/features + the config/QR gates) and worker
        # (enforcement) each cache the license at startup — an api-only restart
        # leaves a rotated license (e.g. new portal_no_* flags) half-applied.
        # Popen lets us return cleanly; systemd then SIGTERMs us, uvicorn drains
        # and exits 0, and systemd brings every unit back on the new .env.
        # start_new_session detaches us from the api process group, and the
        # `systemctl restart` job is handed to PID 1, so it completes even
        # though we are about to die. Don't wait.
        import subprocess
        try:
            subprocess.Popen(
                ["bash", "-c",
                 "systemctl restart $(systemctl list-units --type=service "
                 "--state=active --plain --no-legend 'vpnmanager-*' "
                 "| awk '{print $1}')"],
                stdin  = subprocess.DEVNULL,
                stdout = subprocess.DEVNULL,
                stderr = subprocess.DEVNULL,
                start_new_session = True,
            )
        except Exception as e:
            logger.error("License rotation: systemctl restart failed: {}", e)
            # .env is already written; next manual restart will pick it up.
        return True
    except Exception as e:
        logger.error("License rotation: unhandled error: {}", e)
        return False


def _atomic_env_update(env_path: str, key: str, value: str) -> bool:
    """Replace KEY=… line in .env atomically (tempfile + os.replace).
    Preserves mode 0600. Returns True on success."""
    try:
        try:
            with open(env_path, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []

        prefix = f"{key}="
        found = False
        new_lines = []
        for line in lines:
            if line.startswith(prefix) or line.startswith(f"# {prefix}"):
                if not found:
                    new_lines.append(f"{key}={value}\n")
                    found = True
                # drop any subsequent duplicates
            else:
                new_lines.append(line)
        if not found:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{key}={value}\n")

        tmp_path = env_path + ".rotation.tmp"
        with open(tmp_path, "w") as f:
            f.writelines(new_lines)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, env_path)
        return True
    except Exception as e:
        logger.error("Atomic .env update failed: {}", e)
        return False
