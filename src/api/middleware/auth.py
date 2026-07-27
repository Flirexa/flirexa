"""
Flirexa API Authentication Middleware
JWT-based admin authentication
"""

from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from sqlalchemy.orm import Session
import bcrypt
import os
import hashlib
import json as _json
import logging

from src.database.connection import get_db

logger = logging.getLogger(__name__)


# Configuration
_secret_fallback = ""
try:
    with open("/etc/machine-id", "r", encoding="utf-8") as f:
        _secret_fallback = hashlib.sha256(
            f"vpnmanager-admin-jwt-{f.read().strip()}".encode()
        ).hexdigest()
except Exception:
    _secret_fallback = hashlib.sha256(b"vpnmanager-admin-fallback-key").hexdigest()
SECRET_KEY = os.getenv("SECRET_KEY", _secret_fallback)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # 30 minutes
REFRESH_TOKEN_EXPIRE_DAYS = 7    # 7 days

# HTTP Bearer scheme (auto_error=False so we handle 401 ourselves)
security = HTTPBearer(auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token (long-lived)"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_refresh_token(token: str) -> dict:
    """Verify a refresh token and return its payload"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Not a refresh token")
        if "user_id" not in payload:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8")
    )


def hash_password(password: str) -> str:
    """Hash a password"""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


async def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """
    FastAPI dependency that enforces admin JWT authentication.
    Used as router-level dependency for all protected admin routes.

    Returns decoded JWT payload with user_id, username, is_superadmin.
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        if "user_id" not in payload:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        # A long-lived refresh token must NOT be accepted as an access token —
        # otherwise the 30-min access lifetime is defeated (refresh lives 7 days).
        if payload.get("type") == "refresh":
            raise HTTPException(status_code=401, detail="Refresh token cannot be used for access")
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_superadmin(
    payload: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """
    Dependency that requires the caller to be an ACTIVE superadmin.

    Loads the AdminUser row (authoritative, not just the token claim) so that a
    deactivated/deleted admin is cut immediately, and so a scoped "manager"
    account cannot reach superadmin-only surfaces (e.g. admin-account CRUD).

    The owner (role='owner') always passes — the operator is never locked out of
    their own box even if the is_superadmin flag was never set on their row. If
    the AdminUser lookup itself fails (e.g. a column a migration hasn't added on
    an older install), fall back to the signed token claims instead of 500-ing.
    """
    from src.database.models import AdminUser
    try:
        admin = db.query(AdminUser).filter(AdminUser.id == payload.get("user_id")).first()
    except Exception as e:
        logger.warning("require_superadmin: AdminUser lookup failed (%s) — using token claims", e)
        if payload.get("is_superadmin") or payload.get("role") == "owner":
            return payload
        raise HTTPException(status_code=403, detail="Superadmin privileges required")
    if not admin or getattr(admin, "is_active", True) is False:
        raise HTTPException(status_code=401, detail="Account inactive or not found")
    if getattr(admin, "is_superadmin", False) or getattr(admin, "role", "") == "owner":
        return payload
    raise HTTPException(status_code=403, detail="Superadmin privileges required")


def require_permission(permission: str):
    """
    Dependency FACTORY that gates an admin router/route on a manager permission.

    - Owner/admin accounts and explicit superadmins bypass every permission check
      — only a scoped "manager" account is restricted by its granted list. This
      is what keeps the operator (and any full admin) from being locked out of
      their own panel: a missing/false is_superadmin flag on an owner row no
      longer 403s the entire panel.
    - Non-owner "manager" accounts must have `permission` in their granted list,
      else 403.
    - Re-checks the account is still active, cutting deactivated/deleted admins.
    - If the AdminUser lookup raises (schema drift on an older install), fall back
      to the signed token claims rather than blanking every data endpoint.
    """
    async def _dep(
        payload: dict = Depends(get_current_admin),
        db: Session = Depends(get_db),
    ) -> dict:
        from src.database.models import AdminUser
        try:
            admin = db.query(AdminUser).filter(AdminUser.id == payload.get("user_id")).first()
        except Exception as e:
            logger.warning(
                "require_permission(%s): AdminUser lookup failed (%s) — using token claims",
                permission, e,
            )
            if payload.get("is_superadmin") or payload.get("role", "owner") != "manager":
                return payload
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        if not admin or getattr(admin, "is_active", True) is False:
            raise HTTPException(status_code=401, detail="Account inactive or not found")
        # Owner/admin/superadmin → full access; only 'manager' is scoped.
        if getattr(admin, "is_superadmin", False) or getattr(admin, "role", "owner") != "manager":
            return payload
        try:
            perms = _json.loads(admin.permissions) if admin.permissions else []
        except (ValueError, TypeError):
            perms = []
        if permission not in perms:
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        return payload
    return _dep
