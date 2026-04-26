"""
VPN Management Studio Admin Panel - Authentication Routes
JWT-based auth with brute-force protection
"""

import os
import subprocess
import time
import random
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from loguru import logger

from ...database.connection import get_db
from ...database.models import AdminUser, AuditLog, AuditAction, Server, ServerStatus, ServerLifecycleStatus
from ..middleware.auth import (
    create_access_token, create_refresh_token, verify_refresh_token,
    verify_password, hash_password,
    SECRET_KEY, ALGORITHM
)

router = APIRouter()

# ============================================================================
# RATE LIMITING (in-memory, per IP)
# ============================================================================

_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 300  # 5 minutes
_RATE_LIMIT_MAX = 5        # max attempts per window
_ACCOUNT_LOCK_THRESHOLD = 10
_ACCOUNT_LOCK_MINUTES = 30


def _check_rate_limit(ip: str) -> bool:
    """Check if IP is rate-limited. Returns True if allowed."""
    now = time.time()
    # Clean old entries
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < _RATE_LIMIT_WINDOW]
    return len(_login_attempts[ip]) < _RATE_LIMIT_MAX


def _record_attempt(ip: str):
    """Record a login attempt for rate limiting."""
    _login_attempts[ip].append(time.time())


def _cleanup_rate_limits():
    """Remove stale entries (called periodically)."""
    now = time.time()
    stale = [ip for ip, times in _login_attempts.items()
             if not times or now - times[-1] > _RATE_LIMIT_WINDOW]
    for ip in stale:
        del _login_attempts[ip]


# ============================================================================
# SCHEMAS
# ============================================================================

class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateAdminRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=100)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: dict


# ============================================================================
# HELPERS
# ============================================================================

def _get_client_ip(request: Request) -> str:
    """Get client IP from request (handles proxies)."""
    direct_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and direct_ip in {"127.0.0.1", "::1", "localhost"}:
        return forwarded.split(",")[0].strip()
    return direct_ip


def _make_token_response(user: AdminUser, db: Session) -> dict:
    """Create token response and update last_login."""
    user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()

    token_data = {
        "user_id": user.id,
        "username": user.username,
        "is_superadmin": user.is_superadmin,
        "role": getattr(user, 'role', 'owner'),
    }
    token = create_access_token(token_data)
    refresh = create_refresh_token(token_data)

    return {
        "access_token": token,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "is_superadmin": user.is_superadmin,
        }
    }


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/setup-status")
async def setup_status(db: Session = Depends(get_db)):
    """Check if initial setup is needed (no admin users exist)."""
    count = db.query(AdminUser).count()
    return {"needs_setup": count == 0}


@router.post("/setup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def setup(data: SetupRequest, request: Request, db: Session = Depends(get_db)):
    """
    Initial admin setup. Only works when no admin users exist.
    Creates the first admin account.
    """
    count = db.query(AdminUser).count()
    if count > 0:
        raise HTTPException(status_code=403, detail="Setup already completed")

    # Create admin user
    admin = AdminUser(
        username=data.username,
        password_hash=hash_password(data.password),
        is_superadmin=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    ip = _get_client_ip(request)
    logger.info(f"Admin setup completed: user '{data.username}' created from {ip}")

    # Audit log
    db.add(AuditLog(
        action=AuditAction.CONFIG_CHANGE,
        target_type="admin_user",
        target_id=admin.id,
        target_name=admin.username,
        details={"action": "setup", "ip": ip},
    ))
    db.commit()

    # Auto-register local WireGuard server if present and not yet registered
    try:
        _auto_register_local_server(db)
    except Exception as e:
        logger.warning(f"Auto-register local server failed (non-fatal): {e}")

    return _make_token_response(admin, db)


def _auto_register_local_server(db: Session) -> None:
    """Auto-register local WireGuard server on first admin setup if wg0 is active."""
    # Skip if servers already exist
    if db.query(Server).count() > 0:
        return

    iface = os.getenv("WG_INTERFACE", "wg0")
    wg_conf = os.getenv("WG_CONFIG_PATH", f"/etc/wireguard/{iface}.conf")

    # Check interface is up
    result = subprocess.run(["wg", "show", iface], capture_output=True, text=True)
    if result.returncode != 0:
        return

    # Read public key
    pub_key = ""
    for line in result.stdout.splitlines():
        if line.strip().startswith("public key:"):
            pub_key = line.split(":", 1)[1].strip()
            break
    if not pub_key:
        return

    # Read config
    private_key = ""
    listen_port = 51820
    address_v4 = ""
    address_v6 = ""
    if os.path.exists(wg_conf):
        with open(wg_conf) as f:
            for line in f:
                line = line.strip()
                if line.startswith("PrivateKey"):
                    private_key = line.split("=", 1)[1].strip()
                elif line.startswith("ListenPort"):
                    try:
                        listen_port = int(line.split("=", 1)[1].strip())
                    except ValueError:
                        pass
                elif line.startswith("Address"):
                    addrs = line.split("=", 1)[1].strip().split(",")
                    for addr in addrs:
                        addr = addr.strip()
                        if ":" not in addr and not address_v4:
                            address_v4 = addr
                        elif ":" in addr and not address_v6:
                            address_v6 = addr

    # Get server public IP
    server_ip = ""
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "5", "https://ifconfig.me/ip"],
            capture_output=True, text=True
        )
        import re
        m = re.search(r'(\d{1,3}\.){3}\d{1,3}', r.stdout)
        if m:
            server_ip = m.group(0)
    except Exception:
        pass
    if not server_ip:
        # Fallback to local IP
        try:
            r = subprocess.run(["hostname", "-I"], capture_output=True, text=True)
            server_ip = r.stdout.split()[0]
        except Exception:
            server_ip = "127.0.0.1"

    endpoint = f"{server_ip}:{listen_port}"

    # Convert interface address (10.66.66.1/24) to pool (10.66.66.0/24)
    pool_v4 = address_v4 or "10.66.66.1/24"
    try:
        import ipaddress
        net = ipaddress.IPv4Interface(pool_v4).network
        pool_v4 = str(net)
    except Exception:
        pass

    server = Server(
        name="Main Server",
        endpoint=endpoint,
        public_key=pub_key,
        private_key=private_key,
        listen_port=listen_port,
        address_pool_ipv4=pool_v4,
        address_pool_ipv6=address_v6 or None,
        interface=iface,
        config_path=wg_conf,
        is_default=True,
        status=ServerStatus.ONLINE,
        lifecycle_status=ServerLifecycleStatus.ONLINE.value,
        is_active=True,
    )
    db.add(server)
    db.commit()
    logger.info(f"Auto-registered local WireGuard server: {endpoint} (pub={pub_key[:16]}...)")


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Admin login with brute-force protection.
    """
    ip = _get_client_ip(request)

    # Rate limit check
    if not _check_rate_limit(ip):
        logger.warning(f"Rate limit exceeded for {ip}")
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again in 5 minutes."
        )

    _record_attempt(ip)

    # Find user
    user = db.query(AdminUser).filter(AdminUser.username == data.username).first()

    if not user:
        # Delay to prevent username enumeration
        await asyncio.sleep(random.uniform(0.5, 2.0))
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check account lock (locked_until stored as naive UTC in DB)
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    if user.locked_until:
        lu = user.locked_until.replace(tzinfo=None) if user.locked_until.tzinfo else user.locked_until
        if lu > now_naive:
            remaining = int((lu - now_naive).total_seconds() / 60) + 1
            raise HTTPException(
                status_code=423,
                detail=f"Account locked. Try again in {remaining} minutes."
            )

    # Verify password
    if not verify_password(data.password, user.password_hash):
        user.failed_attempts = (user.failed_attempts or 0) + 1

        # Lock account after threshold
        if user.failed_attempts >= _ACCOUNT_LOCK_THRESHOLD:
            user.locked_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=_ACCOUNT_LOCK_MINUTES)
            logger.warning(f"Account '{user.username}' locked after {user.failed_attempts} failed attempts from {ip}")

        db.commit()

        # Random delay to prevent timing attacks
        await asyncio.sleep(random.uniform(0.5, 2.0))
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Periodic cleanup
    _cleanup_rate_limits()

    logger.info(f"Admin login: '{user.username}' from {ip}")
    return _make_token_response(user, db)


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    """Get a new access token using a refresh token."""
    payload = verify_refresh_token(data.refresh_token)

    user = db.query(AdminUser).filter(AdminUser.id == payload["user_id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    token_data = {
        "user_id": user.id,
        "username": user.username,
        "is_superadmin": user.is_superadmin,
        "role": getattr(user, 'role', 'owner'),
    }

    return {
        "access_token": create_access_token(token_data),
        "refresh_token": data.refresh_token,  # Reuse existing refresh token
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "is_superadmin": user.is_superadmin,
        }
    }


@router.get("/me")
async def get_me(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: Session = Depends(get_db)
):
    """Get current admin user info."""
    from jose import JWTError, jwt as jose_jwt

    try:
        payload = jose_jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("user_id")
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "id": user.id,
        "username": user.username,
        "is_superadmin": user.is_superadmin,
        "role": "admin",
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: Session = Depends(get_db)
):
    """Change admin password."""
    from jose import JWTError, jwt as jose_jwt

    try:
        payload = jose_jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("user_id")
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = hash_password(data.new_password)
    db.commit()

    logger.info(f"Password changed for admin '{user.username}'")
    return {"message": "Password changed successfully"}


@router.post("/create-admin", status_code=status.HTTP_201_CREATED)
async def create_admin(
    data: CreateAdminRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: Session = Depends(get_db)
):
    """Create a new admin account. Only existing admins can create new ones."""
    from jose import JWTError, jwt as jose_jwt

    try:
        payload = jose_jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    caller_id = payload.get("user_id")
    caller = db.query(AdminUser).filter(AdminUser.id == caller_id).first()
    if not caller:
        raise HTTPException(status_code=401, detail="User not found")

    # Only superadmins can create new admin accounts
    if not caller.is_superadmin:
        raise HTTPException(status_code=403, detail="Only superadmins can create admin accounts")

    # Check if username already taken
    existing = db.query(AdminUser).filter(AdminUser.username == data.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    new_admin = AdminUser(
        username=data.username,
        password_hash=hash_password(data.password),
        is_superadmin=False,
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)

    ip = _get_client_ip(request)
    logger.info(f"Admin '{caller.username}' created new admin '{data.username}' from {ip}")

    db.add(AuditLog(
        user_id=caller.id,
        user_type="admin",
        action=AuditAction.CONFIG_CHANGE,
        target_type="admin_user",
        target_id=new_admin.id,
        target_name=new_admin.username,
        details={"action": "create_admin", "created_by": caller.username, "ip": ip},
    ))
    db.commit()

    return {
        "id": new_admin.id,
        "username": new_admin.username,
        "is_superadmin": new_admin.is_superadmin,
        "message": f"Admin '{data.username}' created successfully",
    }


@router.get("/admins")
async def list_admins(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: Session = Depends(get_db)
):
    """List all admin accounts."""
    from jose import JWTError, jwt as jose_jwt
    try:
        payload = jose_jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    caller_id = payload.get("user_id")
    caller = db.query(AdminUser).filter(AdminUser.id == caller_id).first()
    if not caller or not caller.is_superadmin:
        raise HTTPException(status_code=403, detail="Only superadmins can list admin accounts")

    admins = db.query(AdminUser).all()
    return [
        {
            "id": a.id,
            "username": a.username,
            "is_superadmin": a.is_superadmin,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "last_login": a.last_login.isoformat() if a.last_login else None,
        }
        for a in admins
    ]


@router.delete("/admins/{admin_id}")
async def delete_admin(
    admin_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: Session = Depends(get_db)
):
    """Delete an admin account. Only superadmins can delete. Cannot delete yourself."""
    from jose import JWTError, jwt as jose_jwt
    try:
        payload = jose_jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    caller_id = payload.get("user_id")
    caller = db.query(AdminUser).filter(AdminUser.id == caller_id).first()
    if not caller or not caller.is_superadmin:
        raise HTTPException(status_code=403, detail="Only superadmins can delete admin accounts")

    if admin_id == caller_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    target = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found")

    db.delete(target)
    db.commit()

    logger.info(f"Admin '{caller.username}' deleted admin '{target.username}'")
    return {"message": f"Admin '{target.username}' deleted"}
