"""
License Manager — RSA-signed license validation with hardware binding
"""

import hmac
import os
import re
import base64
import hashlib
import json
import platform
import threading
import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
from pathlib import Path
from loguru import logger


GRACE_PERIOD_DAYS = 7


class LicenseType(str, Enum):
    """License plan types (new names + old names as backward-compat aliases)."""
    FREE       = "free"       # open-core: no license key, no expiry, no online check
    TRIAL      = "trial"      # paid tier on trial period (used after explicit activation)
    # New plan names
    STANDARD   = "standard"
    PRO        = "pro"
    ENTERPRISE = "enterprise"
    # Old tier names — kept for backward compat with existing signed keys
    STARTER    = "starter"    # alias for STANDARD
    BUSINESS   = "business"   # alias for PRO


# Map old tier names → canonical plan names (for display / logic)
_TIER_TO_PLAN: Dict[str, str] = {
    "starter":  "standard",
    "business": "pro",
}


def _normalize_license_type(raw: str) -> LicenseType:
    """Resolve old tier or new plan name → LicenseType enum value."""
    raw = raw.lower().strip()
    try:
        return LicenseType(raw)
    except ValueError:
        pass
    # Unknown values default to FREE (safest fallback for open-core)
    return LicenseType.FREE


@dataclass
class LicenseInfo:
    """License information"""
    type: LicenseType
    max_clients: int
    max_servers: int
    features: List[str]
    expires_at: Optional[datetime] = None
    is_valid: bool = True
    validation_message: str = ""
    hardware_id: str = ""
    grace_period: bool = False
    billing_type: str = "lifetime"   # monthly / lifetime / annual

    @property
    def plan(self) -> str:
        """Canonical plan name (normalized from old tier if needed)."""
        return _TIER_TO_PLAN.get(self.type.value, self.type.value)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    def in_grace_period(self) -> bool:
        """Check if in grace period after expiry"""
        if self.expires_at is None:
            return False
        now = datetime.now(timezone.utc)
        grace_end = self.expires_at + timedelta(days=GRACE_PERIOD_DAYS)
        return self.expires_at <= now < grace_end

    def days_remaining(self) -> Optional[int]:
        if self.expires_at is None:
            return None
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, delta.days)

    def can_add_client(self, current_count: int) -> bool:
        return current_count < self.max_clients

    def can_add_server(self, current_count: int) -> bool:
        return current_count < self.max_servers

    def has_feature(self, feature: str) -> bool:
        return feature in self.features


# License plan configurations (fallback for trial / when payload lacks features list)
LICENSE_TIERS = {
    LicenseType.FREE: {
        "max_clients": 80,
        # FREE: one server per protocol (WireGuard + AmneziaWG = up to 2).
        # Per-protocol enforcement happens in the server-create endpoint.
        "max_servers": 2,
        # FREE tier never expires — no duration_days
        "features": [
            "basic_management",
            "telegram_admin_bot",
            "wireguard",
            "amneziawg",
            "client_portal",
            "nowpayments",
        ]
    },
    LicenseType.TRIAL: {
        "max_clients": 5,
        "max_servers": 1,
        "duration_days": 7,
        "features": [
            "basic_management",
            "telegram_admin_bot",
            "wireguard_only",
        ]
    },
    LicenseType.STANDARD: {
        "max_clients": 300,
        # Starter: one of each protocol (WireGuard + AmneziaWG + Hysteria2 + TUIC = 4).
        "max_servers": 4,
        "features": [
            "wireguard",
            "amneziawg",
            "proxy_protocols",   # Hysteria2 + TUIC
            "client_portal",
            "telegram_bots",
            "promo_codes",
            "auto_renewal",
        ],
    },
    LicenseType.PRO: {
        "max_clients": 2000,
        "max_servers": 10,
        "features": [
            "wireguard",
            "amneziawg",
            "proxy_protocols",
            "client_portal",
            "telegram_bots",
            "multi_server",
            "traffic_rules",
            "android_app",
            "white_label_basic",
            "auto_backup",
            "promo_codes",
            "auto_renewal",
        ],
    },
    # Old tier names — STARTER/BUSINESS map to STANDARD/PRO conceptually,
    # extended with feature flags introduced after the tier rename so signed
    # keys generated before the rename still unlock the right capabilities.
    LicenseType.STARTER: {
        "max_clients": 300,
        "max_servers": 1,
        "features": [
            "basic_management",
            "telegram_admin_bot",
            "traffic_limits",
            "bandwidth_limits",
            "expiry_timers",
            "wireguard",
            "amneziawg",
            "proxy_protocols",
            "client_portal",
            "promo_codes",
            "auto_renewal",
        ]
    },
    LicenseType.BUSINESS: {
        "max_clients": 2000,
        "max_servers": 10,
        "features": [
            "basic_management",
            "telegram_admin_bot",
            "telegram_client_bot",
            "traffic_limits",
            "bandwidth_limits",
            "expiry_timers",
            "multi_server",
            "client_portal",
            "traffic_rules",
            "wireguard",
            "amneziawg",
            "proxy_protocols",
            "white_label_basic",
            "auto_backup",
            "promo_codes",
            "auto_renewal",
        ]
    },
    LicenseType.ENTERPRISE: {
        "max_clients": 999999,
        "max_servers": 999999,
        "features": [
            "basic_management",
            "telegram_admin_bot",
            "telegram_client_bot",
            "traffic_limits",
            "bandwidth_limits",
            "expiry_timers",
            "multi_server",
            "client_portal",
            "traffic_rules",
            "android_app",
            "payments",
            "white_label",
            "white_label_basic",
            "priority_support",
            "wireguard",
            "amneziawg",
            "proxy_protocols",
            "corporate_vpn",
            "auto_backup",
            "promo_codes",
            "auto_renewal",
            "manager_rbac",
        ]
    },
}

# Module-level cache for server ID (never changes)
_cached_server_id: Optional[str] = None


def _find_env_file() -> Optional[str]:
    """Locate the .env file used by the running deployment."""
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"),
        "/opt/vpnmanager/.env",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _save_trial_env(key: str, value: str) -> None:
    """Persist a key=value pair to the .env file (append or update)."""
    env_path = _find_env_file()
    if not env_path:
        logger.warning("Cannot persist trial data: .env file not found")
        return
    try:
        with open(env_path, "r") as f:
            content = f.read()
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        else:
            if not content.endswith("\n"):
                content += "\n"
            content += f"{replacement}\n"
        with open(env_path, "w") as f:
            f.write(content)
    except Exception as e:
        logger.warning(f"Failed to persist trial data to .env: {e}")


def _find_public_key() -> Optional[str]:
    """Find the license public key file"""
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "license_public.pem"),
        "/opt/vpnmanager/license_public.pem",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _make_aware(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware (UTC)"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class LicenseManager:
    """
    Manages license validation using RSA-signed keys.

    License key format: base64(payload_json).base64(rsa_signature)
    Payload: {tier, max_clients, max_servers, features[], expires_at, hardware_id}
    """

    def __init__(self, license_key: Optional[str] = None):
        self.license_key = license_key
        self._license_info: Optional[LicenseInfo] = None
        self._public_key = None

    def get_server_id(self) -> str:
        """Generate unique server identifier for hardware binding.

        Returns the legacy (v1) hardware ID for backward compatibility with
        existing licenses. New licenses will also be bound to this ID.
        The extended fingerprint is used for clone detection via heartbeats.
        """
        global _cached_server_id
        if _cached_server_id:
            return _cached_server_id

        components = [
            platform.node(),
            platform.machine(),
            str(uuid.getnode()),
        ]

        # /etc/machine-id — persistent systemd identifier
        for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            try:
                if os.path.exists(path):
                    with open(path, "r") as f:
                        val = f.read().strip()
                        if val:
                            components.append(val)
                            break
            except Exception:
                pass

        # v1 ID: hostname + arch + MAC + machine-id (backward compatible)
        combined = "|".join(components)
        _cached_server_id = hashlib.sha256(combined.encode()).hexdigest()[:32]
        return _cached_server_id

    def get_extended_fingerprint(self) -> str:
        """Extended hardware fingerprint with additional entropy sources.

        Used for clone detection in heartbeats — harder to spoof than v1 ID.
        Not used for license binding (would break existing licenses).
        Includes: DMI UUID, disk serial, RAM size on top of v1 sources.
        """
        components = [
            platform.node(),
            platform.machine(),
            str(uuid.getnode()),
        ]

        for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            try:
                if os.path.exists(path):
                    with open(path, "r") as f:
                        val = f.read().strip()
                        if val:
                            components.append(val)
                            break
            except Exception:
                pass

        # DMI product UUID — BIOS-level, very hard to spoof
        try:
            dmi_path = "/sys/class/dmi/id/product_uuid"
            if os.path.exists(dmi_path):
                with open(dmi_path, "r") as f:
                    val = f.read().strip()
                    if val and val != "Not Settable":
                        components.append(val)
        except Exception:
            pass

        # Primary disk serial
        try:
            import subprocess
            result = subprocess.run(
                ["lsblk", "--nodeps", "-o", "SERIAL", "-n"],
                capture_output=True, text=True, timeout=5
            )
            serials = [s.strip() for s in result.stdout.strip().split("\n") if s.strip()]
            if serials:
                components.append(serials[0])
        except Exception:
            pass

        # Total RAM
        try:
            import psutil
            components.append(str(psutil.virtual_memory().total))
        except Exception:
            pass

        combined = "|".join(components)
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

    def _load_public_key(self):
        """Load RSA public key for signature verification"""
        if self._public_key:
            return self._public_key

        key_path = _find_public_key()
        if not key_path:
            logger.warning("License public key not found")
            return None

        try:
            from cryptography.hazmat.primitives.serialization import load_pem_public_key
            with open(key_path, "rb") as f:
                self._public_key = load_pem_public_key(f.read())
            return self._public_key
        except Exception as e:
            logger.error(f"Failed to load public key: {e}")
            return None

    def validate_license(self, license_key: Optional[str] = None) -> LicenseInfo:
        """Validate a license key using RSA signature verification."""
        # INTERNAL_LICENSE_MODE is only honoured when BOTH conditions are met:
        # 1. No public key is present (i.e. pure dev environment without a key file)
        # 2. A .dev-mode marker file exists in the install root
        # This prevents trivial .env editing attacks in production.
        if os.getenv("INTERNAL_LICENSE_MODE", "false").lower() == "true":
            dev_marker = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), ".dev-mode")
            if not _find_public_key() and os.path.exists(dev_marker):
                return self._create_internal_license("Internal developer license mode")
            if _find_public_key():
                logger.warning(
                    "INTERNAL_LICENSE_MODE is set but ignored — license_public.pem is present"
                )
            elif not os.path.exists(dev_marker):
                logger.warning(
                    "INTERNAL_LICENSE_MODE is set but ignored — .dev-mode marker file missing"
                )

        key = license_key or self.license_key

        if not key:
            # No license key → FREE tier (open-core default).
            # No network calls, no expiry, full free feature set.
            return self._create_free_license("No license key — running in FREE mode")

        try:
            return self._parse_and_validate(key, skip_signature=False)
        except Exception as e:
            logger.error(f"License validation error: {e}")
            # Invalid key → fall back to FREE so user keeps base functionality
            return self._create_free_license("License key invalid — falling back to FREE mode")

    def _parse_and_validate(self, key: str, skip_signature: bool = False) -> LicenseInfo:
        """Parse license key and validate signature + constraints"""

        # Guard against DoS via absurdly long keys (max 8 KB is more than enough)
        if len(key) > 8192:
            return self._create_free_license("License key too long")

        # Sanity-check system clock: if the clock is before the software release
        # date someone may have rolled it back to bypass expiry checks.
        _RELEASE_DATE = datetime(2025, 1, 1, tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < _RELEASE_DATE:
            logger.error(
                "System clock appears to be in the past — possible time-manipulation attack"
            )
            return self._create_free_license("System clock validation failed")

        # Split key into payload and signature
        parts = key.strip().split(".")
        if len(parts) != 2:
            return self._create_free_license("Invalid license key format")

        try:
            # Add base64url padding back (generator strips it with rstrip("="))
            payload_bytes = base64.urlsafe_b64decode(parts[0] + "==")
            payload = json.loads(payload_bytes)
        except Exception:
            return self._create_free_license("Invalid license key encoding")

        # Verify RSA signature
        if not skip_signature:
            public_key = self._load_public_key()
            if not public_key:
                return self._create_free_license("License public key not found — cannot verify")

            try:
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.asymmetric import padding

                signature = base64.urlsafe_b64decode(parts[1] + "==")
                public_key.verify(
                    signature,
                    payload_bytes,
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH,
                    ),
                    hashes.SHA256(),
                )
            except Exception:
                return self._create_free_license("Invalid license signature")

        # Extract fields — support both new "plan" and old "tier" fields
        # New payloads have both fields; old payloads have only "tier"
        raw_plan     = payload.get("plan") or payload.get("tier", "trial")
        license_type = _normalize_license_type(raw_plan)
        billing_type = payload.get("billing_type", "lifetime")

        max_clients = payload.get("max_clients", 10)
        max_servers = payload.get("max_servers", 1)
        features = payload.get("features", LICENSE_TIERS.get(license_type, {}).get("features", []))
        hardware_id = payload.get("hardware_id", "")

        # Parse expiry — require explicit timezone to prevent ambiguous local-time attacks
        expires_at = None
        expires_str = payload.get("expires_at")
        if expires_str:
            try:
                dt = datetime.fromisoformat(expires_str)
                if dt.tzinfo is None:
                    return self._create_free_license(
                        "License expiry must include timezone info (e.g. 2026-03-10T00:00:00+00:00)"
                    )
                expires_at = dt
            except Exception:
                return self._create_free_license("Invalid license expiry date")

        # Check hardware binding (timing-safe comparison).
        # hardware_id must be explicitly non-empty; an absent or blank string would
        # allow a signed key to run on any server — we reject such keys.
        if not hardware_id:
            return self._create_free_license("License has no hardware binding (hardware_id required)")
        if not hmac.compare_digest(hardware_id, self.get_server_id()):
            logger.warning("License hardware ID mismatch")
            return self._create_free_license("License not valid for this server")

        # Check expiry
        grace_period = False
        if expires_at:
            now = datetime.now(timezone.utc)
            grace_end = expires_at + timedelta(days=GRACE_PERIOD_DAYS)
            if now >= grace_end:
                return self._create_free_license("License expired (past grace period)")
            elif now >= expires_at:
                grace_period = True

        self._license_info = LicenseInfo(
            type=license_type,
            max_clients=max_clients,
            max_servers=max_servers,
            features=features,
            expires_at=expires_at,
            is_valid=True,
            validation_message=f"License validated: {license_type.value}" + (" (grace period)" if grace_period else ""),
            hardware_id=hardware_id,
            grace_period=grace_period,
            billing_type=billing_type,
        )

        logger.info(f"License validated: plan={license_type.value} billing={billing_type}, clients={max_clients}, servers={max_servers}")
        return self._license_info

    def _create_free_license(self, message: str = "") -> LicenseInfo:
        """Create a FREE-tier license — open-core mode.

        No network calls, no expiry, no grace period.
        Pure local mode: works offline forever, no license server contact.

        Used when:
          - No LICENSE_KEY env var is set (open-core default)
          - License key is invalid/corrupted (fall back gracefully to FREE)
          - License server unreachable AND no cached paid license (FREE fallback)
        """
        tier = LICENSE_TIERS[LicenseType.FREE]
        self._license_info = LicenseInfo(
            type=LicenseType.FREE,
            max_clients=tier["max_clients"],
            max_servers=tier["max_servers"],
            features=list(tier["features"]),
            expires_at=None,             # never expires
            is_valid=True,
            validation_message=message or "Free tier (open-core)",
            hardware_id=self.get_server_id(),
            grace_period=False,
            billing_type="free",
        )
        return self._license_info

    def _create_trial_license(self, message: str = "") -> LicenseInfo:
        """Create a trial license with persistent start date to prevent reset abuse.

        Trial start is registered on the license server — even full reinstall
        and .env deletion won't reset the trial period.

        Note: in open-core mode, "trial" is reserved for explicitly-activated
        paid-tier trials (e.g. 14-day Business trial). For "no license key"
        case, use _create_free_license() instead.
        """
        tier = LICENSE_TIERS[LicenseType.TRIAL]
        now = datetime.now(timezone.utc)
        server_hw = self.get_server_id()

        # Step 1: Check trial with license server (source of truth)
        trial_start = None
        try:
            import httpx
            ls_url = os.getenv("LICENSE_SERVER_URL", "https://flirexa.biz").rstrip("/")
            resp = httpx.post(
                f"{ls_url}/api/trial/register",
                json={"hardware_id": server_hw},
                timeout=10,
                verify=True,
            )
            if resp.status_code == 200:
                srv_data = resp.json()
                trial_start = datetime.fromisoformat(srv_data["started_at"])
                if trial_start.tzinfo is None:
                    trial_start = trial_start.replace(tzinfo=timezone.utc)
                logger.info(f"Trial verified with license server: started={srv_data['started_at']}, days_remaining={srv_data.get('days_remaining')}")
        except Exception as e:
            logger.warning(f"License server trial check failed (using local): {e}")

        # Step 2: Fallback to local .env if server unreachable
        if trial_start is None:
            trial_start_str = os.getenv("TRIAL_STARTED_AT", "").strip()
            trial_hw = os.getenv("TRIAL_HARDWARE_ID", "").strip()

            if trial_start_str and hmac.compare_digest(trial_hw, server_hw):
                try:
                    trial_start = datetime.fromisoformat(trial_start_str)
                    if trial_start.tzinfo is None:
                        trial_start = trial_start.replace(tzinfo=timezone.utc)
                except Exception:
                    trial_start = now
            else:
                trial_start = now

        # Step 3: Persist locally
        _save_trial_env("TRIAL_STARTED_AT", trial_start.isoformat())
        _save_trial_env("TRIAL_HARDWARE_ID", server_hw)
        os.environ["TRIAL_STARTED_AT"] = trial_start.isoformat()
        os.environ["TRIAL_HARDWARE_ID"] = server_hw

        expires_at = trial_start + timedelta(days=tier["duration_days"])
        grace_end = expires_at + timedelta(days=GRACE_PERIOD_DAYS)

        if now >= grace_end:
            # Trial fully expired — block access entirely.
            logger.warning("Trial fully expired (past grace period) — blocking access")
            self._license_info = LicenseInfo(
                type=LicenseType.TRIAL,
                max_clients=0,
                max_servers=0,
                features=[],
                expires_at=expires_at,
                is_valid=False,
                validation_message="Trial expired — please purchase a license",
                hardware_id=server_hw,
                grace_period=False,
            )
            return self._license_info

        grace_period = now >= expires_at
        self._license_info = LicenseInfo(
            type=LicenseType.TRIAL,
            max_clients=tier["max_clients"],
            max_servers=tier["max_servers"],
            features=tier["features"],
            expires_at=expires_at,
            is_valid=True,
            validation_message=message or "Trial license activated",
            hardware_id=server_hw,
            grace_period=grace_period,
        )

        logger.info(f"Trial license: started={trial_start.date()}, expires={expires_at.date()}, grace={grace_period}")
        return self._license_info

    def _create_internal_license(self, message: str = "") -> LicenseInfo:
        """Create a permanent internal developer license."""
        tier = LICENSE_TIERS[LicenseType.ENTERPRISE]

        self._license_info = LicenseInfo(
            type=LicenseType.ENTERPRISE,
            max_clients=tier["max_clients"],
            max_servers=tier["max_servers"],
            features=tier["features"],
            expires_at=None,
            is_valid=True,
            validation_message=message or "Internal developer license mode",
        )

        logger.info(f"Internal developer license activated: {message}")
        return self._license_info

    def get_license_info(self) -> LicenseInfo:
        """Get current license info (validates if not yet done)"""
        if self._license_info is None:
            self._license_info = self.validate_license()
        return self._license_info

    def check_limits(self, current_clients: int, current_servers: int) -> Dict[str, Any]:
        """Check if current usage is within license limits"""
        license_info = self.get_license_info()

        return {
            "within_limits": (
                current_clients < license_info.max_clients and
                current_servers < license_info.max_servers
            ),
            "clients": {
                "current": current_clients,
                "max": license_info.max_clients,
                "available": max(0, license_info.max_clients - current_clients),
                "at_limit": current_clients >= license_info.max_clients,
            },
            "servers": {
                "current": current_servers,
                "max": license_info.max_servers,
                "available": max(0, license_info.max_servers - current_servers),
                "at_limit": current_servers >= license_info.max_servers,
            },
            "license_type": license_info.type.value,
            "expires_at": license_info.expires_at.isoformat() if license_info.expires_at else None,
            "days_remaining": license_info.days_remaining(),
            "grace_period": license_info.grace_period,
        }

    def get_features(self) -> List[str]:
        """Get list of available features"""
        return self.get_license_info().features

    def has_feature(self, feature: str) -> bool:
        """Check if a feature is available"""
        return self.get_license_info().has_feature(feature)

    def require_feature(self, feature: str) -> None:
        """Require a feature — raises PermissionError if unavailable"""
        if not self.has_feature(feature):
            raise PermissionError(
                f"Feature '{feature}' requires a higher license tier. "
                f"Current: {self.get_license_info().type.value}"
            )

    def is_properly_activated(self) -> bool:
        """Return True if a valid PAID license is active on this machine.

        FREE and TRIAL tiers are NOT considered "properly activated" — they
        are valid usage modes but not paid subscriptions. Used by code that
        needs to distinguish "open-core free" vs "paying customer".
        """
        try:
            info = self.get_license_info()
            return (
                info.is_valid
                and info.type not in (LicenseType.FREE, LicenseType.TRIAL)
                and not info.is_expired()
            )
        except Exception:
            return False

    def is_free(self) -> bool:
        """Return True if running in FREE (open-core) mode.

        This means: no LICENSE_KEY set, or invalid key fell back to FREE.
        FREE mode never makes network calls, never expires.
        """
        try:
            return self.get_license_info().type == LicenseType.FREE
        except Exception:
            return True   # Safe fallback — treat unknown state as FREE

    def is_paid(self) -> bool:
        """Return True if a valid paid license is active (excludes FREE and TRIAL)."""
        return self.is_properly_activated()

    def verify_integrity(self) -> bool:
        """Verify that critical license files haven't been tampered with"""
        try:
            key_path = _find_public_key()
            if not key_path or not os.path.exists(key_path):
                return True  # No key = trial mode, not tampering
            # Verify the public key is a valid PEM RSA key
            with open(key_path, "rb") as f:
                key_data = f.read()
            if b"BEGIN PUBLIC KEY" not in key_data:
                logger.warning("License public key appears corrupted")
                return False
            from cryptography.hazmat.primitives.serialization import load_pem_public_key
            pk = load_pem_public_key(key_data)
            if pk.key_size < 2048:
                logger.warning("License public key is too small")
                return False
            return True
        except Exception as e:
            logger.warning(f"Integrity check failed: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get license status summary"""
        license_info = self.get_license_info()

        result: Dict[str, Any] = {
            "server_id":    self.get_server_id(),
            "license_type": license_info.type.value,
            "plan":         license_info.plan,
            "billing_type": license_info.billing_type,
            "is_valid":     license_info.is_valid,
            "max_clients":  license_info.max_clients,
            "max_servers":  license_info.max_servers,
            "features":     license_info.features,
            "expires_at":   license_info.expires_at.isoformat() if license_info.expires_at else None,
            "days_remaining": license_info.days_remaining(),
            "grace_period": license_info.grace_period,
            "message":      license_info.validation_message,
        }

        # Append online validation state if the validator is running
        try:
            from .online_validator import get_online_status
            result["online"] = get_online_status()
        except ImportError:
            pass

        return result


# Global license manager instance
_license_manager: Optional[LicenseManager] = None
_license_lock = threading.Lock()


def get_license_manager() -> LicenseManager:
    """Get the global license manager instance (thread-safe)"""
    global _license_manager
    if _license_manager is None:
        with _license_lock:
            if _license_manager is None:
                license_key = os.getenv("LICENSE_KEY")
                mgr = LicenseManager(license_key)
                if not mgr.verify_integrity():
                    logger.error("License integrity check failed — forcing FREE mode")
                    mgr.license_key = None

                _license_manager = mgr
    return _license_manager


def reset_license_manager():
    """Reset global instance (used after activating new key)"""
    global _license_manager
    with _license_lock:
        _license_manager = None


def check_license() -> LicenseInfo:
    """Check and return current license info"""
    return get_license_manager().get_license_info()
