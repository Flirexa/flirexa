"""Authentication primitives shared by the client-portal routes.

Browser sessions use short HttpOnly access cookies plus rotating hash-only
refresh families and CSRF. Released native clients keep the Bearer contract.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import secrets
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.modules.subscription.subscription_models import (
    ClientRefreshToken,
    ClientUser,
)
from src.modules.subscription.subscription_manager import SubscriptionManager


_portal_fallback = ""
try:
    with open("/etc/machine-id", "r") as machine_id_file:
        _portal_fallback = hashlib.sha256(
            f"vpnmanager-portal-jwt-{machine_id_file.read().strip()}".encode()
        ).hexdigest()
except Exception:
    _portal_fallback = hashlib.sha256(
        b"vpnmanager-portal-fallback-key"
    ).hexdigest()

JWT_SECRET = os.getenv("JWT_SECRET", _portal_fallback)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "2160"))
PORTAL_COOKIE_SECURE = os.getenv(
    "PORTAL_COOKIE_SECURE", "true"
).strip().lower() in ("1", "true", "yes")


def _bounded_positive_int(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if 1 <= value <= maximum else default


PORTAL_ACCESS_TOKEN_MINUTES = _bounded_positive_int(
    "PORTAL_ACCESS_TOKEN_MINUTES", 15, 1440
)
PORTAL_REFRESH_TOKEN_DAYS = _bounded_positive_int(
    "PORTAL_REFRESH_TOKEN_DAYS", 30, 365
)

security = HTTPBearer(auto_error=False)

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
