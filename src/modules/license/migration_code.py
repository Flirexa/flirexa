"""
Self-service license migration codes (1.5.64+).

Lifetime-protected licenses bind to a hardware fingerprint at activation
time. When a customer legitimately moves to a new server, they need a way
to rebind WITHOUT calling the license server (because lifetime_protected
is offline-tolerant by design).

Design: each lifetime_protected license payload carries a `migration_secret`
(32 bytes random, signed by the lic-server alongside the rest of the
payload). Both the old and the new install can recompute it from the
LICENSE_KEY. The old panel HMAC-signs a migration receipt; the new
panel verifies the HMAC offline — no live lic-server contact required.

The lic-server only sees the migration *after the fact* via the next
heartbeat: the new install includes the migration receipt as proof that
its new fingerprint is intentional, not a clone. If the OLD fingerprint
keeps heartbeating after the migration was claimed, the lic-server flags
the license for an operator review (clone candidate).

Code format:
    MIGRATE-<32 base32 chars (HMAC truncated)>-<unix-ts>

The HMAC covers: license_id || ":" || timestamp_iso || ":" || from_hw_id.
Timestamp lets us expire codes after MIGRATION_CODE_TTL_DAYS.

NOTE: anyone with LICENSE_KEY can derive migration_secret. That's BY
DESIGN — if you have the key, you can move it. Anti-clone is detective
(via heartbeat fingerprint deduplication on the lic-server), not
preventive.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from loguru import logger


MIGRATION_CODE_TTL_DAYS = 7

# "Burning bridge" deadline: once a customer generates a migration code on
# a server, that server self-decommissions after this many days. This
# enforces "old server stops working after migration" without requiring
# the operator to manually shut it down — safer and simpler.
OLD_SERVER_DECOMMISSION_DAYS = 3

_HMAC_LEN_BYTES = 20  # 160 bits — Base32 → 32 chars

_MIGRATION_INITIATED_PATH = os.environ.get(
    "MIGRATION_INITIATED_PATH",
    str(__import__("pathlib").Path(__file__).parent.parent.parent.parent
        / "data" / "migration_initiated.json"),
)

_CODE_RE = re.compile(r"^MIGRATE-([A-Z2-7]{32})-(\d{10,20})$")


def _read_license_payload() -> Optional[dict]:
    """Decode the LICENSE_KEY env var without verifying signature.
    Returns None when no key, malformed, or unparseable."""
    raw = os.getenv("LICENSE_KEY", "").strip()
    if not raw or "." not in raw:
        return None
    try:
        head = raw.split(".", 1)[0]
        head += "=" * (-len(head) % 4)
        return json.loads(base64.urlsafe_b64decode(head).decode())
    except Exception as e:
        logger.debug("LICENSE_KEY payload not parseable: {}", e)
        return None


def _license_id_from_payload(payload: dict) -> str:
    """Stable per-license identifier — sha256 of (issued_at + hardware_id).

    The lic-server's `licenses` table doesn't expose its row-id in the
    payload, but issued_at is unique per license. We use a hash so the
    raw values aren't replayed in the migration code.
    """
    seed = (payload.get("issued_at", "") + ":" + payload.get("hardware_id", "")).encode()
    return hashlib.sha256(seed).hexdigest()[:32]


def _b32(value: bytes) -> str:
    return base64.b32encode(value).rstrip(b"=").decode()


def _b32_decode(s: str) -> bytes:
    s = s + "=" * (-len(s) % 8)
    return base64.b32decode(s)


@dataclass
class MigrationCode:
    code: str
    license_id: str
    from_hw_id: str
    issued_at: datetime
    expires_at: datetime


def _record_migration_initiated(license_id: str, code: str) -> None:
    """Persist that THIS server has handed out a migration code.

    From this moment on, a 3-day countdown starts. After it expires,
    `is_decommissioned()` returns True and LicenseManager falls back
    to FREE tier even though LICENSE_KEY signature still verifies.

    File is tamper-resistant in spirit only — anyone with root on the
    box can delete it. But that's not the threat model: the customer
    intentionally migrated, the file is for their own benefit (and ours,
    so the lic-server stops getting heartbeats from a stale install).
    """
    try:
        from pathlib import Path
        p = Path(_MIGRATION_INITIATED_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Idempotent: don't overwrite an earlier record so the deadline
        # doesn't get "extended" by clicking the button twice.
        if p.exists():
            return
        p.write_text(json.dumps({
            "initiated_at": datetime.now(timezone.utc).isoformat(),
            "license_id":   license_id,
            "code":         code,
            "deadline_days": OLD_SERVER_DECOMMISSION_DAYS,
        }))
        logger.warning(
            "Server migration initiated — this install will self-decommission "
            "in {} days. Move to the new server before then.",
            OLD_SERVER_DECOMMISSION_DAYS,
        )
    except Exception as e:
        logger.error("Failed to record migration_initiated: {}", e)


def get_migration_initiated() -> Optional[dict]:
    """Return migration record if this server has started the migration
    countdown, else None. Safe to call from any module."""
    try:
        from pathlib import Path
        p = Path(_MIGRATION_INITIATED_PATH)
        if not p.exists():
            return None
        return json.loads(p.read_text())
    except Exception:
        return None


def is_decommissioned() -> bool:
    """True if the migration countdown has elapsed on this server.

    Used by LicenseManager to refuse to grant paid features after the
    deadline, even though the LICENSE_KEY signature still verifies.
    """
    rec = get_migration_initiated()
    if not rec:
        return False
    try:
        initiated = datetime.fromisoformat(rec["initiated_at"])
        deadline = initiated + timedelta(days=int(rec.get("deadline_days", OLD_SERVER_DECOMMISSION_DAYS)))
        return datetime.now(timezone.utc) >= deadline
    except Exception:
        return False


def time_to_decommission() -> Optional[timedelta]:
    """How long until this server self-decommissions, or None if not migrating."""
    rec = get_migration_initiated()
    if not rec:
        return None
    try:
        initiated = datetime.fromisoformat(rec["initiated_at"])
        deadline = initiated + timedelta(days=int(rec.get("deadline_days", OLD_SERVER_DECOMMISSION_DAYS)))
        return deadline - datetime.now(timezone.utc)
    except Exception:
        return None


def cancel_migration() -> bool:
    """Erase the migration record — useful if customer abandoned the move
    before the deadline. Returns True if a record was removed.

    Note: any migration code already handed out remains cryptographically
    valid until its own 7-day TTL expires. Cancelling here only prevents
    THIS server from self-decommissioning."""
    try:
        from pathlib import Path
        p = Path(_MIGRATION_INITIATED_PATH)
        if p.exists():
            p.unlink()
            logger.info("Migration record cancelled — this server will not self-decommission")
            return True
    except Exception as e:
        logger.error("Failed to cancel migration: {}", e)
    return False


def generate_migration_code() -> Optional[MigrationCode]:
    """Sign a migration receipt for the currently-active license_key.

    Returns None when:
      - No LICENSE_KEY in env
      - License is not `lifetime_protected` (other types don't need this)
      - Payload missing migration_secret
    """
    payload = _read_license_payload()
    if payload is None:
        return None
    if payload.get("license_type") != "lifetime_protected":
        logger.warning(
            "generate_migration_code refused: license_type={} — only lifetime_protected supports self-service migration",
            payload.get("license_type"),
        )
        return None
    secret = payload.get("migration_secret")
    if not secret:
        logger.warning("generate_migration_code: payload has no migration_secret — old key, can't migrate")
        return None

    license_id = _license_id_from_payload(payload)
    from_hw_id = payload.get("hardware_id", "")
    ts = int(time.time())
    msg = f"{license_id}:{ts}:{from_hw_id}".encode()
    mac = hmac.new(secret.encode(), msg, hashlib.sha256).digest()[:_HMAC_LEN_BYTES]
    code = f"MIGRATE-{_b32(mac)}-{ts}"
    issued = datetime.fromtimestamp(ts, tz=timezone.utc)

    # Burning bridge: from now on this server self-decommissions in 3 days.
    _record_migration_initiated(license_id, code)

    return MigrationCode(
        code=code,
        license_id=license_id,
        from_hw_id=from_hw_id,
        issued_at=issued,
        expires_at=issued + timedelta(days=MIGRATION_CODE_TTL_DAYS),
    )


def verify_migration_code(code: str) -> Tuple[bool, str]:
    """Verify a migration code against the currently-active LICENSE_KEY.

    Returns (ok, message). Used on the NEW server during install: the
    operator pastes the code, panel verifies it offline, and on success
    the next heartbeat carries it as proof of legitimate migration.
    """
    payload = _read_license_payload()
    if payload is None:
        return False, "No LICENSE_KEY in environment"
    if payload.get("license_type") != "lifetime_protected":
        return False, "License is not lifetime_protected — migration codes don't apply"
    secret = payload.get("migration_secret")
    if not secret:
        return False, "License payload missing migration_secret (old key — can't migrate this way)"

    m = _CODE_RE.match(code.strip().upper())
    if not m:
        return False, "Invalid migration code format (expected MIGRATE-XXXXX-XXXXX-...)"
    mac_b32, ts_str = m.group(1), m.group(2)
    try:
        ts = int(ts_str)
    except ValueError:
        return False, "Invalid migration code timestamp"

    age = time.time() - ts
    if age < 0:
        return False, "Migration code timestamp is in the future"
    if age > MIGRATION_CODE_TTL_DAYS * 86_400:
        return False, f"Migration code expired (older than {MIGRATION_CODE_TTL_DAYS} days)"

    license_id = _license_id_from_payload(payload)
    from_hw_id = payload.get("hardware_id", "")
    msg = f"{license_id}:{ts}:{from_hw_id}".encode()
    expected = hmac.new(secret.encode(), msg, hashlib.sha256).digest()[:_HMAC_LEN_BYTES]
    try:
        actual = _b32_decode(mac_b32)
    except Exception:
        return False, "Invalid migration code (decode failure)"
    if not hmac.compare_digest(expected, actual):
        return False, "Migration code signature mismatch — code is from a different license"

    return True, "ok"


def parse_migration_code_metadata(code: str) -> Optional[dict]:
    """Parse the timestamp out of a code without verifying it. Used to
    show 'expires in X days' in the UI before submission."""
    m = _CODE_RE.match(code.strip().upper())
    if not m:
        return None
    try:
        ts = int(m.group(2))
    except ValueError:
        return None
    issued = datetime.fromtimestamp(ts, tz=timezone.utc)
    return {
        "issued_at":  issued.isoformat(),
        "expires_at": (issued + timedelta(days=MIGRATION_CODE_TTL_DAYS)).isoformat(),
    }
