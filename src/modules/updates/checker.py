"""
Update Checker — fetches and verifies the remote update manifest.

Manifest URL: {UPDATE_SERVER_URL}/updates/{channel}/manifest.json
Signature: RSA-PSS-SHA256 over base64url(canonical_json), public key in data/update_public.pem

Trust model:
  - The manifest is signed with update_private.pem (kept only on the license server).
  - package_url is a field inside the signed manifest — tampering with the URL
    invalidates the RSA-PSS signature, so URL injection is not possible.
  - Package authenticity is guaranteed by the SHA-256 in the signed manifest
    (package_sha256 field), verified after download.
  - No separate package file signature is required; the manifest signature +
    SHA-256 verification together provide equivalent security.
"""

import base64
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

_UPDATE_SERVER_URL = os.getenv(
    "UPDATE_SERVER_URL",
    # Public Flirexa update server. Operators running their own license
    # server set UPDATE_SERVER_URL in .env to override this default.
    "https://flirexa.biz",
)

# Separate connect and read timeouts for better diagnostics
# Keep combined timeout well under the frontend's 15s axios timeout
_CONNECT_TIMEOUT = 5.0    # seconds to establish connection
_READ_TIMEOUT    = 8.0    # seconds to read response
_MAX_MANIFEST_BYTES = 64 * 1024   # 64KB — manifests are small JSON files
_MAX_PACKAGE_BYTES = int(os.getenv("UPDATE_MAX_PACKAGE_BYTES", str(512 * 1024 * 1024)))

_PUB_KEY_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "update_public.pem"

# In-memory cache: (manifest_dict, fetched_at_timestamp, channel)
_cache: Optional[Tuple[dict, float, str]] = None
_CACHE_TTL = 3600  # 1 hour


# ── Manifest schema ────────────────────────────────────────────────────────────

REQUIRED_FIELDS = {
    "schema_version", "version", "published_at", "channel",
    "update_type", "release_notes", "package_url", "sha256",
    "min_supported_version", "rollback_supported",
    "requires_migration", "requires_restart", "signature",
}


# ── RSA public key loader ──────────────────────────────────────────────────────

_pub_key = None


def _load_pub_key():
    global _pub_key
    if _pub_key is not None:
        return _pub_key

    key_path = Path(os.getenv("UPDATE_PUBLIC_KEY_PATH", str(_PUB_KEY_PATH)))
    if not key_path.exists():
        raise RuntimeError(f"Update public key not found: {key_path}")

    from cryptography.hazmat.primitives import serialization
    with open(key_path, "rb") as f:
        _pub_key = serialization.load_pem_public_key(f.read())
    return _pub_key


# ── Signature verification ─────────────────────────────────────────────────────

def _verify_manifest_signature(manifest: dict) -> bool:
    """
    Verify RSA-PSS signature on manifest.

    The signature covers: base64url(canonical_json(manifest_without_signature)).
    """
    sig_b64 = manifest.get("signature")
    if not sig_b64:
        return False

    payload_dict = {k: v for k, v in manifest.items() if k != "signature"}
    payload_json = json.dumps(payload_dict, separators=(",", ":"), sort_keys=True)
    payload_b64  = base64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()

    try:
        sig_bytes = base64.urlsafe_b64decode(sig_b64 + "==")
    except Exception:
        return False

    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        key = _load_pub_key()
        key.verify(
            sig_bytes,
            payload_b64.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


def _canonical_manifest_payload(manifest: dict) -> dict:
    """Normalize legacy/new manifest field names into one canonical shape."""
    payload = dict(manifest)

    if "published_at" not in payload and "release_date" in payload:
        payload["published_at"] = payload["release_date"]
    if "release_date" not in payload and "published_at" in payload:
        payload["release_date"] = payload["published_at"]

    if "release_notes" not in payload and "changelog" in payload:
        payload["release_notes"] = payload["changelog"]
    if "changelog" not in payload and "release_notes" in payload:
        payload["changelog"] = payload["release_notes"]

    if "sha256" not in payload and "package_sha256" in payload:
        payload["sha256"] = payload["package_sha256"]
    if "package_sha256" not in payload and "sha256" in payload:
        payload["package_sha256"] = payload["sha256"]

    if "min_supported_version" not in payload and "minimum_supported_version" in payload:
        payload["min_supported_version"] = payload["minimum_supported_version"]
    if "minimum_supported_version" not in payload and "min_supported_version" in payload:
        payload["minimum_supported_version"] = payload["min_supported_version"]

    if "requires_migration" not in payload and "has_db_migrations" in payload:
        payload["requires_migration"] = payload["has_db_migrations"]
    if "has_db_migrations" not in payload and "requires_migration" in payload:
        payload["has_db_migrations"] = payload["requires_migration"]

    return payload


def _allowed_update_hosts() -> set[str]:
    hosts = set()
    primary = urlparse(_UPDATE_SERVER_URL).hostname
    if primary:
        hosts.add(primary)
    extra = os.getenv("UPDATE_SERVER_ALLOWED_HOSTS", "")
    for host in extra.split(","):
        host = host.strip()
        if host:
            hosts.add(host)
    return hosts


# ── Version comparison ─────────────────────────────────────────────────────────

def _parse_version(v: str) -> tuple:
    """Parse '1.2.3' → (1, 2, 3). Returns (0,0,0) on error."""
    try:
        parts = v.strip().split(".")
        return tuple(int(x) for x in parts[:3])
    except Exception:
        return (0, 0, 0)


def is_newer(available: str, current: str) -> bool:
    return _parse_version(available) > _parse_version(current)


def is_compatible(manifest: dict, current: str) -> bool:
    """Check minimum_supported_version constraint."""
    min_ver = manifest.get("min_supported_version", manifest.get("minimum_supported_version", "0.0.0"))
    return _parse_version(current) >= _parse_version(min_ver)


# ── Fetch manifest ─────────────────────────────────────────────────────────────

def _manifest_url(channel: str) -> str:
    base = _UPDATE_SERVER_URL.rstrip("/")
    return f"{base}/updates/{channel}/manifest.json"


async def fetch_manifest(channel: str = "stable", force: bool = False) -> Tuple[Optional[dict], Optional[str]]:
    """
    Fetch and verify the update manifest for given channel.

    Returns (manifest_dict, None) on success or (None, error_message) on failure.
    Uses in-memory cache (1h TTL) unless force=True.
    """
    global _cache

    if not force and _cache is not None:
        manifest, fetched_at, cached_channel = _cache
        if cached_channel == channel and time.time() - fetched_at < _CACHE_TTL:
            logger.debug("Using cached manifest for channel=%s", channel)
            return manifest, None

    url = _manifest_url(channel)
    try:
        timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT,
            read=_READ_TIMEOUT,
            write=5.0,
            pool=5.0,
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)

            if resp.status_code == 404:
                return None, f"No manifest found for channel '{channel}'"
            if resp.status_code == 403:
                return None, "Update server rejected request (403 Forbidden) — check admin token"
            if resp.status_code >= 500:
                return None, f"Update server error (HTTP {resp.status_code}) — try again later"
            if resp.status_code != 200:
                return None, f"Update server returned HTTP {resp.status_code}"

            # Guard against unexpectedly large responses
            content = resp.content
            if len(content) > _MAX_MANIFEST_BYTES:
                return None, f"Manifest response too large ({len(content)} bytes) — rejected for security"

            raw_manifest = resp.json()

    except httpx.ConnectTimeout:
        return None, "Update server connection timeout — check network connectivity"
    except httpx.ReadTimeout:
        return None, "Update server read timeout — server may be slow"
    except httpx.ConnectError as e:
        err_str = str(e).lower()
        if any(x in err_str for x in ("name", "dns", "resolve", "nodename", "no address", "getaddrinfo")):
            return None, "Cannot reach update server: DNS resolution failed"
        return None, "Cannot reach update server: connection refused"
    except httpx.TLSError as e:
        return None, f"TLS error connecting to update server: {type(e).__name__}"
    except httpx.TimeoutException:
        return None, "Update server timeout"
    except Exception as e:
        return None, f"Failed to reach update server: {type(e).__name__}"

    if not _verify_manifest_signature(raw_manifest):
        logger.warning(
            "Manifest signature FAILED for version=%s channel=%s",
            raw_manifest.get("version"), raw_manifest.get("channel"),
        )
        return None, "Manifest signature invalid — update rejected for security"

    manifest = _canonical_manifest_payload(raw_manifest)

    # Validate required fields
    missing = REQUIRED_FIELDS - set(manifest.keys())
    if missing:
        return None, f"Manifest missing required fields: {sorted(missing)}"

    if manifest.get("schema_version") != 1:
        return None, f"Unsupported manifest schema_version: {manifest.get('schema_version')}"

    pkg_url = manifest.get("package_url", "")
    parsed_pkg = urlparse(pkg_url)
    if parsed_pkg.scheme != "https":
        return None, "Manifest package_url has invalid scheme — https required"
    if not parsed_pkg.hostname or parsed_pkg.hostname not in _allowed_update_hosts():
        return None, f"Manifest package_url host not allowed: {parsed_pkg.hostname or 'missing'}"

    sha256 = manifest.get("sha256", "")
    if not isinstance(sha256, str) or len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256.lower()):
        return None, "Manifest sha256 is invalid"

    if "package_size" in manifest and manifest.get("package_size") not in (None, ""):
        try:
            package_size = int(manifest.get("package_size"))
        except Exception:
            return None, "Manifest package_size is invalid"
        if package_size <= 0 or package_size > _MAX_PACKAGE_BYTES:
            return None, f"Manifest package_size out of bounds: {package_size}"
    else:
        manifest["package_size"] = 0

    try:
        # datetime.fromisoformat accepts both "Z" and "+00:00" after replace.
        _published = str(manifest.get("published_at", "")).replace("Z", "+00:00")
        from datetime import datetime
        datetime.fromisoformat(_published)
    except Exception:
        return None, "Manifest published_at is invalid"

    # Verify signature (must come after field validation)
    logger.info(
        "Manifest OK: version=%s channel=%s type=%s",
        manifest["version"], manifest["channel"], manifest["update_type"],
    )

    _cache = (manifest, time.time(), channel)
    return manifest, None


def invalidate_cache():
    global _cache
    _cache = None


async def check_for_update(
    current_version: str,
    channel: str = "stable",
    force: bool = False,
) -> Tuple[Optional[dict], Optional[str]]:
    """
    High-level check: fetch manifest and determine if update is available.

    Returns:
      (manifest, None)  — update available and compatible
      (None, None)      — already up to date
      (None, error_str) — error during check
    """
    manifest, err = await fetch_manifest(channel=channel, force=force)
    if err:
        return None, err

    available_version = manifest["version"]

    if not is_newer(available_version, current_version):
        return None, None  # up to date

    if not is_compatible(manifest, current_version):
        return None, (
            f"Update {available_version} requires minimum version "
            f"{manifest['min_supported_version']}, current is {current_version}"
        )

    return manifest, None


# ── Package checksum verification ─────────────────────────────────────────────

def verify_package_checksum(file_path: Path, expected_sha256: str) -> bool:
    """Compute SHA-256 of downloaded package and compare to manifest value."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    actual = sha.hexdigest()
    if actual != expected_sha256:
        logger.error("Checksum mismatch: expected=%s actual=%s", expected_sha256, actual)
        return False
    return True
