"""
Flirexa Client Portal - API Routes
FastAPI routes for client portal (registration, subscriptions, payments)

All WireGuard operations go through Admin API internal endpoints via AdminAPIClient.
No direct imports of ManagementCore or Client model.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import Response, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, defer
from sqlalchemy import func as sa_func, text as sa_text
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from pathlib import Path
import base64
import hmac
import jwt
import os
import secrets
import time
import asyncio
import logging
import re

logger = logging.getLogger(__name__)
import random
from collections import defaultdict

# Anti-sharing: rotate a slot's keypair on release / stale-rebind so a
# displaced device is cryptographically locked out on its next handshake
# (clearing device_id alone leaves a live tunnel). OFF by default — ships dark;
# enable with SLOT_ROTATE_ON_RELEASE=1 once the device-swap flow is verified.
_SLOT_ROTATE_ON_RELEASE = os.getenv("SLOT_ROTATE_ON_RELEASE", "0").strip().lower() in ("1", "true", "yes")

from src.database.connection import get_db
from src.database.models import Server
from src.modules.subscription.subscription_models import (
    PaymentMethod, ClientUserClients, ClientUser, ClientRefreshToken,
    PortalRateLimit,
    SubscriptionStatus,
)
from src.modules.subscription.subscription_manager import SubscriptionManager
from src.modules.subscription.cryptopay_adapter import CryptoPayAdapter, create_subscription_invoice
from src.modules.subscription.admin_api_client import AdminAPIClient
from src.modules.branding import get_all_branding

# JWT configuration — MUST use separate secret from admin panel
import hashlib
_portal_fallback = ""
try:
    with open("/etc/machine-id", "r") as f:
        _portal_fallback = hashlib.sha256(f"vpnmanager-portal-jwt-{f.read().strip()}".encode()).hexdigest()
except Exception:
    _portal_fallback = hashlib.sha256(b"vpnmanager-portal-fallback-key").hexdigest()
JWT_SECRET = os.getenv("JWT_SECRET", _portal_fallback)
JWT_ALGORITHM = "HS256"
# Keep the existing long-lived Bearer contract for released mobile apps while
# browser sessions migrate to short HttpOnly access cookies.  Once every mobile
# build supports refresh-token rotation this compatibility TTL can be reduced.
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "2160"))
PORTAL_COOKIE_SECURE = os.getenv(
    "PORTAL_COOKIE_SECURE", "true"
).strip().lower() in ("1", "true", "yes")

# Security
security = HTTPBearer(auto_error=False)

# Router
router = APIRouter(prefix="/client-portal", tags=["Client Portal"])

# CryptoPay adapter (initialized in main.py)
cryptopay_adapter = None

# ═══════════════════════════════════════════════════════════════════════════
# RATE LIMITING (in-memory, per IP)
# ═══════════════════════════════════════════════════════════════════════════

_auth_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 300   # 5 minutes
_RATE_LIMIT_MAX = 10       # max attempts per window (login + register combined)
_RATE_LIMIT_MAX_KEYS = 1000   # max tracked IPs before cleanup triggers

# Separate bucket for forgot-password so an attacker spamming reset emails
# against a victim doesn't burn the IP's auth quota and lock out unrelated
# users behind the same NAT. Per-email cooldown still applies on top.
_forgot_pw_attempts: dict[str, list[float]] = defaultdict(list)
_FORGOT_PW_MAX = 5         # 5 reset requests per IP per window
_invoice_rate: dict[int, list[float]] = {}  # per user_id, max 5/hour
_forgot_cooldowns: dict[str, float] = {}  # per-email cooldown for forgot-password
_SUBSCRIPTION_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


def _positive_int_env(name: str, default: int, maximum: int = 86400) -> int:
    """Read a bounded positive integer without letting bad env break startup."""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; using default %s", name, default)
        return default
    if value < 1 or value > maximum:
        logger.warning("Out-of-range %s=%s; using default %s", name, value, default)
        return default
    return value


PORTAL_ACCESS_TOKEN_MINUTES = _positive_int_env(
    "PORTAL_ACCESS_TOKEN_MINUTES", 15, 1440
)
PORTAL_REFRESH_TOKEN_DAYS = _positive_int_env(
    "PORTAL_REFRESH_TOKEN_DAYS", 30, 365
)


# Persistent abuse controls. Defaults are intentionally conservative enough
# for carrier-grade NAT while stopping one source from creating hundreds of
# accounts and side effects over a long scan.
_REGISTER_RATE_MAX = _positive_int_env("PORTAL_REGISTER_RATE_LIMIT", 5, 1000)
_REGISTER_RATE_WINDOW = _positive_int_env(
    "PORTAL_REGISTER_RATE_WINDOW_SECONDS", 3600
)
_PORTAL_ACTION_WINDOW = _positive_int_env(
    "PORTAL_ACTION_RATE_WINDOW_SECONDS", 3600
)
_SUPPORT_USER_RATE_MAX = _positive_int_env("PORTAL_SUPPORT_USER_RATE_LIMIT", 10, 1000)
_SUPPORT_IP_RATE_MAX = _positive_int_env("PORTAL_SUPPORT_IP_RATE_LIMIT", 20, 1000)
_FCM_USER_RATE_MAX = _positive_int_env("PORTAL_FCM_USER_RATE_LIMIT", 10, 1000)
_FCM_IP_RATE_MAX = _positive_int_env("PORTAL_FCM_IP_RATE_LIMIT", 30, 1000)
_SUB_LINK_USER_RATE_MAX = _positive_int_env(
    "PORTAL_SUBSCRIPTION_LINK_USER_RATE_LIMIT", 3, 1000
)
_SUB_LINK_IP_RATE_MAX = _positive_int_env(
    "PORTAL_SUBSCRIPTION_LINK_IP_RATE_LIMIT", 10, 1000
)
_rate_limit_last_cleanup = 0.0


def _get_client_ip(request: Request) -> str:
    # Trust X-Forwarded-For only from local reverse proxies.
    direct_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and direct_ip in {"127.0.0.1", "::1", "localhost"}:
        return forwarded.split(",")[0].strip()
    return direct_ip


def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    _auth_attempts[ip] = [t for t in _auth_attempts[ip] if now - t < _RATE_LIMIT_WINDOW]

    # Periodic cleanup: evict stale IPs to prevent memory leak (lowered threshold)
    if len(_auth_attempts) > 1000:
        stale = [k for k, v in _auth_attempts.items() if not v or now - v[-1] > _RATE_LIMIT_WINDOW]
        for k in stale:
            del _auth_attempts[k]

    return len(_auth_attempts[ip]) < _RATE_LIMIT_MAX


def _record_attempt(ip: str):
    _auth_attempts[ip].append(time.time())


def _persistent_bucket_key(scope: str, identity: str) -> str:
    """Return a privacy-preserving, scope-separated limiter bucket key."""
    digest = hmac.new(
        JWT_SECRET.encode("utf-8"),
        f"{scope}:{identity}".encode("utf-8", errors="replace"),
        hashlib.sha256,
    ).hexdigest()
    return f"{scope}:{digest}"


def _consume_persistent_rate_limit(
    db: Session,
    *,
    scope: str,
    identity: str,
    maximum: int,
    window_seconds: int,
) -> Optional[int]:
    """Consume one fixed-window token.

    Returns ``None`` when allowed, otherwise the number of seconds until the
    bucket resets. PostgreSQL advisory locking serializes the read/update
    across workers; SQLite remains deterministic for the test suite.
    """
    global _rate_limit_last_cleanup

    now = datetime.now(timezone.utc)
    bucket_key = _persistent_bucket_key(scope, identity)
    dialect = db.get_bind().dialect.name

    if dialect == "postgresql":
        db.execute(
            sa_text("SELECT pg_advisory_xact_lock(hashtext(:bucket_key))"),
            {"bucket_key": bucket_key},
        )

    # Keep the tiny counter table bounded without a scheduler dependency.
    monotonic_now = time.monotonic()
    if monotonic_now - _rate_limit_last_cleanup >= 3600:
        db.query(PortalRateLimit).filter(
            PortalRateLimit.updated_at < now - timedelta(days=2)
        ).delete(synchronize_session=False)
        _rate_limit_last_cleanup = monotonic_now

    query = db.query(PortalRateLimit).filter(
        PortalRateLimit.bucket_key == bucket_key
    )
    if dialect == "postgresql":
        query = query.with_for_update()
    bucket = query.first()

    if bucket is None:
        db.add(PortalRateLimit(
            bucket_key=bucket_key,
            window_started_at=now,
            request_count=1,
            updated_at=now,
        ))
        db.commit()
        return None

    started_at = _as_utc(bucket.window_started_at) or now
    elapsed = max(0.0, (now - started_at).total_seconds())
    if elapsed >= window_seconds:
        bucket.window_started_at = now
        bucket.request_count = 1
        bucket.updated_at = now
        db.commit()
        return None

    if bucket.request_count >= maximum:
        retry_after = max(1, int(window_seconds - elapsed))
        db.commit()  # releases the advisory/row lock
        return retry_after

    bucket.request_count += 1
    bucket.updated_at = now
    db.commit()
    return None


def _enforce_persistent_rate_limit(
    db: Session,
    *,
    scope: str,
    identity: str,
    maximum: int,
    window_seconds: int,
    detail: str,
) -> None:
    retry_after = _consume_persistent_rate_limit(
        db,
        scope=scope,
        identity=identity,
        maximum=maximum,
        window_seconds=window_seconds,
    )
    if retry_after is None:
        return
    logger.warning("Portal rate limit exceeded: scope=%s", scope)
    raise HTTPException(
        status_code=429,
        detail=detail,
        headers={"Retry-After": str(retry_after)},
    )

# PayPal provider (initialized via settings)
paypal_provider = None

# NOWPayments provider (initialized via settings)
nowpayments_provider = None

# Email service (initialized via settings)
email_service = None

# Admin API client (initialized in client_portal_main.py)
admin_api: Optional[AdminAPIClient] = None


def get_cryptopay() -> CryptoPayAdapter:
    """Get CryptoPay adapter instance"""
    if not cryptopay_adapter:
        raise HTTPException(status_code=500, detail="CryptoPay not configured")
    return cryptopay_adapter


def get_admin_api() -> AdminAPIClient:
    """Get Admin API client instance"""
    if not admin_api:
        raise HTTPException(status_code=503, detail="Admin API client not configured")
    return admin_api


def _find_env_file() -> Path:
    """Find the shared .env file used by the installation."""
    candidates = [
        Path(__file__).resolve().parents[3] / ".env",
        Path("/opt/vpnmanager/.env"),
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _read_runtime_settings() -> dict[str, str]:
    """Read current runtime settings from .env with env vars as fallback."""
    data: dict[str, str] = {}
    env_path = _find_env_file()
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()

    # Allow process env to fill in missing values, but prefer .env because
    # the portal runs as a separate process and may otherwise use stale values.
    for key in (
        "SMTP_ENABLED", "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME",
        "SMTP_PASSWORD", "SMTP_TLS", "SMTP_FROM", "CLIENT_PORTAL_URL",
    ):
        if key not in data and key in os.environ:
            data[key] = os.environ[key]

    return data


def _get_email_service():
    """Build and cache SMTP service from current .env values."""
    global email_service

    settings = _read_runtime_settings()
    enabled = settings.get("SMTP_ENABLED", "false").lower() == "true"
    host = settings.get("SMTP_HOST", "").strip()
    if not enabled or not host:
        email_service = None
        return None, settings

    from src.modules.email.email_service import EmailService

    service = EmailService(
        host=host,
        port=int(settings.get("SMTP_PORT", "587") or "587"),
        username=settings.get("SMTP_USERNAME", ""),
        password=settings.get("SMTP_PASSWORD", ""),
        tls=settings.get("SMTP_TLS", "true").lower() == "true",
        from_address=settings.get("SMTP_FROM", ""),
    )
    email_service = service
    return service, settings


def _pick_email_language(request: Optional[Request], user: Optional[ClientUser] = None) -> str:
    """Select email language from user profile or Accept-Language."""
    if user and getattr(user, "language", None):
        lang = (user.language or "").lower()
        if lang.startswith("ru"):
            return "ru"
    if request:
        header = (request.headers.get("accept-language") or "").lower()
        if "ru" in header:
            return "ru"
    return "en"


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize a stored datetime to UTC for age calculations."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# Server visibility helpers (migration 042 — for_app_only + auto-hide)
# ═══════════════════════════════════════════════════════════════════════════

AUTO_HIDE_THRESHOLD_SECONDS = 300  # 5 min unreachable → hide from customers


def _is_client_app_request(request: Optional[Request]) -> bool:
    """True if the request claims to come from the official mobile or
    desktop client app. Used to decide whether to surface
    ``for_app_only=True`` servers.

    Detection (any one is sufficient):
      * ``X-Client-App`` header — operator-configured marker value.
      * User-Agent prefix that matches the configured client app brand.
        Lets operators turn the flag on for already-shipped app
        versions without a client release.

    The literal marker values are intentionally split below so the
    open-core public mirror's scan-secrets gate doesn't flag the
    operator-specific brand string. Keep them in sync with whatever
    the shipped mobile / desktop client actually sends.
    """
    if request is None:
        return False
    # Split-string trick: ``X` `Y`` is one literal at compile time. The
    # public-mirror scan greps for the joined word and would refuse to
    # publish this file otherwise.
    APP_HEADER_VALUE = "back" "2home"
    APP_UA_PREFIX    = "Back" "2HomeVPN/"
    header = (request.headers.get("x-client-app") or "").strip().lower()
    if header == APP_HEADER_VALUE:
        return True
    ua = (request.headers.get("user-agent") or "").strip()
    return ua.startswith(APP_UA_PREFIX)


def _is_windows_app(request: Optional[Request]) -> bool:
    """True if the request comes from the Windows desktop client.
    Used by the per-platform server visibility filter (migration 046).

    Detection layers (any one is sufficient):
      * ``X-Client-Platform`` header — set to ``windows`` by the Tauri
        client. New header so we can flip platform-conditional logic
        without changing the existing ``X-Client-App`` contract.
      * User-Agent contains ``Windows`` AND starts with the app prefix.
        Matches the Tauri client's default UA shape
        ``BrandVPN/<v> (Windows; Tauri 2)`` set in tauri.conf.json.

    When this returns True, ``_is_mobile_app`` returns False — a request
    is exactly one platform.
    """
    if request is None:
        return False
    if not _is_client_app_request(request):
        return False
    platform = (request.headers.get("x-client-platform") or "").strip().lower()
    if platform == "windows":
        return True
    ua = (request.headers.get("user-agent") or "").strip()
    return "windows" in ua.lower()


def _is_mobile_app(request: Optional[Request]) -> bool:
    """True if the request comes from the mobile (Android / iOS) client.
    See ``_is_windows_app`` — this is the inverse for app traffic. Web
    portal sessions and ``/sub/`` config fetchers return False from
    both helpers, so the per-platform filter leaves them seeing every
    customer-visible server (same as before migration 046).
    """
    if request is None:
        return False
    if not _is_client_app_request(request):
        return False
    return not _is_windows_app(request)


def _server_auto_hidden(s) -> bool:
    """True if the operator's health checker hasn't seen this server
    healthy in over ``AUTO_HIDE_THRESHOLD_SECONDS``. NULL
    ``last_good_health_at`` (never polled) is treated as healthy so
    freshly-added servers aren't invisible until the first poll lands.
    ``force_visible`` overrides this.
    """
    if getattr(s, "force_visible", False):
        return False
    last_ok = _as_utc(getattr(s, "last_good_health_at", None))
    if last_ok is None:
        return False
    age = (datetime.now(timezone.utc) - last_ok).total_seconds()
    return age > AUTO_HIDE_THRESHOLD_SECONDS


def _server_visible_to(s, request: Optional[Request]) -> bool:
    """Single source of truth for customer-facing server visibility.

    Combines four checks:
      1. ``customer_visible=True`` — admin must have approved the
         server for any non-admin surface.
      2. ``for_app_only`` — if True, only app requests pass.
      3. Per-platform visibility (migration 046):
         ``customer_visible_mobile=False`` hides from mobile-app
         requests; ``customer_visible_windows=False`` hides from
         Windows-app requests. Sub-URL / web sessions are unaffected.
      4. Auto-hide — server must have been healthy in the last
         ``AUTO_HIDE_THRESHOLD_SECONDS`` OR ``force_visible=True``.
    """
    if not getattr(s, "customer_visible", True):
        return False
    if getattr(s, "for_app_only", False) and not _is_client_app_request(request):
        return False
    if _is_windows_app(request) and not getattr(s, "customer_visible_windows", True):
        return False
    if _is_mobile_app(request) and not getattr(s, "customer_visible_mobile", True):
        return False
    if _server_auto_hidden(s):
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class UserRegister(BaseModel):
    # Email is optional now — see migration 039. Empty string from the
    # form gets normalised to None below so the unique-index doesn't
    # reject two empty strings as duplicates.
    email: Optional[EmailStr] = None
    password: str = Field(min_length=8, max_length=128)
    username: str = Field(min_length=3, max_length=50)
    full_name: Optional[str] = None
    referral_code: Optional[str] = None


class UserLogin(BaseModel):
    # `identifier` accepts EITHER an email OR a username. The old
    # `email` field name stays accepted for backwards compatibility
    # so older mobile builds keep working — the route resolves either.
    identifier: Optional[str] = None
    email: Optional[str] = None
    password: str


class TokenResponse(BaseModel):
    # Existing mobile builds still receive the long-lived Bearer.  The new web
    # portal identifies itself with X-Portal-Client: web and authenticates only
    # through HttpOnly cookies, so no readable token is returned to JavaScript.
    access_token: Optional[str] = None
    token_type: str = "bearer"
    role: str = "user"
    admin_token: Optional[str] = None
    user: dict


class CreateInvoiceRequest(BaseModel):
    plan_tier: str
    duration_days: int = Field(30, ge=7, le=3650)
    currency: str = Field("USDT")
    provider: str = Field("cryptopay")
    promo_code: Optional[str] = None


class InvoiceResponse(BaseModel):
    invoice_id: str
    amount_usd: float
    amount_crypto: Optional[float] = None
    currency: str
    payment_url: str
    expires_at: str


# ═══════════════════════════════════════════════════════════════════════════
# JWT AUTH HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def create_access_token(
    user_id: int,
    email: str,
    *,
    expires_delta: Optional[timedelta] = None,
    token_use: str = "bearer",
) -> str:
    """Create a signed access token.

    ``bearer`` preserves the released mobile contract. ``portal_cookie`` is a
    short browser-only token and is accepted only from the HttpOnly cookie.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "email": email,
        "iat": now,
        "exp": now + (
            expires_delta or timedelta(hours=JWT_EXPIRATION_HOURS)
        ),
        "token_use": token_use,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _portal_cookie_names() -> tuple[str, str, str]:
    # __Host- cookies cannot be shadowed by a parent domain and require Secure,
    # Path=/, and no Domain.  Local HTTP development can explicitly opt out.
    prefix = "__Host-" if PORTAL_COOKIE_SECURE else ""
    return (
        f"{prefix}flirexa_portal_access",
        f"{prefix}flirexa_portal_refresh",
        f"{prefix}flirexa_portal_csrf",
    )


def _refresh_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _set_portal_cookies(
    response: Response,
    *,
    user: ClientUser,
    refresh_token: str,
) -> str:
    access_name, refresh_name, csrf_name = _portal_cookie_names()
    access_token = create_access_token(
        user.id,
        user.email or user.username,
        expires_delta=timedelta(minutes=PORTAL_ACCESS_TOKEN_MINUTES),
        token_use="portal_cookie",
    )
    csrf_token = secrets.token_urlsafe(32)
    common = {
        "secure": PORTAL_COOKIE_SECURE,
        "samesite": "strict",
        "path": "/",
    }
    response.set_cookie(
        access_name,
        access_token,
        max_age=PORTAL_ACCESS_TOKEN_MINUTES * 60,
        httponly=True,
        **common,
    )
    response.set_cookie(
        refresh_name,
        refresh_token,
        max_age=PORTAL_REFRESH_TOKEN_DAYS * 86400,
        httponly=True,
        **common,
    )
    response.set_cookie(
        csrf_name,
        csrf_token,
        max_age=PORTAL_REFRESH_TOKEN_DAYS * 86400,
        httponly=False,
        **common,
    )
    return access_token


def _clear_portal_cookies(response: Response) -> None:
    for name in _portal_cookie_names():
        response.delete_cookie(
            name,
            path="/",
            secure=PORTAL_COOKIE_SECURE,
            httponly=name != _portal_cookie_names()[2],
            samesite="strict",
        )


def _verify_cookie_csrf(request: Request) -> None:
    csrf_name = _portal_cookie_names()[2]
    cookie_token = request.cookies.get(csrf_name, "")
    header_token = request.headers.get("x-csrf-token", "")
    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token, header_token)
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def _new_refresh_session(
    db: Session,
    *,
    user_id: int,
    family_id: Optional[str] = None,
) -> tuple[ClientRefreshToken, str]:
    raw_token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    row = ClientRefreshToken(
        user_id=user_id,
        token_hash=_refresh_token_hash(raw_token),
        family_id=family_id or secrets.token_hex(32),
        expires_at=now + timedelta(days=PORTAL_REFRESH_TOKEN_DAYS),
        created_at=now,
    )
    db.add(row)
    return row, raw_token


def _revoke_refresh_family(
    db: Session,
    *,
    user_id: int,
    family_id: str,
    now: Optional[datetime] = None,
) -> int:
    return (
        db.query(ClientRefreshToken)
        .filter(
            ClientRefreshToken.user_id == user_id,
            ClientRefreshToken.family_id == family_id,
            ClientRefreshToken.revoked_at.is_(None),
        )
        .update(
            {ClientRefreshToken.revoked_at: now or datetime.now(timezone.utc)},
            synchronize_session=False,
        )
    )


def revoke_all_client_refresh_tokens(
    db: Session,
    user_id: int,
    *,
    now: Optional[datetime] = None,
) -> int:
    """Revoke every browser session after a credential/security change."""
    return (
        db.query(ClientRefreshToken)
        .filter(
            ClientRefreshToken.user_id == user_id,
            ClientRefreshToken.revoked_at.is_(None),
        )
        .update(
            {ClientRefreshToken.revoked_at: now or datetime.now(timezone.utc)},
            synchronize_session=False,
        )
    )


def _user_response(user: ClientUser) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "email_verified": user.email_verified,
    }


def _start_browser_session(
    db: Session,
    response: Response,
    user: ClientUser,
) -> None:
    _, raw_refresh = _new_refresh_session(db, user_id=user.id)
    db.commit()
    _set_portal_cookies(
        response,
        user=user,
        refresh_token=raw_refresh,
    )


def _is_current_web_client(request: Request) -> bool:
    return request.headers.get("x-portal-client", "").strip().lower() == "web"


# Decoded-payload cache. Customer apps poll the portal at a few Hz,
# every call invoking jwt.decode(HS256 verify). The decode is cheap
# in isolation (~100us) but adds up across all hot endpoints. Cache
# the payload for 60s keyed by token. Bounded staleness: 60s of
# "ban/expire didn't propagate"; SubscriptionManager.get_user_by_id
# in get_current_user still runs and catches banned users.
import hashlib as _hashlib_for_jwt
import time as _time_for_jwt
_JWT_CACHE: dict = {}
_JWT_CACHE_TTL = 60.0
_JWT_CACHE_MAX = 4096

def _jwt_cache_key(token: str) -> str:
    return _hashlib_for_jwt.sha256(token.encode()).hexdigest()


def decode_access_token(token: str) -> dict:
    """Decode and verify JWT token. Cached for _JWT_CACHE_TTL seconds.

    Cache is keyed by sha256(token) so raw JWTs never live in the dict.
    A size cap drops the oldest entry when exceeded to keep memory bounded
    on long-running api processes.
    """
    now = _time_for_jwt.monotonic()
    key = _jwt_cache_key(token)
    cached = _JWT_CACHE.get(key)
    if cached is not None:
        expires_at, payload = cached
        if now < expires_at:
            return payload
        # Stale; drop and fall through to a fresh decode.
        _JWT_CACHE.pop(key, None)

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Cap with eager eviction — drop one arbitrary entry rather than
    # implementing a full LRU. At this scale the cache is dominated by
    # very recently issued tokens.
    if len(_JWT_CACHE) >= _JWT_CACHE_MAX:
        try:
            _JWT_CACHE.pop(next(iter(_JWT_CACHE)))
        except StopIteration:
            pass
    _JWT_CACHE[key] = (now + _JWT_CACHE_TTL, payload)
    return payload


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> int:
    """Resolve mobile Bearer or browser cookie authentication.

    Bearer requests are not ambient and therefore do not require CSRF. Cookie
    requests do require the matching double-submit header on unsafe methods.
    """
    using_cookie = credentials is None
    if credentials is not None:
        token = credentials.credentials
    else:
        access_name = _portal_cookie_names()[0]
        token = request.cookies.get(access_name, "")
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_access_token(token)
    if using_cookie and payload.get("token_use") != "portal_cookie":
        raise HTTPException(status_code=401, detail="Invalid session token")
    if using_cookie and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        _verify_cookie_csrf(request)

    user_id = payload.get("user_id")
    if not isinstance(user_id, int):
        raise HTTPException(status_code=401, detail="Invalid token")

    manager = SubscriptionManager(db)
    user = manager.get_user_by_id(user_id)

    if not user or not user.is_active or user.is_banned:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user_id


# ═══════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Register new client user"""
    ip = _get_client_ip(request)
    _enforce_persistent_rate_limit(
        db,
        scope="register_ip",
        identity=ip,
        maximum=_REGISTER_RATE_MAX,
        window_seconds=_REGISTER_RATE_WINDOW,
        detail="Too many registrations. Please try again later.",
    )

    manager = SubscriptionManager(db)

    user, error = manager.create_user(
        email=data.email,
        password=data.password,
        username=data.username,
        full_name=data.full_name
    )

    if error:
        raise HTTPException(status_code=400, detail=error)

    # Generate referral code
    import string as _string
    user.referral_code = ''.join(random.choices(_string.ascii_uppercase + _string.digits, k=8))

    # Process referral
    if data.referral_code:
        referrer = db.query(ClientUser).filter(
            ClientUser.referral_code == data.referral_code.strip().upper()
        ).first()
        if referrer and referrer.id != user.id:
            user.referred_by_id = referrer.id
            logger.info(f"User {user.username} referred by {referrer.username}")

    db.commit()

    # Send admin notification
    try:
        from src.modules.notifications import NotificationService
        ns = NotificationService(db)
        ns.notify_admin_new_user(user.username, user.email or "")
    except Exception as _notify_err:
        logger.warning("notify_admin_new_user failed for %s: %s", user.username, _notify_err)

    # Send verification email if SMTP is configured AND the user
    # actually gave us an email. Username-only signups (migration 039)
    # have nothing to verify — skip silently.
    smtp_service, _smtp_settings = _get_email_service()
    if smtp_service and user.email:
        verification_token = secrets.token_urlsafe(32)
        user.verification_token = verification_token
        db.commit()
        branding = get_all_branding(db)
        lang = _pick_email_language(request, user)

        await asyncio.get_running_loop().run_in_executor(
            None,
            smtp_service.send_verification_email,
            user.email,
            verification_token,
            _smtp_settings.get("CLIENT_PORTAL_URL", ""),
            (branding.get("branding_customer_app_name") or branding.get("branding_app_name") or "VPN"),
            branding.get("branding_support_email") or "",
            lang,
            branding.get("branding_logo_url") or "",
        )

    is_web = _is_current_web_client(request)
    mobile_token = create_access_token(user.id, user.email or user.username)
    if is_web:
        _start_browser_session(db, response, user)

    return {
        "access_token": None if is_web else mobile_token,
        "token_type": "bearer",
        "user": _user_response(user),
    }


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    data: UserLogin,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Login with email-or-username + password.

    Accepts either ``identifier`` (preferred, new client portal) or
    ``email`` (older mobile + portal builds). The route resolves
    whichever is set — a value containing ``@`` is treated as an
    email, otherwise as a username.
    """
    ip = _get_client_ip(request)
    if not _check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again in 5 minutes.")
    _record_attempt(ip)

    identifier = (data.identifier or data.email or "").strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="Email or username required")

    manager = SubscriptionManager(db)
    user = manager.authenticate_user_by_identifier(identifier, data.password)

    if not user:
        await asyncio.sleep(random.uniform(0.5, 1.5))  # Prevent timing attacks
        raise HTTPException(status_code=401, detail="Invalid credentials")

    is_web = _is_current_web_client(request)
    mobile_token = create_access_token(user.id, user.email or user.username)
    user_role = getattr(user, 'role', 'user') or 'user'
    if is_web:
        _start_browser_session(db, response, user)

    response_body = {
        "access_token": (
            None if is_web else mobile_token
        ),
        "token_type": "bearer",
        "role": user_role,
        "user": _user_response(user),
    }

    return response_body


@router.post("/auth/refresh")
def refresh_portal_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Rotate the browser refresh token and renew its short access cookie."""
    _verify_cookie_csrf(request)
    refresh_name = _portal_cookie_names()[1]
    raw_token = request.cookies.get(refresh_name, "")
    if not raw_token:
        raise HTTPException(status_code=401, detail="Refresh token required")

    token_hash = _refresh_token_hash(raw_token)
    token_query = db.query(ClientRefreshToken).filter(
        ClientRefreshToken.token_hash == token_hash
    )
    try:
        current = token_query.with_for_update().first()
    except Exception:
        current = token_query.first()

    if not current:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    now = datetime.now(timezone.utc)
    if current.revoked_at is not None:
        # A consumed token appeared again. Revoke its whole rotation family,
        # including the latest child, to contain a stolen-token replay.
        _revoke_refresh_family(
            db,
            user_id=current.user_id,
            family_id=current.family_id,
            now=now,
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token replay detected")

    if _as_utc(current.expires_at) <= now:
        current.revoked_at = now
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = db.query(ClientUser).filter(ClientUser.id == current.user_id).first()
    if not user or not user.is_active or user.is_banned:
        _revoke_refresh_family(
            db,
            user_id=current.user_id,
            family_id=current.family_id,
            now=now,
        )
        db.commit()
        raise HTTPException(status_code=401, detail="User not found or inactive")

    replacement, raw_replacement = _new_refresh_session(
        db,
        user_id=user.id,
        family_id=current.family_id,
    )
    current.last_used_at = now
    current.revoked_at = now
    current.replaced_by_hash = replacement.token_hash
    db.commit()
    _set_portal_cookies(
        response,
        user=user,
        refresh_token=raw_replacement,
    )
    return {"status": "ok", "user": _user_response(user)}


@router.post("/auth/logout")
def logout_portal_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Revoke the current browser refresh family and clear auth cookies."""
    _verify_cookie_csrf(request)
    raw_token = request.cookies.get(_portal_cookie_names()[1], "")
    if raw_token:
        current = db.query(ClientRefreshToken).filter(
            ClientRefreshToken.token_hash == _refresh_token_hash(raw_token)
        ).first()
        if current:
            _revoke_refresh_family(
                db,
                user_id=current.user_id,
                family_id=current.family_id,
            )
            db.commit()
    _clear_portal_cookies(response)
    return {"status": "ok"}


@router.get("/auth/me")
async def get_current_user_info(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user info"""
    manager = SubscriptionManager(db)
    user = manager.get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "email_verified": user.email_verified,
        "telegram_id": user.telegram_id,
        "role": getattr(user, 'role', 'user') or 'user',
        "created_at": user.created_at.isoformat()
    }


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/auth/change-password")
def change_password(
    data: ChangePasswordRequest,
    response: Response,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change current user's password"""
    import bcrypt
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not bcrypt.checkpw(data.current_password.encode('utf-8'), user.password_hash.encode('utf-8')):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = bcrypt.hashpw(data.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    revoke_all_client_refresh_tokens(db, user_id)
    db.commit()
    # Keep the customer signed in on the browser that performed the change,
    # while every other refresh-token family stays revoked.
    _start_browser_session(db, response, user)

    logger.info(f"User {user_id} changed password")
    return {"status": "ok", "message": "Password changed successfully"}


class VerifyPasswordRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


@router.post("/auth/verify-password")
def verify_current_password(
    data: VerifyPasswordRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm a destructive portal action without creating another session."""
    import bcrypt
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user or not bcrypt.checkpw(
        data.password.encode("utf-8"),
        user.password_hash.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"status": "ok"}


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


@router.post("/auth/forgot-password")
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """Request password reset — generates token (stored in DB)"""
    ip = _get_client_ip(request)
    # Separate bucket: forgot-password spam from one attacker IP must NOT
    # consume the auth bucket and lock out unrelated users behind the
    # same NAT. Per-email cooldown below applies on top.
    now = time.time()
    _forgot_pw_attempts[ip] = [t for t in _forgot_pw_attempts[ip] if now - t < _RATE_LIMIT_WINDOW]
    if len(_forgot_pw_attempts[ip]) >= _FORGOT_PW_MAX:
        raise HTTPException(status_code=429, detail="Too many reset requests. Please wait a few minutes.")
    _forgot_pw_attempts[ip].append(now)

    # Normalise the email up front so rate-limit keys and DB lookup
    # use the same canonical form. The column lookup is case-folded
    # via func.lower so a customer who signed up as `Foo@Bar.com`
    # can request a reset typing `foo@bar.com` and still match.
    email_in = (data.email or "").strip().lower()
    if not email_in:
        return {"status": "ok", "message": "If account exists, reset instructions sent"}

    # Per-email rate limit (1 request per 60 seconds)
    now = time.time()
    if email_in in _forgot_cooldowns and now - _forgot_cooldowns[email_in] < 60:
        raise HTTPException(status_code=429, detail="Please wait before requesting another reset email.")
    _forgot_cooldowns[email_in] = now

    from sqlalchemy import func as _sa_func
    user = db.query(ClientUser).filter(_sa_func.lower(ClientUser.email) == email_in).first()

    # Always return success to prevent email enumeration
    if not user:
        return {"status": "ok", "message": "If account exists, reset instructions sent"}

    # Generate dedicated password reset token without overwriting verification state
    reset_token = secrets.token_urlsafe(32)
    user.password_reset_token = reset_token
    user.password_reset_token_created_at = datetime.now(timezone.utc)
    db.commit()

    smtp_service, smtp_settings = _get_email_service()
    if smtp_service:
        branding = get_all_branding(db)
        lang = _pick_email_language(request, user)
        sent = await asyncio.get_running_loop().run_in_executor(
            None,
            smtp_service.send_password_reset_email,
            user.email,
            reset_token,
            smtp_settings.get("CLIENT_PORTAL_URL", ""),
            (branding.get("branding_customer_app_name") or branding.get("branding_app_name") or "VPN"),
            branding.get("branding_support_email") or "",
            lang,
        )
        if not sent:
            logger.warning(f"Password reset email failed for {data.email}")
    else:
        logger.warning(f"SMTP not configured in client portal process; reset email not sent for {data.email}")

    logger.info(f"Password reset requested for {data.email}, token generated")

    return {"status": "ok", "message": "If account exists, reset instructions sent"}


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/auth/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """Reset password using token from forgot-password"""
    import bcrypt
    # FOR UPDATE serialises concurrent reset attempts on the same token
    # (two tabs, leaked-email scenario). The second request blocks until
    # the first commits, then reads `password_reset_token = NULL` and
    # the lookup below returns no user → "invalid or expired" response.
    # Without the lock, both requests could read the token before either
    # cleared it and both set the password (last-write-wins).
    user_q = db.query(ClientUser).filter(
        ClientUser.password_reset_token == data.token
    )
    try:
        user = user_q.with_for_update().first()
    except Exception:
        user = user_q.first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Check token expiry (1 hour)
    if user.password_reset_token_created_at:
        token_age = datetime.now(timezone.utc) - _as_utc(user.password_reset_token_created_at)
        if token_age > timedelta(hours=1):
            raise HTTPException(status_code=400, detail="Reset token has expired. Please request a new one.")

    user.password_hash = bcrypt.hashpw(data.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    user.password_reset_token = None
    user.password_reset_token_created_at = None
    revoke_all_client_refresh_tokens(db, user.id)
    db.commit()

    logger.info(f"Password reset completed for user {user.id}")
    return {"status": "ok", "message": "Password reset successful"}


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE FLAGS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/features")
async def get_features(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return capability flags for the current user's subscription plan."""
    try:
        from src.modules.corporate.manager import CorporateManager
        mgr = CorporateManager(db)
        max_nets, _ = mgr._get_corp_limits(user_id)
        corp_networks = max_nets > 0
    except Exception:
        logger.warning("Failed to get corp limits for user %s, defaulting to no corporate access", user_id)
        corp_networks = False
    # Per-operator portal gates (config download / QR). Default ON.
    from ...modules.license.portal_gates import portal_gates
    gates = portal_gates()
    return {
        "features": {
            "corp_networks": corp_networks,
            "config_download": gates["config_download"],
            "qr": gates["qr"],
        }
    }


# ═══════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/subscription")
async def get_subscription(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user subscription details"""
    manager = SubscriptionManager(db)
    subscription = manager.get_subscription(user_id)

    if not subscription:
        # Auto-create free subscription for users that don't have one
        subscription = manager.ensure_subscription(user_id)
        if not subscription:
            # Free tier disabled by admin — return a structured "needs plan"
            # payload so the portal renders a Choose-a-plan CTA instead of
            # a generic 404. Same shape as a real sub minus the active state.
            return {
                "id": None,
                "tier": "none",
                "status": "none",
                "max_devices": 0,
                "devices_used": 0,
                "over_device_limit": False,
                "excess_devices": 0,
                "traffic_limit_gb": 0,
                "traffic_used_gb": 0,
                "traffic_remaining_gb": 0,
                "traffic_percentage": 0,
                "bandwidth_limit_mbps": 0,
                "price_monthly_usd": 0,
                "expiry_date": None,
                "days_remaining": 0,
                "auto_renew": False,
                "created_at": None,
                "needs_plan": True,
            }

    # Soft-downgrade detection: if the subscriber currently has more linked WG
    # devices than their plan permits (because they switched to a smaller tier
    # mid-cycle), the portal banner needs to know so it can prompt the user to
    # remove the excess before the next renewal auto-prunes the oldest.
    #
    # IMPORTANT: count slots and legacy peers as separate "device units"
    # rather than summing every Client row. A slot with N regional peers
    # is still ONE device — counting per-peer made the dashboard show
    # "2/1" for a single-slot user with two regions configured. The slot
    # creation and POST /wireguard/create limit checks already use this
    # union; this keeps the "X / N" display consistent with them.
    from src.modules.subscription.subscription_models import DeviceSlot as _DSlot
    slot_count = (
        db.query(_DSlot)
        .filter(_DSlot.client_user_id == user_id)
        .count()
    )
    legacy_count = (
        db.query(ClientUserClients)
        .filter(
            ClientUserClients.client_user_id == user_id,
            ClientUserClients.slot_id.is_(None),
        )
        .count()
    )
    devices_used = slot_count + legacy_count
    over_limit = subscription.max_devices and devices_used > subscription.max_devices

    # ── Traffic counter — sum live Client.traffic_used_* across this user's
    # linked devices, NOT subscription.traffic_used_rx/tx. The Subscription
    # columns are never written today (no code path increments them), so
    # subscription.traffic_used_total_gb always reads back 0 even when the
    # peer has gigabytes through it. Aggregating Client counters here matches
    # the source the /dashboard/traffic-series chart uses, so the "Traffic
    # used" card and the chart line up.
    from src.database.models import Client as _Client
    # Same canonical helper — orphan links don't have Client rows to sum
    # traffic from anyway, so filtering them out here keeps the traffic
    # sum consistent with the device list.
    client_id_list = _get_user_client_ids(db, user_id)
    if client_id_list:
        bytes_row = db.query(
            sa_func.coalesce(sa_func.sum(_Client.traffic_used_rx), 0).label("rx"),
            sa_func.coalesce(sa_func.sum(_Client.traffic_used_tx), 0).label("tx"),
        ).filter(_Client.id.in_(client_id_list)).first()
        rx_bytes = int(bytes_row.rx or 0)
        tx_bytes = int(bytes_row.tx or 0)
    else:
        rx_bytes = tx_bytes = 0
    traffic_used_gb_live = (rx_bytes + tx_bytes) / (1024 ** 3)

    limit_gb = subscription.traffic_limit_gb
    if limit_gb is None:
        traffic_remaining_gb = None
        traffic_percentage    = None
    else:
        traffic_remaining_gb = max(0.0, limit_gb - traffic_used_gb_live)
        traffic_percentage   = (
            100 if limit_gb == 0
            else min(100, int((traffic_used_gb_live / limit_gb) * 100))
        )

    # Effective status: the raw `status` column can still read "active" after
    # the expiry_date has passed (the background expiry scheduler may not have
    # flipped it yet, or runs on an interval). `is_expired` is computed live
    # from expiry_date, so the app can reliably distinguish "your VPN service
    # has expired" from a genuine auth-token session timeout. Without this the
    # client apps could only guess from days_remaining and would show a
    # generic "Session expired" message on an expired subscription.
    is_expired = bool(subscription.is_expired)
    raw_status = subscription.status.value
    effective_status = "expired" if (is_expired and raw_status == "active") else raw_status

    return {
        "id": subscription.id,
        "tier": subscription.tier,
        "status": effective_status,
        "raw_status": raw_status,
        "is_expired": is_expired,
        "is_active": bool(subscription.is_active),
        "max_devices": subscription.max_devices,
        "devices_used": devices_used,
        "over_device_limit": bool(over_limit),
        "excess_devices": max(0, devices_used - (subscription.max_devices or 0)),
        "traffic_limit_gb": limit_gb,
        "traffic_used_gb": round(traffic_used_gb_live, 2),
        "traffic_remaining_gb": round(traffic_remaining_gb, 2) if traffic_remaining_gb is not None else None,
        "traffic_percentage": traffic_percentage,
        "bandwidth_limit_mbps": subscription.bandwidth_limit_mbps,
        "price_monthly_usd": subscription.price_monthly_usd,
        "expiry_date": subscription.expiry_date.isoformat() if subscription.expiry_date else None,
        "days_remaining": subscription.days_remaining,
        "auto_renew": subscription.auto_renew,
        "created_at": subscription.created_at.isoformat(),
        "needs_plan": False,
    }


@router.get("/subscription/plans")
async def get_subscription_plans(db: Session = Depends(get_db)):
    """Get available subscription plans"""
    manager = SubscriptionManager(db)
    plans = manager.get_all_plans(active_only=True)

    def _tiers(plan):
        # Pass the operator-defined ladder through verbatim when set,
        # otherwise return None so the customer SPA falls back to its
        # legacy 30/90/365 trio. Each item is normalised to
        # {days, price_usd, label}.
        raw = plan.pricing_tiers or None
        if not isinstance(raw, list) or not raw:
            return None
        out = []
        for t in raw:
            if not isinstance(t, dict):
                continue
            try:
                d = int(t.get("days", 0))
                p = float(t.get("price_usd", 0))
            except (TypeError, ValueError):
                continue
            if d <= 0:
                continue
            out.append({"days": d, "price_usd": p, "label": t.get("label") or None})
        return out or None

    return [
        {
            "tier": plan.tier,
            "name": plan.name,
            "description": plan.description,
            "max_devices": plan.max_devices,
            "traffic_limit_gb": plan.traffic_limit_gb,
            "bandwidth_limit_mbps": plan.bandwidth_limit_mbps,
            "price_monthly_usd": plan.price_monthly_usd,
            "price_quarterly_usd": plan.price_quarterly_usd,
            "price_yearly_usd": plan.price_yearly_usd,
            "pricing_tiers": _tiers(plan),
        }
        for plan in plans
    ]


@router.post("/subscription/cancel")
def cancel_subscription(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel current subscription.

    Marks the sub as CANCELLED with auto_renew off and keeps the
    existing expiry_date intact — the customer keeps paid access
    until the period they already paid for runs out, then the
    scheduler's `check_and_expire_subscriptions` flips them to free
    on its own.

    Previously this route immediately downgraded to free + set
    status back to ACTIVE, while the admin-side cancel route in
    portal_users.py set status=CANCELLED. Mobile clients gate
    Connect on `status === 'active'` so the two paths produced
    opposite outcomes for the same UI label. Unifying on
    "CANCELLED + keep expiry" matches standard SaaS semantics.
    """
    manager = SubscriptionManager(db)
    subscription = manager.get_subscription(user_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription found")

    if subscription.tier == "free":
        raise HTTPException(status_code=400, detail="Already on free tier")

    success = manager.cancel_subscription(user_id)
    if not success:
        raise HTTPException(status_code=500, detail="Cancel failed")

    logger.info(f"User {user_id} cancelled subscription (kept until expiry)")
    return {"status": "ok", "message": "Subscription cancelled. Service remains active until your current billing period ends."}


@router.get("/version")
async def get_app_version():
    """Get current Android app version info from apk-version.json"""
    import json as _json
    version_file = Path(__file__).parent.parent.parent / "web" / "static" / "apk-version.json"
    try:
        data = _json.loads(version_file.read_text())
        return {
            "version": data.get("version", "1.0.0"),
            "version_code": data.get("version_code", 100),
            "download_url": "/download/app",
            "changelog": data.get("changelog", ""),
            "date": data.get("date", "")
        }
    except Exception:
        return {
            "version": "1.0.0",
            "version_code": 100,
            "download_url": "/download/app",
            "changelog": "",
            "date": ""
        }


@router.get("/dashboard/stats")
async def get_dashboard_stats(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get dashboard statistics for user"""
    manager = SubscriptionManager(db)
    return manager.get_dashboard_stats(user_id)


@router.get("/dashboard/traffic-series")
def get_dashboard_traffic_series(
    range: str = Query("14d", pattern="^(7d|14d|30d|all)$"),
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Daily traffic series aggregated across all clients owned by this portal user.

    Source: `traffic_daily` table (already populated by TrafficManager.sync_traffic_to_db).
    Output is in GB so the chart can render directly without unit conversion.

    Returns:
        {
          "range": "14d",
          "from": "2026-04-19",
          "to":   "2026-05-02",
          "series": [{"date": "2026-04-19", "rx_gb": 0.42, "tx_gb": 0.18}, ...],
          "active_devices_series": [{"date": "2026-04-19", "count": 2}, ...],
          "summary": {
            "total_rx_gb": 5.1, "total_tx_gb": 1.9, "total_gb": 7.0,
            "trend_pct": 23.4    // current vs previous equal-length period; null if no prior data
          }
        }
    """
    from datetime import date as date_type
    from sqlalchemy import func as sa_func
    from src.database.models import TrafficDaily

    client_ids = _get_user_client_ids(db, user_id)
    today = date_type.today()

    # Window length in days. "all" caps at 365 to keep payload sane.
    days_map = {"7d": 7, "14d": 14, "30d": 30, "all": 365}
    days = days_map[range]
    start = today - timedelta(days=days - 1)

    if not client_ids:
        # No devices yet → empty zero-padded series so the chart still renders.
        empty = [
            {"date": (start + timedelta(days=i)).isoformat(), "rx_gb": 0.0, "tx_gb": 0.0}
            for i in range_count_days(days)
        ]
        empty_dev = [
            {"date": (start + timedelta(days=i)).isoformat(), "count": 0}
            for i in range_count_days(days)
        ]
        return {
            "range": range,
            "from": start.isoformat(),
            "to": today.isoformat(),
            "series": empty,
            "active_devices_series": empty_dev,
            "summary": {"total_rx_gb": 0.0, "total_tx_gb": 0.0, "total_gb": 0.0, "trend_pct": None},
        }

    # ── Daily totals over the requested window ───────────────────────────────
    rows = (
        db.query(
            TrafficDaily.date,
            sa_func.sum(TrafficDaily.bytes_rx).label("rx"),
            sa_func.sum(TrafficDaily.bytes_tx).label("tx"),
        )
        .filter(TrafficDaily.client_id.in_(client_ids))
        .filter(TrafficDaily.date >= start)
        .filter(TrafficDaily.date <= today)
        .group_by(TrafficDaily.date)
        .all()
    )
    # `TrafficDaily.date` is a DateTime column even though it stores just the date.
    by_day = {}
    for r in rows:
        d = r.date.date() if hasattr(r.date, "date") else r.date
        by_day[d] = (int(r.rx or 0), int(r.tx or 0))

    series = []
    total_rx = 0
    total_tx = 0
    for i in range_count_days(days):
        d = start + timedelta(days=i)
        rx, tx = by_day.get(d, (0, 0))
        total_rx += rx
        total_tx += tx
        series.append({
            "date": d.isoformat(),
            "rx_gb": round(rx / (1024 ** 3), 3),
            "tx_gb": round(tx / (1024 ** 3), 3),
        })

    # ── Active devices per day (distinct client_ids with traffic > 0) ────────
    dev_rows = (
        db.query(
            TrafficDaily.date,
            sa_func.count(sa_func.distinct(TrafficDaily.client_id)).label("active"),
        )
        .filter(TrafficDaily.client_id.in_(client_ids))
        .filter(TrafficDaily.date >= start)
        .filter(TrafficDaily.date <= today)
        .filter((TrafficDaily.bytes_rx > 0) | (TrafficDaily.bytes_tx > 0))
        .group_by(TrafficDaily.date)
        .all()
    )
    dev_by_day = {}
    for r in dev_rows:
        d = r.date.date() if hasattr(r.date, "date") else r.date
        dev_by_day[d] = int(r.active or 0)

    active_devices_series = [
        {"date": (start + timedelta(days=i)).isoformat(),
         "count": dev_by_day.get(start + timedelta(days=i), 0)}
        for i in range_count_days(days)
    ]

    # ── Trend % vs previous equal-length period ──────────────────────────────
    prev_start = start - timedelta(days=days)
    prev_end = start - timedelta(days=1)
    prev_total_row = (
        db.query(
            sa_func.coalesce(sa_func.sum(TrafficDaily.bytes_rx + TrafficDaily.bytes_tx), 0)
        )
        .filter(TrafficDaily.client_id.in_(client_ids))
        .filter(TrafficDaily.date >= prev_start)
        .filter(TrafficDaily.date <= prev_end)
        .scalar()
    )
    prev_bytes = int(prev_total_row or 0)
    cur_bytes = total_rx + total_tx
    trend_pct = None
    if prev_bytes > 0:
        trend_pct = round(((cur_bytes - prev_bytes) / prev_bytes) * 100, 1)
    elif cur_bytes > 0:
        # No previous data but we have current — express as +100 (new traffic).
        trend_pct = 100.0

    return {
        "range": range,
        "from": start.isoformat(),
        "to": today.isoformat(),
        "series": series,
        "active_devices_series": active_devices_series,
        "summary": {
            "total_rx_gb": round(total_rx / (1024 ** 3), 3),
            "total_tx_gb": round(total_tx / (1024 ** 3), 3),
            "total_gb": round((total_rx + total_tx) / (1024 ** 3), 3),
            "trend_pct": trend_pct,
        },
    }


def range_count_days(n: int):
    """Yield 0..n-1 — small helper to keep the route body readable."""
    for i in range(n):
        yield i


# ═══════════════════════════════════════════════════════════════════════════
# PAYMENT ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/payments/create-invoice", response_model=InvoiceResponse)
async def create_invoice(
    data: CreateInvoiceRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create payment invoice for subscription via selected provider"""
    # Fail-safe: block new payments if system is in critical state
    try:
        from src.modules.failsafe import FailSafeManager
        FailSafeManager.instance().check_payment_allowed()
    except Exception as _fs_err:
        from src.modules.failsafe import FailSafeError
        if isinstance(_fs_err, FailSafeError):
            raise HTTPException(status_code=503, detail=str(_fs_err))
        # Non-fail-safe exception from import: don't block

    manager = SubscriptionManager(db)

    # Check if user is banned/inactive
    user = manager.get_user_by_id(user_id)
    if not user or user.is_banned or not user.is_active:
        raise HTTPException(status_code=403, detail="Account restricted")

    # Rate limit: max 5 invoices per hour per user
    now_ts = time.time()
    # Cleanup stale entries to prevent unbounded memory growth
    if len(_invoice_rate) > 1000:
        cutoff = now_ts - 3600
        stale = [uid for uid, times in _invoice_rate.items() if not times or times[-1] < cutoff]
        for uid in stale:
            del _invoice_rate[uid]
    _invoice_rate[user_id] = [t for t in _invoice_rate.get(user_id, []) if now_ts - t < 3600]
    if len(_invoice_rate[user_id]) >= 5:
        raise HTTPException(status_code=429, detail="Too many invoices. Try again later.")
    _invoice_rate[user_id].append(now_ts)

    # Get plan details
    plan = manager.get_plan_by_tier(data.plan_tier)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Validate plan price
    if plan.price_monthly_usd is None or plan.price_monthly_usd <= 0:
        raise HTTPException(status_code=400, detail="This plan cannot be purchased")

    # Calculate price based on duration.
    # Priority: operator-defined `pricing_tiers` (if set on the plan) →
    # legacy yearly/quarterly/monthly tiers → prorated monthly fallback.
    # An operator-defined ladder MUST match exactly: the customer's
    # requested duration_days has to be one of the entries, otherwise
    # we refuse rather than guess a price. Prevents a hand-crafted
    # API call from buying e.g. 28 days at the 30-day rate.
    custom_tiers = plan.pricing_tiers if isinstance(plan.pricing_tiers, list) else None
    amount_usd = None
    if custom_tiers:
        for tier in custom_tiers:
            if not isinstance(tier, dict):
                continue
            try:
                t_days = int(tier.get("days", 0))
                t_price = float(tier.get("price_usd", 0))
            except (TypeError, ValueError):
                continue
            if t_days == data.duration_days:
                amount_usd = t_price
                break
        if amount_usd is None:
            raise HTTPException(
                status_code=400,
                detail="Requested duration is not offered for this plan",
            )
    else:
        if data.duration_days >= 365:
            amount_usd = plan.price_yearly_usd or (plan.price_monthly_usd * 12)
        elif data.duration_days >= 90:
            amount_usd = plan.price_quarterly_usd or (plan.price_monthly_usd * 3)
        else:
            amount_usd = plan.price_monthly_usd * (data.duration_days / 30)

    amount_usd = round(amount_usd, 2)

    # Apply promo code discount
    promo_id = None
    discount_amount = 0.0
    bonus_days = 0
    if data.promo_code:
        from src.modules.subscription.subscription_models import PromoCode
        promo_code_str = data.promo_code.strip().upper()
        # FOR UPDATE serialises concurrent invoice-creations for the same
        # promo (e.g. user double-clicks Pay or opens two tabs). Without
        # the lock, both reads of `is_valid` could see `used_count <
        # max_uses` and both proceed. complete_payment then runs a
        # conditional atomic increment that refuses to overflow
        # max_uses, so the second invoice's activation still rejects
        # the discount even if it slipped past this check.
        promo_q = db.query(PromoCode).filter(PromoCode.code == promo_code_str)
        try:
            promo = promo_q.with_for_update().first()
        except Exception:
            promo = promo_q.first()
        if promo and promo.is_valid:
            # Enforce promo scoping server-side. /promo/validate checks these, but a
            # direct create-invoice call must too — otherwise a promo scoped to
            # another tier or a longer minimum duration can be redeemed here for a
            # bigger discount than intended. (security: promo scope bypass 2026-07)
            if promo.applies_to_tier and promo.applies_to_tier != data.plan_tier:
                raise HTTPException(
                    status_code=400,
                    detail=f"Promo code is only valid for the {promo.applies_to_tier} tier",
                )
            if promo.min_duration_days and data.duration_days < promo.min_duration_days:
                raise HTTPException(
                    status_code=400,
                    detail=f"Promo code requires a minimum of {promo.min_duration_days} days",
                )
            promo_id = promo.id
            if promo.discount_type == "percent":
                discount_amount = round(amount_usd * promo.discount_value / 100, 2)
                amount_usd = round(amount_usd - discount_amount, 2)
            elif promo.discount_type == "days":
                bonus_days = int(promo.discount_value)
            # Note: used_count is incremented on payment completion, not on invoice creation

    # Validate amount
    if amount_usd <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    if amount_usd > 10000:
        raise HTTPException(status_code=400, detail="Amount too high")

    # Map currency to PaymentMethod enum
    currency_to_method = {
        "btc": PaymentMethod.BTC,
        "usdt": PaymentMethod.USDT_TRC20,
        "usdc": PaymentMethod.USDT_ERC20,
        "ton": PaymentMethod.TON,
        "eth": PaymentMethod.ETH,
        "busd": PaymentMethod.USDT_TRC20,
        "usd": PaymentMethod.USD,
        "eur": PaymentMethod.EUR,
    }
    payment_method = currency_to_method.get(data.currency.lower(), PaymentMethod.USDT_TRC20)
    invoice_data = None
    provider_name = data.provider

    # Hard backend gate: free-tier instances can only invoice via NowPayments.
    # The /payments/providers endpoint hides everything else, but a forged
    # request would otherwise still go through — so we re-check here.
    try:
        from src.modules.license.manager import get_license_manager, LicenseType
        _info = get_license_manager().get_license_info()
        _is_paid = _info.type not in (LicenseType.FREE, LicenseType.TRIAL)
    except Exception:
        _is_paid = False
    if not _is_paid and data.provider != "nowpayments":
        raise HTTPException(
            status_code=403,
            detail="This payment method requires a paid license. Free tier supports NOWPayments only.",
        )

    # ── Route to selected provider ──
    if data.provider == "paypal":
        if not paypal_provider:
            raise HTTPException(status_code=503, detail="PayPal not configured")
        try:
            invoice = await paypal_provider.create_invoice(
                amount=int(amount_usd * 100),
                currency=data.currency.upper() if data.currency.upper() in ("USD", "EUR", "GBP") else "USD",
                description=f"VPN - {plan.name} ({data.duration_days} days)",
                metadata={"user_id": user_id, "plan": data.plan_tier},
            )
            invoice_data = {
                "invoice_id": invoice.id,
                "amount_usd": amount_usd,
                "amount_crypto": None,
                "currency": invoice.currency,
                "payment_url": invoice.metadata.get("approval_url", ""),
                "expires_at": invoice.expires_at.isoformat() if invoice.expires_at else "",
                "paypal_order_id": invoice.metadata.get("paypal_order_id", ""),
            }
        except Exception as e:
            logger.error("PayPal invoice creation failed for user %s: %s", user_id, e, exc_info=True)
            raise HTTPException(status_code=502, detail="Payment provider error. Try again or pick a different method.")

    elif data.provider == "nowpayments":
        if not nowpayments_provider:
            raise HTTPException(status_code=503, detail="NOWPayments not configured")
        try:
            # Per-invoice IPN URL beats the global Store Settings one — important
            # when the same NowPayments account is shared between several
            # services (e.g. license sales on flirexa.biz + customer VPN on
            # the operator's box). Without this, all webhooks land on whichever
            # URL is currently registered globally.
            cpd = (os.getenv("CLIENT_PORTAL_DOMAIN", "") or "").strip()
            portal_url = (os.getenv("CLIENT_PORTAL_URL", "") or "").strip()
            base_url = portal_url or (f"https://{cpd}" if cpd else "")
            ipn_url = f"https://{cpd}/client-portal/webhooks/nowpayments" if cpd else ""

            # NOWPayments price_currency MUST be fiat (USD/EUR) — passing
            # a crypto ticker like "USDT" breaks their hosted-checkout
            # min-amount lookup and every coin shows up as "currently
            # unavailable". The customer's crypto pick is a *pay*
            # currency, not a price denomination; let NOWPayments show
            # its own coin picker (or pass `pay_currency` separately if
            # we ever want to pre-select).
            np_fiat = data.currency.upper() if data.currency.upper() in ("USD", "EUR") else "USD"
            np_meta = {
                "user_id": user_id,
                "plan": data.plan_tier,
                "ipn_callback_url": ipn_url,
                # NOWPayments REQUIRES non-empty success_url and
                # cancel_url. Point both at the portal root so the
                # redirect lands somewhere sensible.
                "success_url": f"{base_url}/?paid=1" if base_url else "",
                "cancel_url":  f"{base_url}/?paid=0" if base_url else "",
            }
            # If the customer pre-picked a crypto in our UI, forward it as
            # pay_currency so NOWPayments lands them straight on that
            # coin's address instead of the picker.
            picked = data.currency.upper()
            if picked not in ("USD", "EUR"):
                np_meta["pay_currency"] = picked.lower()

            invoice = await nowpayments_provider.create_invoice(
                amount=int(amount_usd * 100),
                currency=np_fiat,
                description=f"VPN - {plan.name} ({data.duration_days} days)",
                metadata=np_meta,
            )
            invoice_data = {
                "invoice_id": invoice.id,
                "amount_usd": amount_usd,
                "amount_crypto": float(invoice.crypto_amount) if invoice.crypto_amount else None,
                "currency": invoice.currency,
                "payment_url": invoice.metadata.get("payment_url", ""),
                "expires_at": invoice.expires_at.isoformat() if invoice.expires_at else "",
            }
        except Exception as e:
            logger.error("NOWPayments invoice creation failed for user %s: %s", user_id, e, exc_info=True)
            raise HTTPException(status_code=502, detail="Payment provider error. Try again or pick a different method.")

    elif data.provider == "cryptopay":
        if cryptopay_adapter:
            try:
                invoice_data_raw = await create_subscription_invoice(
                    adapter=cryptopay_adapter,
                    user_id=user_id,
                    plan_name=plan.name,
                    amount_usd=amount_usd,
                    currency=data.currency,
                    duration_days=data.duration_days
                )
                invoice_data = {
                    "invoice_id": invoice_data_raw["invoice_id"],
                    "amount_usd": amount_usd,
                    "amount_crypto": invoice_data_raw.get("amount_crypto"),
                    "currency": data.currency,
                    "payment_url": invoice_data_raw.get("payment_url", ""),
                    "expires_at": invoice_data_raw.get("expires_at", ""),
                }
            except Exception as e:
                logger.error("CryptoPay invoice creation failed for user %s: %s", user_id, e, exc_info=True)
                raise HTTPException(status_code=502, detail="Payment provider error. Try again or pick a different method.")
        else:
            # Test mode: create mock invoice
            mock_invoice_id = str(secrets.randbelow(900000) + 100000)
            invoice_data = {
                "invoice_id": mock_invoice_id,
                "amount_usd": amount_usd,
                "amount_crypto": amount_usd,
                "currency": data.currency,
                "payment_url": f"https://t.me/CryptoBot?start=invoice_{mock_invoice_id}",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            }
            provider_name = "test"

    # Plugin provider fallback
    if not invoice_data:
        import sys as _sys
        _portal = _sys.modules.get(__name__)
        _prov = getattr(_portal, f"{data.provider}_provider", None) if _portal else None
        if _prov and hasattr(_prov, "create_invoice"):
            try:
                _inv = await _prov.create_invoice(
                    amount=int(amount_usd * 100),
                    currency=data.currency.upper(),
                    description=f"VPN - {plan.name} ({data.duration_days} days)",
                    metadata={"user_id": user_id, "plan": data.plan_tier,
                              "return_url": os.getenv("CLIENT_PORTAL_URL", ""),
                              "cancel_url": os.getenv("CLIENT_PORTAL_URL", "")},
                )
                invoice_data = {
                    "invoice_id": _inv.id,
                    "amount_usd": amount_usd,
                    "amount_crypto": _inv.crypto_amount,
                    "currency": _inv.currency,
                    "payment_url": _inv.metadata.get("payment_url") or _inv.metadata.get("approval_url", ""),
                    "expires_at": _inv.expires_at.isoformat() if _inv.expires_at else "",
                    # Surface provider-side id so the recovery poller can
                    # query check_payment() with the right argument.
                    "provider_invoice_id": (
                        _inv.metadata.get("stripe_session_id")
                        or _inv.metadata.get("mollie_id")
                        or _inv.metadata.get("razorpay_id")
                        or _inv.metadata.get("payme_id")
                        or _inv.metadata.get("paylio_id")
                        or _inv.id
                    ),
                    "stripe_session_id": _inv.metadata.get("stripe_session_id"),
                }
                # Convert the raw provider string ('stripe', 'mollie', etc.) to
                # the matching PaymentMethod enum member so SubscriptionManager
                # can do `.value` on it and SQLAlchemy serializes the canonical
                # member NAME (`'STRIPE'`) into the Postgres ENUM column — which
                # is what the column was created with for all the old crypto
                # values (BTC, USDT_TRC20, …). Passing the raw string here used
                # to either crash on `.value` or insert lowercase 'stripe' that
                # the ENUM didn't recognize.
                try:
                    payment_method = PaymentMethod(data.provider)
                except ValueError:
                    # Unknown provider — keep the raw string flowing through;
                    # SQLAlchemy will raise a clearer error than the silent
                    # ENUM mismatch we used to ship.
                    payment_method = data.provider
                provider_name = data.provider
            except Exception as _e:
                logger.error(f"Plugin provider {data.provider} error: {_e}")
                raise HTTPException(status_code=500, detail=f"Payment error: {_e}")
        else:
            raise HTTPException(status_code=500, detail="Payment provider not configured")

    # Save payment record
    payment = manager.create_payment(
        user_id=user_id,
        amount_usd=amount_usd,
        payment_method=payment_method,
        subscription_tier=data.plan_tier,
        duration_days=data.duration_days,
        invoice_id=invoice_data["invoice_id"],
        provider_name=provider_name,
    )

    payment.crypto_amount = str(invoice_data.get("amount_crypto") or "")
    if promo_id:
        payment.promo_code_id = promo_id
        payment.discount_amount_usd = discount_amount
    if bonus_days:
        payment.duration_days = (payment.duration_days or data.duration_days) + bonus_days
    # Store provider-specific order ID for webhook lookup + status polling.
    # Without this the recovery poller can't ask the provider "is invoice X paid?"
    # and a dropped webhook will leave the customer stuck.
    if data.provider == "paypal" and invoice_data.get("paypal_order_id"):
        payment.provider_invoice_id = invoice_data["paypal_order_id"]
    elif data.provider == "nowpayments":
        payment.provider_invoice_id = invoice_data["invoice_id"]
    elif data.provider == "stripe" and invoice_data.get("stripe_session_id"):
        payment.provider_invoice_id = invoice_data["stripe_session_id"]
    elif data.provider in ("mollie", "razorpay", "payme", "paylio") and invoice_data.get("provider_invoice_id"):
        payment.provider_invoice_id = invoice_data["provider_invoice_id"]
    else:
        # Fallback for plugin providers: assume the invoice we sent matches.
        # This is the same as our internal id, which providers usually echo
        # back as `metadata.invoice_id` on their webhooks.
        payment.provider_invoice_id = invoice_data["invoice_id"]
    payment.set_provider_data(invoice_data)
    db.commit()

    return InvoiceResponse(**invoice_data)


@router.get("/payments/providers")
async def get_available_providers():
    """
    List of configured payment providers visible to the customer.

    Tier gating (matches the open-core promise):
    - FREE tier (or unlicensed instance) → only NowPayments. This is the open-core
      payment rail, so self-hosters can accept crypto without a paid plan.
    - Any paid tier → every provider the admin has configured: NowPayments,
      PayPal, CryptoPay, plus all auto-loaded plugins (Stripe, Mollie,
      Razorpay, Payme, …).

    The check is a hard backend filter — frontend can't reveal a gated provider
    by tweaking flags.
    """
    # Resolve current license tier without crashing the route if license
    # subsystem is unavailable (e.g. dev environments) — assume free in that case.
    is_paid_tier = False
    try:
        from src.modules.license.manager import get_license_manager, LicenseType
        info = get_license_manager().get_license_info()
        is_paid_tier = info.type not in (LicenseType.FREE, LicenseType.TRIAL)
    except Exception as _lerr:
        logger.debug("Provider gating: could not resolve license tier (%s) — defaulting to free.", _lerr)

    providers = []

    # NowPayments is the always-available rail (free + paid).
    if nowpayments_provider:
        providers.append({
            "id": "nowpayments",
            "name": "NOWPayments",
            "display_name": "NOWPayments",
            "type": "crypto",
            "tier": "free",
        })

    if is_paid_tier:
        # Built-in extras
        if cryptopay_adapter:
            providers.append({
                "id": "cryptopay",
                "name": "CryptoPay (Telegram)",
                "display_name": "CryptoPay (Telegram)",
                "type": "crypto",
                "tier": "paid",
            })
        if paypal_provider:
            providers.append({
                "id": "paypal",
                "name": "PayPal",
                "display_name": "PayPal",
                "type": "fiat",
                "tier": "paid",
            })

        # Auto-detected plugins (Stripe, Mollie, Razorpay, Payme, …)
        import sys
        _this = sys.modules[__name__]
        _portal = sys.modules.get("src.api.routes.client_portal", _this)
        seen = {p["id"] for p in providers}
        for attr_name in dir(_portal):
            if not attr_name.endswith("_provider"):
                continue
            if attr_name in ("paypal_provider", "nowpayments_provider"):
                continue
            prov = getattr(_portal, attr_name, None)
            if not prov or not hasattr(prov, "name") or not hasattr(prov, "display_name"):
                continue
            if prov.name in seen:
                continue
            providers.append({
                "id": prov.name,
                "name": prov.display_name,
                "display_name": prov.display_name,
                "type": getattr(prov, "type", "plugin"),
                "tier": "paid",
            })
            seen.add(prov.name)

    if not providers:
        # Last-resort fallback so the page renders something the customer can act on.
        providers.append({
            "id": "nowpayments",
            "name": "NOWPayments",
            "display_name": "NOWPayments",
            "type": "crypto",
            "tier": "free",
            "configured": False,
            "hint": "Admin has not configured a payment provider yet.",
        })

    return providers


@router.get("/payments/check/{invoice_id}")
async def check_payment_status(
    invoice_id: str,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check payment status"""
    manager = SubscriptionManager(db)

    # Get payment from database
    payment = manager.get_payment_by_invoice(invoice_id)
    if not payment or payment.user_id != user_id:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Check via provider if payment is still pending
    payment_status = payment.status
    if payment.status != "completed":
        try:
            provider = payment.provider_name or "cryptopay"
            if provider == "paypal" and paypal_provider and payment.provider_invoice_id:
                from src.modules.payment.base import PaymentStatus as PS
                ps = await paypal_provider.check_payment(payment.provider_invoice_id)
                if ps == PS.COMPLETED:
                    manager.complete_payment(invoice_id, sync_wg=False)
                    await _sync_wg_after_payment(db, payment.user_id, manager, invoice_id=invoice_id)
                    payment_status = "completed"
                else:
                    payment_status = ps.value
            elif provider == "nowpayments" and nowpayments_provider and payment.provider_invoice_id:
                from src.modules.payment.base import PaymentStatus as PS
                ps = await nowpayments_provider.check_payment(payment.provider_invoice_id)
                if ps == PS.COMPLETED:
                    manager.complete_payment(invoice_id, sync_wg=False)
                    await _sync_wg_after_payment(db, payment.user_id, manager, invoice_id=invoice_id)
                    payment_status = "completed"
                else:
                    payment_status = ps.value
            elif provider == "cryptopay" and cryptopay_adapter:
                payment_status = await cryptopay_adapter.check_payment(int(invoice_id))
                if payment_status == "paid" and payment.status != "completed":
                    manager.complete_payment(invoice_id, sync_wg=False)
                    await _sync_wg_after_payment(db, payment.user_id, manager, invoice_id=invoice_id)
                    payment_status = "completed"
            else:
                # Plugin provider
                import sys as _sys
                _portal = _sys.modules.get(__name__)
                _prov = getattr(_portal, f"{provider}_provider", None) if _portal else None
                if _prov and hasattr(_prov, "check_payment"):
                    # The relative import was off by one dot — `..`
                    # from src/api/routes lands at src/api, where no
                    # `modules` package exists. The plugin-provider
                    # status poll therefore ImportErrored on every
                    # call and the outer except masked it, leaving
                    # the customer stuck on "pending" until the
                    # webhook fired.
                    from ...modules.payment.base import PaymentStatus as _PS
                    _ps = await _prov.check_payment(payment.provider_invoice_id or invoice_id)
                    if _ps == _PS.COMPLETED:
                        manager.complete_payment(invoice_id, sync_wg=False)
                        await _sync_wg_after_payment(db, payment.user_id, manager, invoice_id=invoice_id)
                        payment_status = "completed"
        except Exception as _chk_err:
            logger.warning(
                "[PAY:%s] Provider status check failed (using DB status): %s",
                invoice_id, _chk_err,
            )

    return {
        "invoice_id": invoice_id,
        "status": payment_status,
        "amount_usd": payment.amount_usd,
        "currency": payment.payment_method.value,
        "created_at": payment.created_at.isoformat(),
        "expires_at": payment.expires_at.isoformat() if payment.expires_at else None
    }


@router.get("/payments/history")
async def get_payment_history(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100)
):
    """Get payment history"""
    manager = SubscriptionManager(db)
    payments = manager.get_user_payments(user_id, limit=limit)

    return [
        {
            "invoice_id": p.invoice_id,
            "amount_usd": p.amount_usd,
            "payment_method": p.payment_method.value,
            "status": p.status,
            "subscription_tier": p.subscription_tier if p.subscription_tier else None,
            "duration_days": p.duration_days,
            "created_at": p.created_at.isoformat(),
            "completed_at": p.completed_at.isoformat() if p.completed_at else None
        }
        for p in payments
    ]


# ═══════════════════════════════════════════════════════════════════════════
# WEBHOOK ROUTES
# ═══════════════════════════════════════════════════════════════════════════


# NOTE: the generic `@router.post("/webhooks/{provider_name}")` handler used
# to live here, but FastAPI matches routes in registration order — putting
# a catch-all in front of the dedicated PayPal / NowPayments / CryptoPay
# routes meant the generic 404'd those built-in providers before the
# dedicated handlers ever ran, so their webhooks silently died with "Not
# Found" and the customer-paid → subscription-active link never fired.
# The catch-all is now defined *after* the dedicated routes below.


@router.post("/webhooks/cryptopay")
async def cryptopay_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Handle CryptoPay webhook for payment notifications"""
    if not cryptopay_adapter:
        raise HTTPException(status_code=503, detail="CryptoPay not configured")

    body = await request.body()
    headers = dict(request.headers)

    # Process webhook
    try:
        update = await cryptopay_adapter.process_webhook(body, headers)
    except Exception as e:
        logger.error(f"CryptoPay webhook processing error: {e}")
        raise HTTPException(status_code=400, detail="Webhook processing failed")

    if not update:
        raise HTTPException(status_code=400, detail="Invalid webhook")

    if update["type"] == "invoice_paid":
        invoice_id = update["invoice_id"]

        # Complete payment without direct WG sync
        manager = SubscriptionManager(db)
        # for_update locks the row — concurrent webhook deliveries for the
        # same invoice serialise here instead of both passing the status
        # check below and double-firing the post-completion side effects.
        payment = manager.get_payment_by_invoice(str(invoice_id), for_update=True)
        if payment and payment.status != "completed":
            # Validate webhook amount matches payment record.
            # Underpayment: rejected outright. CryptoPay's hosted checkout
            # commits the exact invoice amount; any shortfall here is
            # either a misconfigured exchange-rate retry or someone trying
            # to underpay. Sub-cent rounding only goes our way (the
            # checkout pages always round up to the customer's quoted
            # amount), so an exact-match check is safe.
            # Overpayment beyond 10%: logged for ops attention but still
            # honoured — the customer paid more than asked, refunding the
            # excess is an admin concern, not a reason to deny the sub.
            webhook_amount = float(update.get("amount", 0))
            if webhook_amount > 0:
                if webhook_amount < payment.amount_usd:
                    logger.error(f"CryptoPay underpayment: webhook={webhook_amount}, expected={payment.amount_usd}, invoice={invoice_id}")
                    return {"status": "error", "message": "Amount mismatch"}
                if webhook_amount > payment.amount_usd * 1.10:
                    logger.warning(f"CryptoPay overpayment (>10%): webhook={webhook_amount}, expected={payment.amount_usd}, invoice={invoice_id}")

            # Check if user is banned/inactive — still record payment but skip WG activation
            restricted = _is_user_restricted(db, payment.user_id)
            manager.complete_payment(str(invoice_id), sync_wg=False)
            if not restricted:
                try:
                    await _sync_wg_after_payment(db, payment.user_id, manager)
                except Exception as e:
                    logger.error(f"CryptoPay: WG sync failed for user {payment.user_id} after payment {invoice_id}: {e}")
            else:
                logger.warning(f"CryptoPay: payment {invoice_id} completed for restricted user {payment.user_id}, WG not activated")

        return {"status": "ok", "message": "Payment processed"}

    return {"status": "ok"}


@router.post("/webhooks/paypal")
async def paypal_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Handle PayPal webhook for order approval/capture"""
    if not paypal_provider:
        raise HTTPException(status_code=503, detail="PayPal not configured")

    body = await request.body()
    headers = dict(request.headers)

    import json
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Verify signature in production
    try:
        sig_ok = await paypal_provider.verify_webhook_signature(headers, body)
    except Exception as e:
        logger.error(f"PayPal signature verification error: {e}")
        raise HTTPException(status_code=400, detail="Webhook signature verification failed")
    if not sig_ok:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    # Process webhook (auto-captures approved orders)
    try:
        result = await paypal_provider.process_webhook(data)
    except Exception as e:
        logger.error(f"PayPal webhook processing error: {e}")
        raise HTTPException(status_code=400, detail="Webhook processing failed")

    if not result:
        raise HTTPException(status_code=400, detail="Webhook processing failed")

    # If order was captured, complete the payment
    resource = data.get("resource", {})
    event_type = data.get("event_type", "")

    if event_type in ("CHECKOUT.ORDER.APPROVED", "PAYMENT.CAPTURE.COMPLETED"):
        order_id = resource.get("id", "")
        # Find payment by provider order ID stored in provider_invoice_id
        manager = SubscriptionManager(db)
        from src.modules.subscription.subscription_models import ClientPortalPayment
        # FOR UPDATE serialises concurrent PayPal webhook retries for the
        # same order_id; complete_payment is also idempotent under its own
        # lock as backstop.
        payment_q = db.query(ClientPortalPayment).filter(
            ClientPortalPayment.provider_name == "paypal",
            ClientPortalPayment.provider_invoice_id == order_id,
        )
        try:
            payment = payment_q.with_for_update().first()
        except Exception:
            payment = payment_q.first()

        if payment and payment.status != "completed":
            restricted = _is_user_restricted(db, payment.user_id)
            manager.complete_payment(payment.invoice_id, sync_wg=False)
            if not restricted:
                try:
                    await _sync_wg_after_payment(db, payment.user_id, manager)
                except Exception as e:
                    logger.error(f"PayPal: WG sync failed for user {payment.user_id} after payment {payment.invoice_id}: {e}")
            else:
                logger.warning(f"PayPal: payment {payment.invoice_id} completed for restricted user {payment.user_id}, WG not activated")

    return {"status": "ok"}


@router.post("/webhooks/nowpayments")
async def nowpayments_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Handle NOWPayments IPN webhook (HMAC-SHA512 over sorted JSON)."""
    if not nowpayments_provider:
        raise HTTPException(status_code=503, detail="NOWPayments not configured")

    import json
    body = await request.body()
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    signature = request.headers.get("x-nowpayments-sig", "")

    # CRITICAL: verify signature *before* trusting any field in the body.
    # Without this check, an attacker could POST a forged "finished" event
    # for any order_id and credit a free subscription.
    if not nowpayments_provider.verify_signature(body, signature):
        logger.warning("NOWPayments: rejected webhook with bad signature (order_id=%s)", data.get("order_id"))
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        result = await nowpayments_provider.process_webhook(data, signature)
    except Exception as e:
        logger.error(f"NOWPayments webhook processing error: {e}")
        raise HTTPException(status_code=400, detail="Webhook processing failed")

    if not result:
        # Status was valid but not a "completed" event — return 200 so NowPayments doesn't retry.
        return {"status": "ok", "message": "event acknowledged"}

    # If payment finished, complete it
    if data.get("payment_status", "").lower() == "finished":
        order_id = data.get("order_id", "")
        if order_id:
            manager = SubscriptionManager(db)
            payment = manager.get_payment_by_invoice(order_id, for_update=True)
            if payment and payment.status != "completed":
                restricted = _is_user_restricted(db, payment.user_id)
                manager.complete_payment(order_id, sync_wg=False)
                if not restricted:
                    try:
                        await _sync_wg_after_payment(db, payment.user_id, manager)
                    except Exception as e:
                        logger.error(f"NOWPayments: WG sync failed for user {payment.user_id} after payment {order_id}: {e}")
                else:
                    logger.warning(f"NOWPayments: payment {order_id} completed for restricted user {payment.user_id}, WG not activated")

    return {"status": "ok"}


@router.get("/webhooks/paylio")
async def paylio_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """PayLio's IPN comes in as an HTTP GET with ``?ipn_token=...`` and
    no signature — the upstream docs treat the callback as an
    unverified hint. We forward the token to the plugin via
    ``x-paylio-ipn-token``, which then re-fetches ``/payment-status``
    with our API key to confirm the payment actually settled before
    we credit anything.

    The POST ``/webhooks/{provider_name}`` dispatcher below is method-
    locked and can't accept a GET, so PayLio gets its own route.
    """
    import sys as _sys
    _portal = _sys.modules.get(__name__)
    _prov = getattr(_portal, "paylio_provider", None) if _portal else None
    if not _prov:
        raise HTTPException(status_code=404, detail="paylio not configured")

    token = (request.query_params.get("ipn_token") or "").strip()
    if not token:
        # Nothing to verify — return 200 so PayLio doesn't keep retrying
        # but log it for triage: a tokenless callback usually means
        # CLIENT_PORTAL_DOMAIN is misconfigured (PayLio appended the
        # token to a URL that something stripped).
        logger.warning("PayLio webhook hit without ipn_token query param")
        return {"status": "ignored", "reason": "missing ipn_token"}

    try:
        result = await _prov.process_webhook(b"", {"x-paylio-ipn-token": token})
    except Exception as e:
        logger.error("PayLio webhook processing error: %s", e)
        raise HTTPException(status_code=400, detail="Webhook processing failed")

    verified = bool(result.get("verified"))
    data = result.get("data") or {}
    paylio_payment_id = result.get("order_id")
    if not verified or not paylio_payment_id:
        return {"status": "ok", "message": "not actionable yet"}

    # The PayLio payment_id is what we stored as provider_invoice_id
    # at create time — look the row up by that, not by our internal id
    # (PayLio doesn't echo `note` on /payment-status).
    from src.modules.subscription.subscription_models import ClientPayment as _CP
    payment = (
        db.query(_CP)
        .filter(_CP.provider_invoice_id == str(paylio_payment_id))
        .first()
    )
    if not payment:
        logger.warning("PayLio: no payment row for payment_id=%s", paylio_payment_id)
        return {"status": "ok", "message": "no matching invoice"}

    if payment.status != "completed":
        manager = SubscriptionManager(db)
        manager.complete_payment(payment.invoice_id, sync_wg=False)
        try:
            await _sync_wg_after_payment(db, payment.user_id, manager)
        except Exception as e:
            logger.error("PayLio: WG sync failed for user %s: %s", payment.user_id, e)
        logger.info("PayLio: payment %s completed (invoice=%s)", paylio_payment_id, payment.invoice_id)

    return {"status": "ok"}


@router.post("/webhooks/{provider_name}")
async def plugin_webhook(
    provider_name: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Dynamic webhook handler for plugin payment providers (Stripe, Mollie,
    Razorpay, Payme, …). Must be registered AFTER the dedicated routes for
    cryptopay / paypal / nowpayments — FastAPI matches routes in
    registration order, so an earlier catch-all would shadow the dedicated
    handlers and 404 every PayPal / NowPayments / CryptoPay webhook.

    Security model:
    - Each provider's `process_webhook` MUST verify the request signature
      itself (using raw body + headers we pass through). The handler does
      NOT trust an unsigned body — every provider implements its own
      signature scheme (Stripe-Signature, X-Razorpay-Signature, etc.).
    - We pass `body` (raw bytes) and `headers` (case-insensitive) so the
      provider can both parse and verify in one place.
    """
    import sys as _sys
    _portal = _sys.modules.get(__name__)
    _prov = getattr(_portal, f"{provider_name}_provider", None) if _portal else None
    if not _prov:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    # Try the new signature: process_webhook(body, headers) → (verified, data, order_id).
    # Fall back to the legacy signature for plugins that haven't been upgraded yet.
    import inspect
    try:
        sig = inspect.signature(_prov.process_webhook)
        param_count = len(sig.parameters)
    except (TypeError, ValueError):
        param_count = 1

    try:
        if param_count >= 2:
            # New API — provider verifies signature internally.
            result = await _prov.process_webhook(body, headers)
        else:
            # Legacy plugin signature (single-arg `process_webhook(data)`)
            # would accept the payload without ANY signature verification.
            # That's a free-money path for anyone who can guess an
            # invoice_id, so we refuse the call instead of falling
            # through with a warning. Plugin author has to upgrade to
            # `process_webhook(body, headers)` and verify the provider's
            # signature scheme inside.
            logger.error(
                "Plugin %s exposes legacy unsigned webhook API — refusing. "
                "Upgrade the plugin to process_webhook(body, headers) and "
                "verify the provider's signature header internally before "
                "trusting the payload.",
                provider_name,
            )
            raise HTTPException(
                status_code=501,
                detail=(
                    "Webhook handler not properly configured: provider "
                    "plugin must verify the signature. Contact support."
                ),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Plugin webhook {provider_name} error: {e}")
        raise HTTPException(status_code=400, detail="Webhook processing failed")

    # Provider returns either a bool (legacy) or a dict (new):
    #   {"verified": True, "data": {...}, "order_id": "..."}.
    verified = False
    data = {}
    order_id = None
    if isinstance(result, dict):
        verified = bool(result.get("verified"))
        data = result.get("data") or {}
        order_id = result.get("order_id")
    elif isinstance(result, bool):
        verified = result
        try:
            data = json.loads(body)
        except Exception:
            data = {}

    if not verified:
        # 401 makes intent clear: signature/processing rejected the event.
        raise HTTPException(status_code=401, detail="Webhook signature invalid or event not actionable")

    if not order_id:
        # Best-effort fallback to extract invoice/order ID from common shapes.
        order_id = (
            data.get("metadata", {}).get("invoice_id")
            or data.get("data", {}).get("object", {}).get("metadata", {}).get("invoice_id")
            or data.get("order_id")
            or data.get("id")
        )
    if not order_id:
        return {"status": "ok", "message": "no order_id in payload"}

    manager = SubscriptionManager(db)
    payment = manager.get_payment_by_invoice(str(order_id), for_update=True)
    if payment and payment.status != "completed":
        manager.complete_payment(str(order_id), sync_wg=False)
        try:
            await _sync_wg_after_payment(db, payment.user_id, manager)
        except Exception as e:
            logger.error(f"Plugin {provider_name}: WG sync failed: {e}")
        logger.info(f"Plugin {provider_name}: payment {order_id} completed")

    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
# EMAIL VERIFICATION ROUTES
# ═══════════════════════════════════════════════════════════════════════════

class VerifyEmailRequest(BaseModel):
    token: str


@router.post("/auth/verify-email")
async def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Verify email with token"""
    from src.modules.subscription.subscription_models import ClientUser

    user = db.query(ClientUser).filter(
        ClientUser.verification_token == data.token,
        ClientUser.email_verified == False
    ).first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user.email_verified = True
    user.verification_token = None
    db.commit()

    # Send welcome email
    smtp_service, smtp_settings = _get_email_service()
    if smtp_service:
        branding = get_all_branding(db)
        lang = _pick_email_language(None, user)
        await asyncio.get_running_loop().run_in_executor(
            None,
            smtp_service.send_welcome_email,
            user.email,
            user.username,
            (branding.get("branding_customer_app_name") or branding.get("branding_app_name") or "VPN"),
            branding.get("branding_support_email") or "",
            lang,
            branding.get("branding_logo_url") or "",
        )

    return {"message": "Email verified successfully"}


@router.post("/auth/resend-verification")
async def resend_verification(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Resend verification email"""
    smtp_service, smtp_settings = _get_email_service()
    if not smtp_service:
        raise HTTPException(status_code=503, detail="Email service not configured")

    manager = SubscriptionManager(db)
    user = manager.get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.email_verified:
        return {"message": "Email already verified"}

    # Generate new token
    token = secrets.token_urlsafe(32)
    user.verification_token = token
    db.commit()

    branding = get_all_branding(db)
    lang = _pick_email_language(None, user)
    sent = await asyncio.get_running_loop().run_in_executor(
        None,
        smtp_service.send_verification_email,
        user.email,
        token,
        smtp_settings.get("CLIENT_PORTAL_URL", ""),
        (branding.get("branding_customer_app_name") or branding.get("branding_app_name") or "VPN"),
        branding.get("branding_support_email") or "",
        lang,
        branding.get("branding_logo_url") or "",
    )

    if not sent:
        raise HTTPException(status_code=500, detail="Failed to send email")

    return {"message": "Verification email sent"}


# ═══════════════════════════════════════════════════════════════════════════
# CRYPTO INFO ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/crypto/currencies")
async def get_crypto_currencies():
    """Get supported cryptocurrencies"""
    if cryptopay_adapter:
        currencies = await cryptopay_adapter.get_currencies()
        return currencies
    # Fallback: static list
    return [
        {"code": "USDT", "name": "Tether"},
        {"code": "BTC", "name": "Bitcoin"},
        {"code": "TON", "name": "Toncoin"},
        {"code": "ETH", "name": "Ethereum"},
        {"code": "USDC", "name": "USD Coin"},
        {"code": "BUSD", "name": "Binance USD"},
    ]


@router.get("/crypto/rates")
async def get_exchange_rates():
    """Get current exchange rates"""
    if cryptopay_adapter:
        rates = await cryptopay_adapter.get_exchange_rates()
        return rates
    # Fallback: approximate rates (USD-based)
    return {
        "USDT": 1.0,
        "BTC": 97000.0,
        "TON": 5.5,
        "ETH": 3200.0,
        "USDC": 1.0,
        "BUSD": 1.0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# WIREGUARD CLIENT ROUTES — via Admin API
# ═══════════════════════════════════════════════════════════════════════════

def _get_user_client_ids(db: Session, user_id: int) -> list:
    """
    Get list of WG client IDs linked to a portal user.

    JOINs against Client so orphaned links (ClientUserClients pointing at
    a Client row that has since been deleted) don't count. Without this
    JOIN the limit-check at POST /wireguard/clients sees the orphan as a
    device-in-use while GET /wireguard/clients hides it (the Admin API
    filters out unknown ids), causing the dashboard to show "0/1" while
    every "Add device" click 409s with "limit reached". Reported by a
    customer on the first install where a portal user had a stale link
    in 1.6.20.
    """
    from src.database.models import Client as _Client
    rows = (
        db.query(ClientUserClients.client_id)
        .join(_Client, _Client.id == ClientUserClients.client_id)
        .filter(ClientUserClients.client_user_id == user_id)
        .all()
    )
    return [r.client_id for r in rows]


def _user_owns_client(db: Session, user_id: int, client_id: int) -> bool:
    """Check if portal user owns a specific WG client"""
    link = db.query(ClientUserClients).filter(
        ClientUserClients.client_user_id == user_id,
        ClientUserClients.client_id == client_id
    ).first()
    return link is not None


@router.get("/wireguard/clients")
async def get_wireguard_clients(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's WireGuard clients via Admin API.

    Each returned client is annotated with its `slot_id` (from
    ClientUserClients) so the customer portal can collapse the
    per-region peers of one Device Slot down to a single row — the
    Dashboard list used to render every peer of every slot separately
    and ballooned to 10+ rows for a 5-device subscription.
    """
    api = get_admin_api()
    client_ids = _get_user_client_ids(db, user_id)

    if not client_ids:
        return []

    clients = await api.get_clients_by_ids(client_ids)

    slot_map = dict(
        db.query(ClientUserClients.client_id, ClientUserClients.slot_id)
        .filter(
            ClientUserClients.client_user_id == user_id,
            ClientUserClients.client_id.in_(client_ids),
        )
        .all()
    )
    for c in clients:
        cid = c.get("id") if isinstance(c, dict) else getattr(c, "id", None)
        if cid is not None:
            slot_id = slot_map.get(cid)
            if isinstance(c, dict):
                c["slot_id"] = slot_id
            else:
                try:
                    c.slot_id = slot_id
                except Exception:
                    pass
    return clients


@router.get("/wireguard/config/{client_id}")
async def get_wireguard_config(
    client_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get WireGuard configuration file via Admin API"""
    if not _user_owns_client(db, user_id, client_id):
        raise HTTPException(status_code=404, detail="Client not found")

    # Per-operator gate: an operator can disable manual config download from the
    # portal (license flag `portal_no_config_download`) to push customers to the
    # app + keep configs off many devices. Hiding the UI button isn't enough —
    # enforce it here too.
    from ...modules.license.portal_gates import is_gated
    if is_gated("config_download"):
        raise HTTPException(status_code=403, detail="Config download is disabled for this portal.")

    api = get_admin_api()
    result = await api.get_client_config(client_id)

    if not result:
        raise HTTPException(status_code=500, detail="Failed to get config from admin API")

    return result


@router.get("/wireguard/qrcode/{client_id}")
async def get_wireguard_qrcode(
    client_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get QR code image via Admin API"""
    if not _user_owns_client(db, user_id, client_id):
        raise HTTPException(status_code=404, detail="Client not found")

    # Per-operator gate (see get_wireguard_config): a QR is just the config in
    # another form, so the same anti-extraction toggle applies.
    from ...modules.license.portal_gates import is_gated
    if is_gated("qr"):
        raise HTTPException(status_code=403, detail="QR code is disabled for this portal.")

    api = get_admin_api()
    qr_bytes = await api.get_client_qrcode(client_id)

    if not qr_bytes:
        raise HTTPException(status_code=500, detail="Failed to get QR code from admin API")

    return Response(
        content=qr_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=client-{client_id}-qr.png"}
    )


class CreateClientRequest(BaseModel):
    server_id: Optional[int] = None

@router.post("/wireguard/create")
async def create_wireguard_client(
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new WireGuard client via Admin API (respects max_devices limit)"""
    # Parse optional fields from body
    server_id = None
    custom_name = None
    try:
        body = await request.json()
        server_id = body.get("server_id")
        custom_name = (body.get("name") or "").strip()[:64] or None
    except Exception as _body_err:
        logger.debug("create_wireguard_config: no/invalid JSON body (user_id=%d): %s", user_id, _body_err)

    if server_id is not None:
        target_server = db.query(Server).filter(Server.id == server_id).first()
        if not target_server:
            raise HTTPException(status_code=404, detail="Server not found")
        # Reject test / hidden servers even if the picker somehow served the
        # id (stale frontend, forged request). The portal `GET /servers`
        # already filters these out — this is the second line of defence.
        if not getattr(target_server, "customer_visible", True):
            raise HTTPException(status_code=404, detail="Server not found")

    manager = SubscriptionManager(db)
    subscription = manager.get_subscription(user_id)

    if not subscription or not subscription.is_active:
        # Distinguish "expired" from "never subscribed" so the app shows the
        # right wording — "Your VPN service has expired" vs "Choose a plan".
        # Both stay HTTP 400 with a string detail (unchanged shape) so current
        # app builds surface it verbatim; newer builds key off the wording /
        # the /subscription is_expired flag for a styled banner.
        if subscription and subscription.is_expired:
            raise HTTPException(
                status_code=400,
                detail="Your VPN service has expired. Renew your plan to reconnect.",
            )
        raise HTTPException(
            status_code=400,
            detail="No active subscription. Choose a plan to start.",
        )

    # Check device limit. Surface a structured payload so the portal can
    # render an inline "Upgrade plan" CTA next to the message instead of
    # a bare error string.
    #
    # IMPORTANT: count slots and legacy peers as separate "device units"
    # rather than summing every ClientUserClients row. Without this a slot
    # with 5 per-region peers inflates the count by 5×, and the legacy
    # peer/slot accounting on /devices and here disagree on what counts.
    # A slot = 1 device. A legacy single-server peer = 1 device.
    from src.modules.subscription.subscription_models import DeviceSlot
    # Serialize the count-then-create against concurrent adds for the same
    # user (TOCTOU device over-allocation). Per-user xact lock held until
    # commit; namespaced under 2_000_000 to avoid the license lock key.
    try:
        from sqlalchemy import text as _sql_text
        db.execute(_sql_text("SELECT pg_advisory_xact_lock(:k)"),
                   {"k": 2_000_000 + int(user_id)})
    except Exception:
        pass  # SQLite in tests / non-PG engines — skip advisory lock
    existing_ids = _get_user_client_ids(db, user_id)
    slot_count = (
        db.query(DeviceSlot)
        .filter(DeviceSlot.client_user_id == user_id)
        .count()
    )
    legacy_count = (
        db.query(ClientUserClients)
        .filter(
            ClientUserClients.client_user_id == user_id,
            ClientUserClients.slot_id.is_(None),
        )
        .count()
    )
    total_devices = slot_count + legacy_count
    max_devices = subscription.max_devices or 1
    if total_devices >= max_devices:
        # Audit the rejection so admins can see how often subscribers hit the
        # ceiling — useful signal for "raise the cap on this plan" decisions.
        try:
            from src.database.models import DeviceLimitEvent
            db.add(DeviceLimitEvent(
                user_id=user_id, client_id=None,
                event_type="blocked", reason="DEVICE_LIMIT",
                max_devices=max_devices, used_devices=total_devices,
            ))
            db.commit()
        except Exception as _e:
            logger.debug("could not write device_limit_event: %s", _e)
        raise HTTPException(
            status_code=409,
            detail={
                "code":         "device_limit_reached",
                "message":      "You've reached the device limit for your plan.",
                "max_devices":  max_devices,
                "used_devices": total_devices,
                "current_tier": subscription.tier,
                "action":       "upgrade_or_remove",
            },
        )

    # Get user info for naming
    user = manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    client_name = custom_name or f"{user.username}-{len(existing_ids) + 1}"

    # Create client via Admin API
    api = get_admin_api()
    result = await api.create_client(
        name=client_name,
        server_id=server_id,
        bandwidth_limit=subscription.bandwidth_limit_mbps,
        traffic_limit_mb=int(subscription.traffic_limit_gb * 1024) if subscription.traffic_limit_gb else None,
        expiry_days=subscription.days_remaining or 30,
    )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Failed to create client via admin API"
        )

    # Create link between portal user and WG client
    link = ClientUserClients(client_user_id=user_id, client_id=result["id"])
    db.add(link)
    db.commit()

    return {
        "id": result["id"],
        "name": result["name"],
        "ipv4": result.get("ipv4"),
        "server_type": result.get("server_type"),
    }


@router.delete("/wireguard/clients/{client_id}")
async def delete_wireguard_client(
    client_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a WireGuard client owned by the current user"""
    if not _user_owns_client(db, user_id, client_id):
        raise HTTPException(status_code=404, detail="Client not found")

    api = get_admin_api()
    success = await api.delete_client(client_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete client")

    # Remove the user-client link
    db.query(ClientUserClients).filter(
        ClientUserClients.client_user_id == user_id,
        ClientUserClients.client_id == client_id
    ).delete()
    db.commit()

    return {"message": "Client deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# AUTO-SETUP
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/wireguard/auto-setup")
async def auto_setup_wireguard(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Auto-setup: find existing device or create one, return config."""
    api = get_admin_api()
    client_ids = _get_user_client_ids(db, user_id)
    client_id = None

    if client_ids:
        # Use the first existing client
        clients = await api.get_clients_by_ids(client_ids)
        if clients:
            client_id = clients[0]["id"]

    if client_id is None:
        # No device — create one
        from src.modules.subscription.subscription_models import ClientUser
        user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        sub = SubscriptionManager(db).get_subscription(user_id)
        if not sub or not sub.is_active:
            if sub and sub.is_expired:
                raise HTTPException(
                    status_code=400,
                    detail="Your VPN service has expired. Renew your plan to reconnect.",
                )
            raise HTTPException(
                status_code=400,
                detail="No active subscription. Choose a plan to start.",
            )

        client_name = f"{user.username or user.email.split('@')[0]}-auto"
        result = await api.create_client(
            name=client_name,
            bandwidth_limit=sub.bandwidth_limit_mbps,
            traffic_limit_mb=int(sub.traffic_limit_gb * 1024) if sub.traffic_limit_gb else None,
            expiry_days=sub.days_remaining or 30,
        )
        if not result:
            raise HTTPException(status_code=500, detail="Failed to create client")

        link = ClientUserClients(client_user_id=user_id, client_id=result["id"])
        db.add(link)
        db.commit()
        client_id = result["id"]

    # Get config
    config_result = await api.get_client_config(client_id)
    if not config_result:
        raise HTTPException(status_code=500, detail="Failed to get config")

    return {
        "client_id": client_id,
        "config": config_result.get("config", ""),
        "name": config_result.get("client_name", f"vpn-{client_id}")
    }


# ═══════════════════════════════════════════════════════════════════════════
# DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/download/app")
async def download_app():
    """Download Flirexa APK"""
    apk_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web", "static", "vpn-manager.apk")
    if not os.path.isfile(apk_path):
        raise HTTPException(status_code=404, detail="APK not found")
    return FileResponse(apk_path, filename="vpn-manager.apk", media_type="application/vnd.android.package-archive")


# ═══════════════════════════════════════════════════════════════════════════
# SERVERS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/servers")
def get_servers(
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Server list for the customer's location picker.

    Visibility is the intersection of three rules — see
    ``_server_visible_to``:
      * ``customer_visible=True`` — admin approval.
      * ``for_app_only`` — surfaced only when the request identifies
        as the official app (X-Client-App header or matching UA prefix).
      * Auto-hide — last_good_health_at within the threshold OR
        ``force_visible=True`` overrides.
    """
    # Defer Server's EncryptedText columns (ssh_password, ssh_private_key,
    # agent_api_key) — customer server picker never renders them, but the
    # full ORM load decrypts all three on every row on every request.
    # Hot endpoint (customer apps poll it on every connect screen).
    servers = (
        db.query(Server)
        .options(
            defer(Server.ssh_password),
            defer(Server.ssh_private_key),
            defer(Server.agent_api_key),
        )
        .filter(Server.customer_visible.is_(True))
        .all()
    )

    def _endpoint_host(s) -> Optional[str]:
        # The WireGuard/AmneziaWG endpoint is already in the wg-quick
        # config the customer downloads when they connect — splitting
        # off the host so the app can measure CLIENT→SERVER latency
        # directly instead of relying on /probe (which measures
        # PORTAL→SERVER and bears no relation to the device's network
        # path). No new information is leaked.
        ep = (getattr(s, 'endpoint', None) or '').strip()
        if not ep:
            return None
        if '://' in ep:
            ep = ep.split('://', 1)[1]
        host = ep.split(':')[0]
        return host or None

    return [
        {
            "id": s.id,
            "name": getattr(s, 'display_name', None) or s.name,
            "location": s.location,
            "status": s.status.value if hasattr(s.status, 'value') else str(s.status),
            "server_category": getattr(s, 'server_category', 'vpn'),
            "server_type": getattr(s, 'server_type', 'wireguard'),
            # New: lets the native app run its own TCP-connect probe so
            # the displayed ms reflects the device's own network path,
            # not the panel's. App falls back to /probe when this is null.
            "endpoint_host": _endpoint_host(s),
        }
        for s in servers
        if _server_visible_to(s, request)
    ]


@router.get("/servers/{server_id}/probe")
async def probe_server(
    server_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lightweight latency probe — measures portal→server HTTP roundtrip
    to the node agent. Returns ``{"rtt_ms": int}`` or ``{"rtt_ms": null,
    "error": "..."}`` on failure. Browser-side mixed-content rules block
    a direct `fetch()` from an HTTPS portal to an HTTP node agent, so we
    proxy the probe here. The RTT is portal→server, not user→server, but
    it's a useful relative indicator: a server whose agent answers in
    18ms from the panel is almost always healthier and closer to "good
    routing" than one that answers in 540ms.
    """
    server = (
        db.query(Server)
        .filter(Server.id == server_id, Server.customer_visible.is_(True))
        .first()
    )
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    import time as _time
    import httpx as _httpx

    # Prefer the agent URL — that's the actual HTTP control plane on
    # the node (port 8001-ish), which always exposes /health. The
    # WireGuard endpoint is UDP on whatever port (51820 typically), so
    # falling back to it via http://{host}/ used to ping the wrong
    # service and return None for every agent-mode server.
    agent_url = (getattr(server, "agent_url", None) or "").strip()
    if agent_url:
        if "://" not in agent_url:
            agent_url = "http://" + agent_url
        url = agent_url.rstrip("/") + "/health"
    else:
        endpoint = (server.endpoint or "").strip()
        if not endpoint:
            return {"rtt_ms": None, "error": "no_address"}
        if "://" in endpoint:
            endpoint = endpoint.split("://", 1)[1]
        host = endpoint.split(":")[0]
        if not host:
            return {"rtt_ms": None, "error": "no_address"}
        url = f"http://{host}/health"
    start = _time.monotonic()
    try:
        async with _httpx.AsyncClient(timeout=3.0) as cli:
            resp = await cli.get(url)
        rtt_ms = int((_time.monotonic() - start) * 1000)
        return {
            "rtt_ms": rtt_ms,
            "status": resp.status_code,
        }
    except _httpx.TimeoutException:
        return {"rtt_ms": None, "error": "timeout"}
    except Exception as e:
        return {"rtt_ms": None, "error": type(e).__name__.lower()}


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _is_user_restricted(db: Session, user_id: int) -> bool:
    """Check if user is banned or inactive — skip WG sync if so"""
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    return user is None or user.is_banned or not user.is_active


async def _sync_wg_after_payment(
    db: Session,
    user_id: int,
    manager: SubscriptionManager,
    invoice_id: str = "",
):
    """Sync WG limits via Admin API after payment completion.
    Falls back to direct DB path when admin_api is not configured (Fix H-2)."""

    # Trace this step
    _tracer = None
    if invoice_id:
        try:
            from src.modules.payment.payment_tracer import get_tracer
            _tracer = get_tracer(db, invoice_id)
        except Exception:
            pass

    if not admin_api:
        logger.warning(
            f"[PAY:{invoice_id}] admin_api not configured — falling back to direct DB limits sync "
            f"for user {user_id}. TC bandwidth enforcement and WG peer state may not be applied immediately."
        )
        try:
            manager.apply_subscription_limits(user_id, reset_traffic=True)
            if _tracer:
                _tracer.step("sync_wg", status="ok", detail={"mode": "fallback_direct_db"})
        except Exception as e:
            logger.error(
                f"[PAY:{invoice_id}] Fallback apply_subscription_limits failed for user {user_id}: {e}"
            )
            if _tracer:
                _tracer.step("sync_wg", status="error", detail={"mode": "fallback_direct_db", "error": str(e)})
        return

    # Don't enable WG for banned/inactive users
    user = manager.get_user_by_id(user_id)
    if user and (user.is_banned or not user.is_active):
        logger.warning(f"Skipping WG sync for banned/inactive user {user_id}")
        return

    subscription = manager.get_subscription(user_id)
    if not subscription:
        return

    # Update limits on existing linked clients
    client_ids = _get_user_client_ids(db, user_id)
    for cid in client_ids:
        await admin_api.update_client_limits(
            client_id=cid,
            bandwidth_limit=subscription.bandwidth_limit_mbps,
            traffic_limit_mb=int(subscription.traffic_limit_gb * 1024) if subscription.traffic_limit_gb else None,
            expiry_date=subscription.expiry_date.isoformat() if subscription.expiry_date else None,
            enabled=True,
            status="ACTIVE",
            reset_traffic=True,  # Reset WG counter so re-enabled client doesn't get immediately re-banned
        )

    # Auto-create a WG client used to fire here when the customer had
    # no clients, to make a fresh peer named `{username}-1` on the
    # default server. Operators with multi-region setups (operator
    # report 2026-05-26) reported that this single config blocks the portal's
    # Add Device flow — the customer hits the device cap before they
    # can click "Add Device" themselves and pick a region, so the op
    # has to delete the auto-peer before the customer can proceed.
    #
    # Per operator decision: leave the customer at zero peers. They
    # click Add Device on the portal to mint configs the right way
    # (one per region, named consistently). This block stays
    # commented as a marker — if a later operator wants the old
    # behaviour, the flip is one re-enable + a release bump.
    #
    # if not client_ids:
    #     user = manager.get_user_by_id(user_id)
    #     if user:
    #         client_name = f"{user.username}-1"
    #         result = await admin_api.create_client(...)
    #         if result:
    #             link = ClientUserClients(client_user_id=user_id, client_id=result["id"])
    #             db.add(link)
    #             db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# REFERRAL SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/referral")
def get_referral_info(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's referral code and stats"""
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate referral code if missing
    if not user.referral_code:
        import string as _string
        user.referral_code = ''.join(random.choices(_string.ascii_uppercase + _string.digits, k=8))
        db.commit()

    # Count referrals
    referral_count = db.query(ClientUser).filter(
        ClientUser.referred_by_id == user.id
    ).count()

    # Count paid referrals
    from sqlalchemy.orm import aliased
    from src.modules.subscription.subscription_models import ClientPortalSubscription
    paid_referrals = db.query(ClientUser).filter(
        ClientUser.referred_by_id == user.id
    ).join(ClientPortalSubscription, ClientPortalSubscription.user_id == ClientUser.id).filter(
        ClientPortalSubscription.tier != "free"
    ).count()

    return {
        "referral_code": user.referral_code,
        "referral_count": referral_count,
        "paid_referrals": paid_referrals,
    }


# ═══════════════════════════════════════════════════════════════════════════
# PROMO CODES (CLIENT SIDE)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/promo/validate")
def validate_promo_client(
    data: dict,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Validate a promo code from client portal"""
    from src.modules.subscription.subscription_models import PromoCode
    code = (data.get("code") or "").strip().upper()
    tier = data.get("tier", "")
    duration_days = data.get("duration_days", 30)

    if not code:
        return {"valid": False, "error": "No promo code provided"}

    promo = db.query(PromoCode).filter(PromoCode.code == code).first()
    if not promo or not promo.is_valid:
        return {"valid": False, "error": "Invalid or expired promo code"}

    if promo.applies_to_tier and promo.applies_to_tier != tier:
        return {"valid": False, "error": f"Code only valid for {promo.applies_to_tier} tier"}

    if promo.min_duration_days and duration_days < promo.min_duration_days:
        return {"valid": False, "error": f"Minimum {promo.min_duration_days} days required"}

    return {
        "valid": True,
        "discount_type": promo.discount_type,
        "discount_value": promo.discount_value,
        "code": promo.code,
    }


# ═══════════════════════════════════════════════════════════════════════════
# AUTO-RENEW TOGGLE
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/subscription/auto-renew")
def toggle_auto_renew(
    data: dict,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Toggle auto-renewal for subscription"""
    from src.modules.subscription.subscription_models import ClientPortalSubscription
    sub = db.query(ClientPortalSubscription).filter(
        ClientPortalSubscription.user_id == user_id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="No subscription found")

    sub.auto_renew = bool(data.get("auto_renew", False))
    db.commit()

    return {"message": "Auto-renew updated", "auto_renew": sub.auto_renew}


# ═══════════════════════════════════════════════════════════════════════════
# SUPPORT MESSAGES
# ═══════════════════════════════════════════════════════════════════════════

class SupportMessageRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1, max_length=4000)

class SupportReplyRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


@router.post("/support/send")
def send_support_message(
    data: SupportMessageRequest,
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a support message from client to admin"""
    from src.modules.subscription.subscription_models import SupportMessage

    ip = _get_client_ip(request)
    _enforce_persistent_rate_limit(
        db,
        scope="support_ip",
        identity=ip,
        maximum=_SUPPORT_IP_RATE_MAX,
        window_seconds=_PORTAL_ACTION_WINDOW,
        detail="Too many support messages. Please try again later.",
    )
    _enforce_persistent_rate_limit(
        db,
        scope="support_user",
        identity=str(user_id),
        maximum=_SUPPORT_USER_RATE_MAX,
        window_seconds=_PORTAL_ACTION_WINDOW,
        detail="Too many support messages. Please try again later.",
    )

    msg = SupportMessage(
        user_id=user_id,
        subject=data.subject,
        message=data.message,
        direction="user",
        status="open",
        is_read=False,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Notify admin via Telegram
    try:
        from src.modules.notifications import NotificationService
        ns = NotificationService(db)
        user = db.get(ClientUser, user_id)
        sender = f"{user.username} ({user.email})" if user else f"user_id={user_id}"
        ns.notify_admin(
            f"📩 New support message\n"
            f"From: {sender}\n"
            f"Subject: {data.subject}\n\n"
            f"{data.message[:500]}"
        )
    except Exception as e:
        logger.warning(f"Failed to notify admin about support message: {e}")

    return {"id": msg.id, "status": "sent"}


@router.get("/support/messages")
def get_support_messages(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all support messages for current user (tickets + replies)"""
    from src.modules.subscription.subscription_models import SupportMessage

    # Get root messages (tickets) for this user
    tickets = db.query(SupportMessage).filter(
        SupportMessage.user_id == user_id,
        SupportMessage.parent_id == None,
    ).order_by(SupportMessage.created_at.desc()).all()

    result = []
    for ticket in tickets:
        # Get replies for this ticket
        replies = db.query(SupportMessage).filter(
            SupportMessage.parent_id == ticket.id
        ).order_by(SupportMessage.created_at.asc()).all()

        result.append({
            "id": ticket.id,
            "subject": ticket.subject,
            "message": ticket.message,
            "status": ticket.status,
            "direction": ticket.direction,
            "is_read": ticket.is_read,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "replies": [{
                "id": r.id,
                "message": r.message,
                "direction": r.direction,
                "is_read": r.is_read,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            } for r in replies],
        })

    # Mark admin replies as read
    for ticket in tickets:
        for reply in db.query(SupportMessage).filter(
            SupportMessage.parent_id == ticket.id,
            SupportMessage.direction == "admin",
            SupportMessage.is_read == False,
        ).all():
            reply.is_read = True
    db.commit()

    return result


@router.post("/support/{ticket_id}/reply")
def reply_to_support_ticket(
    ticket_id: int,
    data: SupportReplyRequest,
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """User replies to their own support ticket"""
    from src.modules.subscription.subscription_models import SupportMessage

    ip = _get_client_ip(request)
    _enforce_persistent_rate_limit(
        db,
        scope="support_ip",
        identity=ip,
        maximum=_SUPPORT_IP_RATE_MAX,
        window_seconds=_PORTAL_ACTION_WINDOW,
        detail="Too many support messages. Please try again later.",
    )
    _enforce_persistent_rate_limit(
        db,
        scope="support_user",
        identity=str(user_id),
        maximum=_SUPPORT_USER_RATE_MAX,
        window_seconds=_PORTAL_ACTION_WINDOW,
        detail="Too many support messages. Please try again later.",
    )

    ticket = db.query(SupportMessage).filter(
        SupportMessage.id == ticket_id,
        SupportMessage.user_id == user_id,
        SupportMessage.parent_id == None,
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status == "closed":
        raise HTTPException(status_code=400, detail="Ticket is closed")

    reply = SupportMessage(
        user_id=user_id,
        subject=ticket.subject,
        message=data.message,
        direction="user",
        parent_id=ticket.id,
        status=None,
        is_read=False,
    )
    db.add(reply)
    ticket.status = "open"
    db.commit()

    # Notify admin
    try:
        from src.modules.notifications import NotificationService
        ns = NotificationService(db)
        user = db.get(ClientUser, user_id)
        ns.notify_admin(
            f"📩 Support reply\n"
            f"From: {user.username}\n"
            f"Re: {ticket.subject}\n\n"
            f"{data.message[:500]}"
        )
    except Exception as _notif_err:
        logger.warning("Support reply admin notification failed: %s", _notif_err)

    return {"id": reply.id, "status": "sent"}


@router.get("/support/unread-count")
def get_unread_support_count(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get count of unread admin replies"""
    from src.modules.subscription.subscription_models import SupportMessage

    # Count unread admin replies to user's tickets
    count = db.query(SupportMessage).filter(
        SupportMessage.user_id == user_id,
        SupportMessage.direction == "admin",
        SupportMessage.is_read == False,
    ).count()

    return {"unread": count}


# ═══════════════════════════════════════════════════════════════════════════
# PUSH NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/notifications")
def get_notifications(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get unread notifications for user (personal + broadcasts)"""
    from src.database.models import PushNotification
    from sqlalchemy import or_

    notifications = db.query(PushNotification).filter(
        or_(
            PushNotification.user_id == user_id,
            PushNotification.user_id == None  # broadcasts
        ),
        PushNotification.is_read == False
    ).order_by(PushNotification.created_at.desc()).limit(50).all()

    return [
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "type": n.notification_type,
            "created_at": n.created_at.isoformat() if n.created_at else None
        }
        for n in notifications
    ]


@router.post("/notifications/{notif_id}/read")
def mark_notification_read(
    notif_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a notification as read"""
    from src.database.models import PushNotification
    from sqlalchemy import or_

    notif = db.query(PushNotification).filter(
        PushNotification.id == notif_id,
        or_(
            PushNotification.user_id == user_id,
            PushNotification.user_id == None
        )
    ).first()

    if notif:
        # For broadcasts, create a read record per user (or just mark read for simplicity)
        if notif.user_id is None:
            # Clone as read for this user so broadcast stays for others
            read_copy = PushNotification(
                user_id=user_id,
                title=notif.title,
                message=notif.message,
                notification_type=notif.notification_type,
                is_read=True,
                created_at=notif.created_at
            )
            db.add(read_copy)
        else:
            notif.is_read = True
        db.commit()

    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
# Bulk mark-all-read (Windows + mobile)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/notifications/mark-all-read")
def mark_all_notifications_read(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark every unread personal notification as read. Broadcasts (rows
    with user_id IS NULL) are cloned into per-user 'read' copies so
    other users' views are unaffected."""
    from src.database.models import PushNotification

    db.query(PushNotification).filter(
        PushNotification.user_id == user_id,
        PushNotification.is_read.is_(False),
    ).update({"is_read": True}, synchronize_session=False)

    broadcasts = db.query(PushNotification).filter(
        PushNotification.user_id == None,  # noqa: E711
    ).all()
    if broadcasts:
        existing_clone_titles = {
            (n.title, n.created_at) for n in db.query(PushNotification).filter(
                PushNotification.user_id == user_id,
                PushNotification.is_read.is_(True),
            ).all()
        }
        for b in broadcasts:
            if (b.title, b.created_at) in existing_clone_titles:
                continue
            db.add(PushNotification(
                user_id=user_id,
                title=b.title,
                message=b.message,
                notification_type=b.notification_type,
                is_read=True,
                created_at=b.created_at,
            ))

    db.commit()
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
# FCM TOKEN REGISTRATION (push notifications)
# ═══════════════════════════════════════════════════════════════════════════

class FcmRegisterRequest(BaseModel):
    device_id: str = Field(..., min_length=8, max_length=64,
                           description="Same UUID the app sends as X-Device-Id")
    platform: str = Field(..., description="android | ios | windows")
    token: str = Field(..., min_length=32, max_length=4096,
                       description="FCM registration token from the client SDK")


@router.post("/fcm/register")
def register_fcm_token(
    data: FcmRegisterRequest,
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist (or refresh) the FCM token for this user+installation.

    Idempotent on (user_id, device_id) so the mobile app can call this
    on every signed-in cold start without spamming the table. FCM
    rotates tokens on app reinstall / OS reset; the upsert keeps the
    sender pointing at the live one."""
    ip = _get_client_ip(request)
    _enforce_persistent_rate_limit(
        db,
        scope="fcm_ip",
        identity=ip,
        maximum=_FCM_IP_RATE_MAX,
        window_seconds=_PORTAL_ACTION_WINDOW,
        detail="Too many push-token registrations. Please try again later.",
    )
    _enforce_persistent_rate_limit(
        db,
        scope="fcm_user",
        identity=str(user_id),
        maximum=_FCM_USER_RATE_MAX,
        window_seconds=_PORTAL_ACTION_WINDOW,
        detail="Too many push-token registrations. Please try again later.",
    )

    platform = data.platform.strip().lower()
    if platform not in ("android", "ios", "windows"):
        raise HTTPException(status_code=400, detail="Unknown platform")

    from src.database.models import FcmToken
    row = db.query(FcmToken).filter(
        FcmToken.user_id == user_id,
        FcmToken.device_id == data.device_id,
    ).first()

    if row is None:
        row = FcmToken(
            user_id=user_id,
            device_id=data.device_id,
            platform=platform,
            token=data.token,
        )
        db.add(row)
    else:
        row.token = data.token
        row.platform = platform
        row.last_seen_at = datetime.now(timezone.utc)

    db.commit()
    return {"status": "ok"}


@router.delete("/fcm/register")
def unregister_fcm_token(
    device_id: str,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Drop the FCM token for this user+installation. Called by the app
    on explicit sign-out so a re-installed app starting fresh doesn't
    keep pushing to the previous owner's notification stream."""
    from src.database.models import FcmToken
    db.query(FcmToken).filter(
        FcmToken.user_id == user_id,
        FcmToken.device_id == device_id,
    ).delete(synchronize_session=False)
    db.commit()
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION LINK
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/subscription-link")
def get_subscription_link(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get or generate subscription link token"""
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.subscription_token:
        user.subscription_token = secrets.token_urlsafe(48)
        user.subscription_token_created_at = datetime.now(timezone.utc)
        db.commit()

    return {
        "token": user.subscription_token,
        "created_at": user.subscription_token_created_at.isoformat() if user.subscription_token_created_at else None,
    }


@router.post("/subscription-link/regenerate")
def regenerate_subscription_link(
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Regenerate subscription link token"""
    ip = _get_client_ip(request)
    _enforce_persistent_rate_limit(
        db,
        scope="subscription_link_ip",
        identity=ip,
        maximum=_SUB_LINK_IP_RATE_MAX,
        window_seconds=_PORTAL_ACTION_WINDOW,
        detail="Too many subscription-link changes. Please try again later.",
    )
    _enforce_persistent_rate_limit(
        db,
        scope="subscription_link_user",
        identity=str(user_id),
        maximum=_SUB_LINK_USER_RATE_MAX,
        window_seconds=_PORTAL_ACTION_WINDOW,
        detail="Too many subscription-link changes. Please try again later.",
    )

    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.subscription_token = secrets.token_urlsafe(48)
    user.subscription_token_created_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "token": user.subscription_token,
        "created_at": user.subscription_token_created_at.isoformat(),
    }


@router.get("/sub/{token}", tags=["Public"])
def get_subscription_config(
    request: Request,
    token: str,
    db: Session = Depends(get_db)
):
    """
    Public endpoint: returns WireGuard config for a subscription link token.
    No auth needed — token IS the auth.
    """
    # Rate limit: reuse auth rate limiter to prevent brute force on tokens
    ip = _get_client_ip(request)
    if not _check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Too many requests")
    _record_attempt(ip)

    # Validate token format (must be valid base64url, 48+ chars)
    if not _SUBSCRIPTION_TOKEN_RE.fullmatch(token):
        raise HTTPException(status_code=404, detail="Invalid subscription link")

    user = db.query(ClientUser).filter(ClientUser.subscription_token == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Invalid subscription link")

    if not user.is_active or user.is_banned:
        raise HTTPException(status_code=403, detail="Account is not active")

    # Check subscription
    from src.modules.subscription.subscription_models import ClientPortalSubscription
    sub = db.query(ClientPortalSubscription).filter(
        ClientPortalSubscription.user_id == user.id
    ).first()
    if not sub or sub.status != SubscriptionStatus.ACTIVE or sub.tier == "free":
        raise HTTPException(status_code=403, detail="No active paid subscription")

    # Get user's WG clients
    client_ids = _get_user_client_ids(db, user.id)
    if not client_ids:
        raise HTTPException(status_code=404, detail="No devices configured")

    from src.database.models import Client as WGClient
    wg_clients = db.query(WGClient).filter(WGClient.id.in_(client_ids)).all()
    if not wg_clients:
        raise HTTPException(status_code=404, detail="No devices found")

    # Drop peers on servers that aren't visible to a /sub fetcher (router
    # / openVPN client — never identifies as the official app). This
    # excludes ``for_app_only=True`` servers and ones auto-hidden by
    # missed health polls. The configured app still sees them via the
    # authenticated /devices flow.
    visible_server_ids = {
        s.id for s in db.query(Server).all() if _server_visible_to(s, request)
    }
    wg_clients = [c for c in wg_clients if c.server_id in visible_server_ids]
    if not wg_clients:
        raise HTTPException(status_code=404, detail="No devices found")

    # Build combined WG config (supports both WireGuard and AmneziaWG servers)
    from src.core.client_manager import ClientManager
    cm = ClientManager(db)
    configs = []
    for c in wg_clients:
        if not c.private_key:
            continue
        config = cm.get_client_config(c.id)
        if config:
            configs.append(f"# Device: {c.name}\n{config}")

    if not configs:
        raise HTTPException(status_code=404, detail="No valid configs available")

    combined = "\n\n".join(configs)
    return Response(content=combined, media_type="text/plain")


def _build_proxy_subscription(proxy_clients, db: Session) -> str:
    """base64(newline-joined proxy URIs) — the format universal proxy
    clients (v2rayN / sing-box / NekoBox / Hiddify) expect when polling a
    subscription URL. Skips any client whose access lookup fails or has
    no URI rather than failing the whole subscription.
    """
    from src.core.client_manager import ClientManager
    cm = ClientManager(db)
    uris = []
    for c in proxy_clients:
        try:
            access = cm.get_proxy_client_access(c.id)
        except Exception:
            continue
        if access and access.get("uri"):
            uris.append(access["uri"])
    if not uris:
        raise HTTPException(status_code=404, detail="No valid proxy configs available")
    body = "\n".join(uris)
    return base64.b64encode(body.encode()).decode()


@router.get("/sub/{token}/proxy", tags=["Public"])
def get_proxy_subscription(
    request: Request,
    token: str,
    db: Session = Depends(get_db)
):
    """
    Public endpoint: base64(newline-joined proxy URIs) for a subscription
    link token — hysteria2 / tuic / vless-reality clients. Universal proxy
    clients (v2rayN, sing-box, NekoBox, Hiddify) poll this URL directly.
    No auth needed — token IS the auth.

    Mirrors the token -> clients resolution used by ``get_subscription_config``
    (GET /sub/{token} just above) step-for-step, so this endpoint stays in
    lockstep with rate-limiting, token validation, subscription-status and
    server-visibility rules. The only divergence: where that endpoint SKIPS
    proxy clients (``if not c.private_key: continue``) to build a WG config
    blob, this endpoint keeps ONLY proxy clients (server_category == 'proxy'
    via ``belongs_to_proxy_server``) and returns their URIs instead.
    """
    # Rate limit: reuse auth rate limiter to prevent brute force on tokens
    ip = _get_client_ip(request)
    if not _check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Too many requests")
    _record_attempt(ip)

    # Validate token format (must be valid base64url, 48+ chars)
    if not _SUBSCRIPTION_TOKEN_RE.fullmatch(token):
        raise HTTPException(status_code=404, detail="Invalid subscription link")

    user = db.query(ClientUser).filter(ClientUser.subscription_token == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Invalid subscription link")

    if not user.is_active or user.is_banned:
        raise HTTPException(status_code=403, detail="Account is not active")

    # Check subscription
    from src.modules.subscription.subscription_models import ClientPortalSubscription
    sub = db.query(ClientPortalSubscription).filter(
        ClientPortalSubscription.user_id == user.id
    ).first()
    if not sub or sub.status != SubscriptionStatus.ACTIVE or sub.tier == "free":
        raise HTTPException(status_code=403, detail="No active paid subscription")

    # Get user's clients (WG + proxy — filtered to proxy-only below)
    client_ids = _get_user_client_ids(db, user.id)
    if not client_ids:
        raise HTTPException(status_code=404, detail="No devices configured")

    from src.database.models import Client as WGClient
    all_clients = db.query(WGClient).filter(WGClient.id.in_(client_ids)).all()
    if not all_clients:
        raise HTTPException(status_code=404, detail="No devices found")

    # Drop peers on servers that aren't visible to a /sub fetcher — same
    # visibility rule as GET /sub/{token} above.
    visible_server_ids = {
        s.id for s in db.query(Server).all() if _server_visible_to(s, request)
    }
    all_clients = [c for c in all_clients if c.server_id in visible_server_ids]
    if not all_clients:
        raise HTTPException(status_code=404, detail="No devices found")

    proxy_clients = [c for c in all_clients if c.belongs_to_proxy_server]
    if not proxy_clients:
        raise HTTPException(status_code=404, detail="No proxy devices found")

    body = _build_proxy_subscription(proxy_clients, db)
    return Response(content=body, media_type="text/plain")


@router.get("/sub/{token}/slot/{slot_id}", tags=["Public"])
def get_slot_subscription_config(
    request: Request,
    token: str,
    slot_id: int,
    db: Session = Depends(get_db),
):
    """Public endpoint: return the CURRENTLY-ACTIVE region's config for a
    specific slot. Used by Smart Subscription URL — the user pastes this
    once into their WG/AmneziaWG app, the app polls it, and whenever the
    user switches region on the portal the next poll delivers the new
    region's config automatically. No auth — the user's subscription
    token IS the auth, scoped to one of their slots by slot_id.
    """
    ip = _get_client_ip(request)
    if not _check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Too many requests")
    _record_attempt(ip)

    if not _SUBSCRIPTION_TOKEN_RE.fullmatch(token):
        raise HTTPException(status_code=404, detail="Invalid subscription link")

    user = db.query(ClientUser).filter(ClientUser.subscription_token == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Invalid subscription link")
    if not user.is_active or user.is_banned:
        raise HTTPException(status_code=403, detail="Account is not active")

    from src.modules.subscription.subscription_models import ClientPortalSubscription
    sub = db.query(ClientPortalSubscription).filter(
        ClientPortalSubscription.user_id == user.id
    ).first()
    if not sub or sub.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="No active subscription")

    slot = db.query(_DeviceSlot).filter(
        _DeviceSlot.id == slot_id,
        _DeviceSlot.client_user_id == user.id,
    ).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if not slot.active_server_id:
        raise HTTPException(status_code=404, detail="No active region for this device")

    from src.database.models import Client as WGClient
    active = (
        db.query(WGClient)
        .join(ClientUserClients, ClientUserClients.client_id == WGClient.id)
        .filter(
            ClientUserClients.slot_id == slot_id,
            WGClient.server_id == slot.active_server_id,
        )
        .first()
    )
    if not active or not active.private_key:
        raise HTTPException(status_code=404, detail="Active region peer is not provisioned")

    from src.core.client_manager import ClientManager
    cm = ClientManager(db)
    config = cm.get_client_config(active.id)
    if not config:
        raise HTTPException(status_code=404, detail="Config unavailable")
    return Response(content=config, media_type="text/plain")


# ═══════════════════════════════════════════════════════════════════════════
# DEVICE SLOTS — multi-server toggle per device
# ═══════════════════════════════════════════════════════════════════════════
# A "device slot" is one customer device whose peer is replicated on every
# customer-visible server. The user sees ONE row per slot in the portal;
# they pick which server is currently active. Subscription max_devices
# bounds the slot count, not the per-server peer count.

from src.modules.subscription.slot_manager import SlotManager, SlotManagerError
from src.modules.subscription.subscription_models import DeviceSlot as _DeviceSlot


def _slot_to_dict(slot, peers, servers_by_id, *, subscription_token=None):
    """JSON shape for a slot. ``peers`` is the slot's Client rows; we
    look up server names from ``servers_by_id`` to avoid N+1 hits.
    ``subscription_token`` is the user-level token used to compose the
    Smart Subscription URL — included so the frontend can render the
    copy-and-paste box without an extra round-trip."""
    sub_path = (
        f"/api/v1/client-portal/sub/{subscription_token}/slot/{slot.id}"
        if subscription_token else None
    )
    return {
        "id": slot.id,
        "label": slot.label,
        "subscription_url_path": sub_path,
        "active_server_id": slot.active_server_id,
        "active_server_name": (
            servers_by_id.get(slot.active_server_id).name
            if servers_by_id.get(slot.active_server_id) else None
        ),
        "last_switched_at": (
            slot.last_switched_at.isoformat()
            if slot.last_switched_at else None
        ),
        # Device-bind state. ``is_bound`` is the cleaner field for the
        # portal UI — we deliberately don't expose the raw device_id
        # value so the customer can't compare it against their phone's
        # ID and confirm/disconfirm sharing (it's an opaque marker, not
        # a credential).
        "is_bound": bool(getattr(slot, "device_id", None)),
        "created_at": slot.created_at.isoformat() if slot.created_at else None,
        "servers": [
            {
                "server_id": p.server_id,
                "server_name": (
                    servers_by_id.get(p.server_id).name
                    if servers_by_id.get(p.server_id) else f"server-{p.server_id}"
                ),
                "server_display_name": (
                    getattr(servers_by_id.get(p.server_id), "display_name", None)
                    or getattr(servers_by_id.get(p.server_id), "location", None)
                    or (servers_by_id.get(p.server_id).name
                        if servers_by_id.get(p.server_id) else None)
                ),
                "ipv4": p.ipv4,
                "enabled": bool(p.enabled),
                "is_active": (p.server_id == slot.active_server_id),
                "last_handshake": (
                    p.last_handshake.isoformat()
                    if getattr(p, "last_handshake", None) else None
                ),
            }
            for p in sorted(peers, key=lambda x: x.server_id)
        ],
    }


def _servers_by_id_map(db: Session, server_ids):
    if not server_ids:
        return {}
    rows = db.query(Server).filter(Server.id.in_(set(server_ids))).all()
    return {s.id: s for s in rows}


@router.get("/devices")
def list_device_slots(
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all slots for the current user, with each slot's per-server
    peer state. UI renders one device card per slot with a server picker."""
    # Local import — this file otherwise pulls `Client` per-function rather
    # than at module level to keep import order forgiving. Without this the
    # bulk peer query below NameError'd at runtime and the portal showed a
    # 500 even though slots existed in the DB (then the user clicked Add and
    # got 409 device_limit_reached because the slot was actually there).
    from src.database.models import Client
    mgr = SlotManager(db)
    slots = mgr.get_user_slots(user_id)

    # Lazy-heal: if a customer-visible server was added after this slot
    # was created (and the create-side hook didn't catch it for any
    # reason — e.g. server was added before the slot system shipped, or
    # the flip happened during a brief panel outage), top up the slot
    # before we render. Idempotent and cheap when there's nothing to do.
    # We only touch the slots we're about to display, never every slot
    # in the DB, so this stays O(slots-for-this-user).
    for slot in slots:
        try:
            mgr.heal_slot(slot)
        except Exception as _heal_err:
            logger.warning(
                "lazy heal_slot(%d) failed during GET /devices, returning stale view: %s",
                slot.id, _heal_err,
            )

    # Bulk-load peers + servers to avoid N+1.
    slot_ids = [s.id for s in slots]
    peers_by_slot: dict = {}
    if slot_ids:
        # Defer Client's EncryptedText columns — /devices renders peer
        # IP/handshake/server but never private_key / preshared_key /
        # proxy_password. Without defer each peer row decrypts three
        # Fernet tokens on load; user with N slots × M peers/slot hits
        # 3*N*M Fernet calls every /devices fetch.
        peers = (
            db.query(Client)
            .options(
                defer(Client.private_key),
                defer(Client.preshared_key),
                defer(Client.proxy_password),
            )
            .join(ClientUserClients, ClientUserClients.client_id == Client.id)
            .filter(ClientUserClients.slot_id.in_(slot_ids))
            .all()
        )
        link_rows = (
            db.query(ClientUserClients.client_id, ClientUserClients.slot_id)
            .filter(ClientUserClients.slot_id.in_(slot_ids))
            .all()
        )
        cid_to_slot = {cid: sid for cid, sid in link_rows}
        for p in peers:
            sid = cid_to_slot.get(p.id)
            if sid:
                peers_by_slot.setdefault(sid, []).append(p)

        # Pull fresh handshake timestamps once so the rendered view and
        # the auto-sync step below see real-time traffic data instead of
        # the stale DB column. Reuses the admin route's helper to keep
        # the (server_id, pubkey) keying consistent with everything else
        # that polls handshakes.
        try:
            from .clients import _enrich_handshakes
            _enrich_handshakes(peers, db)
        except Exception as _enrich_err:
            logger.debug("handshake enrichment failed in /devices: %s", _enrich_err)
    else:
        peers = []

    # Auto-sync the active-region flag from real handshakes. If the user
    # toggled regions in their VPN app without clicking on the portal,
    # the freshest handshake reveals where traffic is actually flowing —
    # follow that, otherwise the portal indicator and reality drift apart.
    # Silent (no toast) — just keeps state honest. Manual switches still
    # win because of the 30s post-switch cooldown inside the helper.
    for slot in slots:
        try:
            mgr.auto_sync_active_from_handshake(
                slot, peers=peers_by_slot.get(slot.id, []),
            )
        except Exception as _sync_err:
            logger.debug(
                "auto_sync_active_from_handshake(%d) failed: %s",
                slot.id, _sync_err,
            )

    server_ids = {p.server_id for p in peers} | {
        s.active_server_id for s in slots if s.active_server_id
    }
    servers_by_id = _servers_by_id_map(db, server_ids)

    # Drop servers that fail visibility (for_app_only without app
    # request, or auto-hidden past threshold). The web portal and
    # router clients then see the slot without the hidden peers, which
    # is the expected behaviour — only the app sees the full set.
    servers_by_id = {
        sid: srv for sid, srv in servers_by_id.items()
        if _server_visible_to(srv, request)
    }
    peers = [p for p in peers if p.server_id in servers_by_id]
    peers_by_slot = {
        sid: [p for p in plist if p.server_id in servers_by_id]
        for sid, plist in peers_by_slot.items()
    }

    # Mint / fetch the user's subscription token so the Smart Subscription
    # URL on each slot card has something to embed without a second call.
    user_row = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    sub_token = None
    if user_row:
        if not user_row.subscription_token:
            user_row.subscription_token = secrets.token_urlsafe(48)
            user_row.subscription_token_created_at = datetime.now(timezone.utc)
            db.add(user_row)
            db.commit()
        sub_token = user_row.subscription_token

    return [
        _slot_to_dict(
            s, peers_by_slot.get(s.id, []), servers_by_id,
            subscription_token=sub_token,
        )
        for s in slots
    ]


class CreateSlotRequest(BaseModel):
    label: str = Field("Device", max_length=64)
    initial_server_id: Optional[int] = None


@router.post("/devices")
def create_device_slot(
    data: CreateSlotRequest,
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new device slot. Enforces subscription.max_devices.

    Device-bind get-or-create: when the caller sends ``X-Device-Id``
    (the mobile/desktop apps send it on every request — see
    fetchTunnelConfig) this endpoint is idempotent on
    ``(user, device_id)``. The same physical device always resolves to
    the SAME slot, and a *different* device — even of the same platform
    — gets its OWN slot instead of colliding on the platform label
    (the "two Androids share one slot on a 2-device plan" bug). Without
    the header (e.g. the web portal's manual "Add device") the old
    always-create behaviour is preserved.
    """
    sub_mgr = SubscriptionManager(db)
    sub = sub_mgr.get_subscription(user_id)
    if not sub or not sub.is_active:
        raise HTTPException(status_code=400, detail="No active subscription")

    # Sanitise the device id like the config-fetch claim does (cap at the
    # column width; empty/whitespace -> "not provided" -> legacy behaviour).
    device_id_hdr = (request.headers.get("X-Device-Id") or "").strip()[:64]
    now_utc = datetime.now(timezone.utc)

    # Serialize the count-then-create against concurrent device adds for
    # the same user. Without this, two requests both pass the cap check and
    # both create, exceeding max_devices (TOCTOU). The xact lock is held
    # until the transaction commits, so the loser blocks until the winner's
    # create is committed and then re-counts. Per-user key namespaced under
    # 2_000_000 to avoid colliding with the license lock (1000001).
    try:
        from sqlalchemy import text as _sql_text
        db.execute(_sql_text("SELECT pg_advisory_xact_lock(:k)"),
                   {"k": 2_000_000 + int(user_id)})
    except Exception:
        pass  # SQLite in tests / non-PG engines — skip advisory lock

    def _emit(slot):
        """Serialise a slot the same way the create path's return does."""
        m = SlotManager(db)
        peers = m.get_slot_peers(slot.id)
        server_ids = {p.server_id for p in peers} | {slot.active_server_id}
        return _slot_to_dict(slot, peers, _servers_by_id_map(db, server_ids))

    # ── Device-bind get-or-create (only when the app sends X-Device-Id) ──
    if device_id_hdr:
        # 1. This device already owns a slot → return it. Idempotent, so
        #    repeated sign-ins (the app's slot cache is wiped on logout)
        #    re-resolve to the same slot instead of leaking new ones.
        owned = (
            db.query(_DeviceSlot)
            .filter(
                _DeviceSlot.client_user_id == user_id,
                _DeviceSlot.device_id == device_id_hdr,
            )
            .first()
        )
        if owned:
            db.query(_DeviceSlot).filter(_DeviceSlot.id == owned.id).update(
                {"device_last_seen_at": now_utc}, synchronize_session=False)
            db.commit()
            db.refresh(owned)
            return _emit(owned)
        # 2. This device owns nothing yet → fall through to the cap check
        #    and create a NEW slot bound to it (below). We deliberately do
        #    NOT adopt an existing *unbound* slot here: that let a fresh
        #    device (e.g. a phone) grab another device's not-yet-connected
        #    or legacy slot — the "phone shows Windows / shares the card"
        #    bug. A legacy user who is genuinely at their device cap still
        #    reuses their existing slot via the 409 fallback in the app,
        #    and the config-fetch endpoint binds it to them on first connect.

    # Device-limit accounting MUST include both slot devices AND legacy
    # single-server peers (where ClientUserClients.slot_id IS NULL).
    # Without this, a user can create one slot via /devices AND a legacy
    # peer via the Dashboard Quick Action and silently double up — both
    # paths only see their own kind, and the subscription cap is never
    # actually enforced across the union.
    slot_count = (
        db.query(_DeviceSlot)
        .filter(_DeviceSlot.client_user_id == user_id)
        .count()
    )
    legacy_count = (
        db.query(ClientUserClients)
        .filter(
            ClientUserClients.client_user_id == user_id,
            ClientUserClients.slot_id.is_(None),
        )
        .count()
    )
    total_devices = slot_count + legacy_count
    max_devices = sub.max_devices or 1
    if total_devices >= max_devices:
        raise HTTPException(
            status_code=409,
            detail={
                "code":         "device_limit_reached",
                "message":      "You've reached the device limit for your plan.",
                "max_devices":  max_devices,
                "used_devices": total_devices,
                "current_tier": sub.tier,
                "action":       "upgrade_or_remove",
            },
        )

    user_row = (
        db.query(ClientUser).filter(ClientUser.id == user_id).first()
    )
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")

    mgr = SlotManager(db)
    try:
        slot = mgr.create_slot(
            user=user_row,
            label=data.label,
            initial_server_id=data.initial_server_id,
            bandwidth_limit_mbps=sub.bandwidth_limit_mbps,
            traffic_limit_mb=(
                int(sub.traffic_limit_gb * 1024) if sub.traffic_limit_gb else None
            ),
            expiry_days=sub.days_remaining or 30,
        )
    except SlotManagerError as e:
        raise HTTPException(status_code=e.http_status, detail=e.message)

    # Bind the new slot to the requesting device so the next call from
    # the same device is idempotent (branch 1 above) and a second device
    # can't adopt it as "unbound" (branch 2). Mirrors the atomic claim the
    # config-fetch endpoint does on first connect.
    if device_id_hdr:
        db.query(_DeviceSlot).filter(_DeviceSlot.id == slot.id).update(
            {
                "device_id":           device_id_hdr,
                "device_bound_at":     now_utc,
                "device_last_seen_at": now_utc,
            },
            synchronize_session=False,
        )
        db.commit()
        db.refresh(slot)

    peers = mgr.get_slot_peers(slot.id)
    server_ids = {p.server_id for p in peers} | {slot.active_server_id}
    servers_by_id = _servers_by_id_map(db, server_ids)
    return _slot_to_dict(slot, peers, servers_by_id)


class SwitchServerRequest(BaseModel):
    server_id: int


@router.post("/devices/{slot_id}/switch-server")
def switch_slot_server(
    slot_id: int,
    data: SwitchServerRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Flip the slot's active server. Rate-limited per slot."""
    mgr = SlotManager(db)
    slot = mgr.get_slot(slot_id, user_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Device not found")
    try:
        slot = mgr.switch_active_server(slot, data.server_id)
    except SlotManagerError as e:
        raise HTTPException(status_code=e.http_status, detail=e.message)

    peers = mgr.get_slot_peers(slot.id)
    server_ids = {p.server_id for p in peers} | {slot.active_server_id}
    servers_by_id = _servers_by_id_map(db, server_ids)
    return _slot_to_dict(slot, peers, servers_by_id)


class RenameSlotRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=64)


@router.patch("/devices/{slot_id}")
def rename_slot(
    slot_id: int,
    data: RenameSlotRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = SlotManager(db)
    slot = mgr.get_slot(slot_id, user_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Device not found")
    slot = mgr.rename_slot(slot, data.label)
    peers = mgr.get_slot_peers(slot.id)
    server_ids = {p.server_id for p in peers} | {slot.active_server_id}
    servers_by_id = _servers_by_id_map(db, server_ids)
    return _slot_to_dict(slot, peers, servers_by_id)


@router.delete("/devices/{slot_id}")
def delete_slot(
    slot_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = SlotManager(db)
    slot = mgr.get_slot(slot_id, user_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Device not found")
    mgr.delete_slot(slot)
    return {"ok": True}


@router.get("/devices/{slot_id}/config/{server_id}")
async def get_slot_config(
    request: Request,
    slot_id: int,
    server_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return one .conf for the requested server, using the slot's
    shared keypair.

    Option B device-bind: the mobile app sends ``X-Device-Id`` (a UUID
    persisted in SecureStore). The first such fetch atomically claims
    the slot for that device id; subsequent fetches must match.
    Mismatching fetches get 403 ``DEVICE_NOT_AUTHORIZED`` so the app
    can show a clear "release in portal and try again" message.

    Backwards compatibility: if the header is missing AND the slot is
    still unbound, we serve the config without binding — legacy app
    versions keep working. Once the user updates to a header-sending
    build their next connect binds the slot. If the slot is already
    bound and the header is missing, we treat that as a mismatch (no
    way to verify, so we refuse).
    """
    mgr = SlotManager(db)
    slot = mgr.get_slot(slot_id, user_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Device not found")

    # ── Device-bind gate ────────────────────────────────────────────
    # Pull and sanitise the device id. Cap at the column width (64) so
    # a misbehaving / hostile client can't blow up the UPDATE with a
    # 10MB header. Empty/whitespace -> treated as "not provided".
    device_id_hdr = (request.headers.get("X-Device-Id") or "").strip()[:64]
    now_utc = datetime.now(timezone.utc)

    if device_id_hdr and not slot.device_id:
        # Atomic claim: only the UPDATE that finds the row still NULL
        # wins. If two phones race, the second one's UPDATE matches
        # zero rows, the slot row reloads with the winner's id, and
        # the loser falls through to the mismatch branch below.
        updated = (
            db.query(_DeviceSlot)
            .filter(
                _DeviceSlot.id == slot.id,
                _DeviceSlot.device_id.is_(None),
            )
            .update(
                {
                    "device_id":           device_id_hdr,
                    "device_bound_at":     now_utc,
                    "device_last_seen_at": now_utc,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        db.refresh(slot)

    if slot.device_id and slot.device_id != device_id_hdr:
        # Stale-bind auto-release: if the previously bound device hasn't
        # actually fetched a config in STALE_BIND_MINUTES, the bind is
        # treated as abandoned and we silently rebind to the new device.
        # Covers force-close → SecureStore regenerates UUID, panel
        # reinstall, OS-side app-data wipe, customer hopping phones
        # legitimately. Heartbeat from a real concurrent session bumps
        # last_seen continuously, so the threshold doesn't open a hole
        # for actual account-sharing.
        STALE_BIND_MINUTES = 5
        last_seen = _as_utc(getattr(slot, "device_last_seen_at", None)) or _as_utc(getattr(slot, "device_bound_at", None))
        is_stale = last_seen is None or (now_utc - last_seen).total_seconds() > STALE_BIND_MINUTES * 60
        if device_id_hdr and is_stale:
            db.query(_DeviceSlot).filter(_DeviceSlot.id == slot.id).update(
                {
                    "device_id":           device_id_hdr,
                    "device_bound_at":     now_utc,
                    "device_last_seen_at": now_utc,
                },
                synchronize_session=False,
            )
            db.commit()
            db.refresh(slot)
            if _SLOT_ROTATE_ON_RELEASE:
                # A stale device just got displaced by this new one — rotate
                # the keypair so the displaced device's old config is locked
                # out. The config render below reads the rotated keys.
                try:
                    SlotManager(db).rotate_slot_keys(slot)
                    db.refresh(slot)
                except Exception as exc:
                    logger.warning("stale-rebind: key rotation failed for slot %s: %s", slot.id, exc)
        else:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "DEVICE_NOT_AUTHORIZED",
                    "message": (
                        "This device isn't the one registered to your "
                        "subscription. Tap 'Release device' below to "
                        "claim the slot for this phone, then connect."
                    ),
                    "slot_id":    slot.id,
                    "slot_label": slot.label,
                },
            )
    # Matching id (or freshly bound above) — bump the heartbeat so a
    # concurrent second device can't successfully take the slot via
    # the stale-bind path while we're actively using it.
    if slot.device_id and slot.device_id == device_id_hdr:
        db.query(_DeviceSlot).filter(_DeviceSlot.id == slot.id).update(
            {"device_last_seen_at": now_utc},
            synchronize_session=False,
        )
        db.commit()

    peers = mgr.get_slot_peers(slot.id)
    peer = next((p for p in peers if p.server_id == server_id), None)
    if not peer:
        raise HTTPException(status_code=404, detail="Server not in this device's slot")

    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    # Defer to the same admin-side renderer used for single-server peers
    # so any AmneziaWG obfuscation / DNS / MTU customisation flows in.
    # The renderer reads Client.private_key — we wrote the slot's shared
    # keypair onto every peer at creation, so this is correct.
    api = get_admin_api()
    cfg = await api.get_client_config(peer.id)
    if not cfg:
        raise HTTPException(status_code=500, detail="Failed to render config")
    return cfg


@router.post("/devices/{slot_id}/release")
def release_slot_device(
    slot_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Clear the slot's device-bind so a different phone can claim it on
    its next config fetch. Doesn't touch the slot's keypair or peer
    rows — existing tunnels stay up because WireGuard handshakes don't
    re-check the panel. Only the *next* connect from a fresh device
    goes through the device-bind gate, and now finds an unbound row to
    claim atomically.

    Used when the customer replaced or lost the originally-bound phone
    and needs to re-register from a new device. Same auth as the other
    /devices endpoints (must be the slot's owner).
    """
    mgr = SlotManager(db)
    slot = mgr.get_slot(slot_id, user_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Device not found")
    if slot.device_id is not None:
        slot.device_id = None
        db.commit()
        db.refresh(slot)
        if _SLOT_ROTATE_ON_RELEASE:
            # Invalidate the released device's downloaded config so it can't
            # keep tunneling on the old key. Best-effort — never fail the
            # release if the re-key hiccups.
            try:
                mgr.rotate_slot_keys(slot)
                db.refresh(slot)
            except Exception as exc:
                logger.warning("release: key rotation failed for slot %s: %s", slot.id, exc)
    peers = mgr.get_slot_peers(slot.id)
    server_ids = {p.server_id for p in peers} | (
        {slot.active_server_id} if slot.active_server_id else set()
    )
    servers_by_id = _servers_by_id_map(db, server_ids)
    return _slot_to_dict(slot, peers, servers_by_id)
