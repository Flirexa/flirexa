"""
VPN Management Studio Client Portal - API Routes
FastAPI routes for client portal (registration, subscriptions, payments)

All WireGuard operations go through Admin API internal endpoints via AdminAPIClient.
No direct imports of ManagementCore or Client model.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import Response, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from pathlib import Path
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

from src.database.connection import get_db
from src.database.models import Server
from src.modules.subscription.subscription_models import (
    PaymentMethod, ClientUserClients, ClientUser, SubscriptionStatus
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
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))  # 24 hours

# Security
security = HTTPBearer()

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
_invoice_rate: dict[int, list[float]] = {}  # per user_id, max 5/hour
_forgot_cooldowns: dict[str, float] = {}  # per-email cooldown for forgot-password
_SUBSCRIPTION_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


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
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    username: str = Field(min_length=3, max_length=50)
    full_name: Optional[str] = None
    referral_code: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str = "user"
    admin_token: Optional[str] = None
    user: dict


class CreateInvoiceRequest(BaseModel):
    plan_tier: str
    duration_days: int = Field(30, ge=7, le=365)
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

def create_access_token(user_id: int, email: str) -> str:
    """Create JWT access token"""
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> int:
    """Get current authenticated user ID"""
    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = payload.get("user_id")

    manager = SubscriptionManager(db)
    user = manager.get_user_by_id(user_id)

    if not user or not user.is_active or user.is_banned:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user_id


# ═══════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, request: Request, db: Session = Depends(get_db)):
    """Register new client user"""
    ip = _get_client_ip(request)
    if not _check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in 5 minutes.")
    _record_attempt(ip)

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
        ns.notify_admin_new_user(user.username, user.email)
    except Exception as _notify_err:
        logger.warning("notify_admin_new_user failed for %s: %s", user.username, _notify_err)

    # Send verification email if SMTP is configured
    smtp_service, _smtp_settings = _get_email_service()
    if smtp_service:
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
            branding.get("branding_app_name") or "VPN Manager",
            branding.get("branding_support_email") or "",
            lang,
            branding.get("branding_logo_url") or "",
        )

    token = create_access_token(user.id, user.email)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "email_verified": user.email_verified
        }
    }


@router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, request: Request, db: Session = Depends(get_db)):
    """Login with email and password"""
    ip = _get_client_ip(request)
    if not _check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again in 5 minutes.")
    _record_attempt(ip)

    manager = SubscriptionManager(db)
    user = manager.authenticate_user(data.email, data.password)

    if not user:
        await asyncio.sleep(random.uniform(0.5, 1.5))  # Prevent timing attacks
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.id, user.email)
    user_role = getattr(user, 'role', 'user') or 'user'

    response = {
        "access_token": token,
        "token_type": "bearer",
        "role": user_role,
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "email_verified": user.email_verified
        }
    }

    return response


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
async def change_password(
    data: ChangePasswordRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change current user's password"""
    import bcrypt
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not bcrypt.checkpw(data.current_password.encode('utf-8'), user.password_hash.encode('utf-8')):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = bcrypt.hashpw(data.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.commit()

    logger.info(f"User {user_id} changed password")
    return {"status": "ok", "message": "Password changed successfully"}


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
    if not _check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Too many requests")
    _record_attempt(ip)

    # Per-email rate limit (1 request per 60 seconds)
    email_key = data.email.lower()
    now = time.time()
    if email_key in _forgot_cooldowns and now - _forgot_cooldowns[email_key] < 60:
        raise HTTPException(status_code=429, detail="Please wait before requesting another reset email.")
    _forgot_cooldowns[email_key] = now

    user = db.query(ClientUser).filter(ClientUser.email == data.email).first()

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
            branding.get("branding_app_name") or "VPN Manager",
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
async def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """Reset password using token from forgot-password"""
    import bcrypt
    user = db.query(ClientUser).filter(
        ClientUser.password_reset_token == data.token
    ).first()

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
    return {
        "features": {
            "corp_networks": corp_networks,
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
            raise HTTPException(status_code=404, detail="No subscription found")

    return {
        "id": subscription.id,
        "tier": subscription.tier,
        "status": subscription.status.value,
        "max_devices": subscription.max_devices,
        "traffic_limit_gb": subscription.traffic_limit_gb,
        "traffic_used_gb": round(subscription.traffic_used_total_gb, 2),
        "traffic_remaining_gb": round(subscription.traffic_remaining_gb, 2) if subscription.traffic_remaining_gb else None,
        "traffic_percentage": subscription.traffic_percentage_used,
        "bandwidth_limit_mbps": subscription.bandwidth_limit_mbps,
        "price_monthly_usd": subscription.price_monthly_usd,
        "expiry_date": subscription.expiry_date.isoformat() if subscription.expiry_date else None,
        "days_remaining": subscription.days_remaining,
        "auto_renew": subscription.auto_renew,
        "created_at": subscription.created_at.isoformat()
    }


@router.get("/subscription/plans")
async def get_subscription_plans(db: Session = Depends(get_db)):
    """Get available subscription plans"""
    manager = SubscriptionManager(db)
    plans = manager.get_all_plans(active_only=True)

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
        }
        for plan in plans
    ]


@router.post("/subscription/cancel")
async def cancel_subscription(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel current subscription — downgrade to free tier"""
    manager = SubscriptionManager(db)
    subscription = manager.get_subscription(user_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription found")

    if subscription.tier == "free":
        raise HTTPException(status_code=400, detail="Already on free tier")

    # Downgrade to free plan
    free_plan = manager.get_plan_by_tier("free")
    if not free_plan:
        raise HTTPException(status_code=500, detail="Free plan not configured")

    subscription.tier = "free"
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.max_devices = free_plan.max_devices
    subscription.traffic_limit_gb = free_plan.traffic_limit_gb
    subscription.bandwidth_limit_mbps = free_plan.bandwidth_limit_mbps
    subscription.price_monthly_usd = 0
    subscription.expiry_date = None
    subscription.auto_renew = False
    db.commit()

    # Apply free limits to WG clients
    manager.apply_subscription_limits(user_id)

    logger.info(f"User {user_id} cancelled subscription, downgraded to free")
    return {"status": "ok", "message": "Subscription cancelled, downgraded to free tier"}


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

    # Calculate price based on duration
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
        promo = db.query(PromoCode).filter(PromoCode.code == promo_code_str).first()
        if promo and promo.is_valid:
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
            raise HTTPException(status_code=500, detail=f"PayPal error: {str(e)}")

    elif data.provider == "nowpayments":
        if not nowpayments_provider:
            raise HTTPException(status_code=503, detail="NOWPayments not configured")
        try:
            invoice = await nowpayments_provider.create_invoice(
                amount=int(amount_usd * 100),
                currency=data.currency.upper(),
                description=f"VPN - {plan.name} ({data.duration_days} days)",
                metadata={"user_id": user_id, "plan": data.plan_tier},
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
            raise HTTPException(status_code=500, detail=f"NOWPayments error: {str(e)}")

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
                raise HTTPException(status_code=500, detail=f"CryptoPay error: {str(e)}")
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
                }
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
    # Store provider-specific order ID for webhook lookup
    if data.provider == "paypal" and invoice_data.get("paypal_order_id"):
        payment.provider_invoice_id = invoice_data["paypal_order_id"]
    elif data.provider == "nowpayments":
        payment.provider_invoice_id = invoice_data["invoice_id"]
    payment.set_provider_data(invoice_data)
    db.commit()

    return InvoiceResponse(**invoice_data)


@router.get("/payments/providers")
async def get_available_providers():
    """Get list of configured payment providers (built-in + plugins)"""
    providers = []
    if cryptopay_adapter:
        providers.append({"id": "cryptopay", "name": "CryptoPay (Telegram)", "type": "crypto"})
    if paypal_provider:
        providers.append({"id": "paypal", "name": "PayPal", "type": "fiat"})
    if nowpayments_provider:
        providers.append({"id": "nowpayments", "name": "NOWPayments (Crypto)", "type": "crypto"})
    # Auto-detect plugin providers
    import sys
    _this = sys.modules[__name__]
    _portal = sys.modules.get("src.api.routes.client_portal", _this)
    for attr_name in dir(_portal):
        if attr_name.endswith("_provider") and attr_name not in ("paypal_provider", "nowpayments_provider"):
            prov = getattr(_portal, attr_name, None)
            if prov and hasattr(prov, "name") and hasattr(prov, "display_name"):
                providers.append({"id": prov.name, "name": prov.display_name, "type": "plugin"})
    if not providers:
        providers.append({"id": "cryptopay", "name": "CryptoPay (Test Mode)", "type": "crypto"})
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
                    from ..modules.payment.base import PaymentStatus as _PS
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


@router.post("/webhooks/{provider_name}")
async def plugin_webhook(
    provider_name: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Dynamic webhook handler for plugin payment providers."""
    # Skip built-in providers (handled by specific routes below)
    if provider_name in ("cryptopay", "paypal", "nowpayments"):
        raise HTTPException(status_code=404)

    import sys as _sys
    _portal = _sys.modules.get(__name__)
    _prov = getattr(_portal, f"{provider_name}_provider", None) if _portal else None
    if not _prov:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    body = await request.body()
    try:
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        result = await _prov.process_webhook(data)
    except Exception as e:
        logger.error(f"Plugin webhook {provider_name} error: {e}")
        raise HTTPException(status_code=400, detail="Webhook processing failed")

    if result:
        # Find and complete payment
        order_id = (
            data.get("metadata", {}).get("invoice_id")
            or data.get("data", {}).get("object", {}).get("metadata", {}).get("invoice_id")
            or data.get("order_id")
            or data.get("id")
        )
        if order_id:
            manager = SubscriptionManager(db)
            payment = manager.get_payment_by_invoice(str(order_id))
            if payment and payment.status != "completed":
                manager.complete_payment(str(order_id), sync_wg=False)
                try:
                    await _sync_wg_after_payment(db, payment.user_id, manager)
                except Exception as e:
                    logger.error(f"Plugin {provider_name}: WG sync failed: {e}")
                logger.info(f"Plugin {provider_name}: payment {order_id} completed")

    return {"status": "ok"}


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
        payment = manager.get_payment_by_invoice(str(invoice_id))
        if payment and payment.status != "completed":
            # Validate webhook amount matches payment record (allow 1% variance for rounding)
            webhook_amount = float(update.get("amount", 0))
            if webhook_amount > 0:
                if webhook_amount < payment.amount_usd * 0.99:
                    logger.error(f"CryptoPay underpayment: webhook={webhook_amount}, expected={payment.amount_usd}, invoice={invoice_id}")
                    return {"status": "error", "message": "Amount mismatch"}
                if webhook_amount > payment.amount_usd * 1.10:
                    # Overpayment beyond 10% is suspicious — log but still process
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
        payment = db.query(ClientPortalPayment).filter(
            ClientPortalPayment.provider_name == "paypal",
            ClientPortalPayment.provider_invoice_id == order_id,
        ).first()

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
    """Handle NOWPayments IPN webhook"""
    if not nowpayments_provider:
        raise HTTPException(status_code=503, detail="NOWPayments not configured")

    import json
    body = await request.body()
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    signature = request.headers.get("x-nowpayments-sig", "")

    try:
        result = await nowpayments_provider.process_webhook(data, signature)
    except Exception as e:
        logger.error(f"NOWPayments webhook processing error: {e}")
        raise HTTPException(status_code=400, detail="Webhook processing failed")

    if not result:
        raise HTTPException(status_code=400, detail="Invalid webhook")

    # If payment finished, complete it
    if data.get("payment_status", "").lower() == "finished":
        order_id = data.get("order_id", "")
        if order_id:
            manager = SubscriptionManager(db)
            payment = manager.get_payment_by_invoice(order_id)
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
            branding.get("branding_app_name") or "VPN Manager",
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
        branding.get("branding_app_name") or "VPN Manager",
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
    """Get list of WG client IDs linked to a portal user"""
    links = db.query(ClientUserClients).filter(
        ClientUserClients.client_user_id == user_id
    ).all()
    return [link.client_id for link in links]


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
    """Get user's WireGuard clients via Admin API"""
    api = get_admin_api()
    client_ids = _get_user_client_ids(db, user_id)

    if not client_ids:
        return []

    clients = await api.get_clients_by_ids(client_ids)
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

    manager = SubscriptionManager(db)
    subscription = manager.get_subscription(user_id)

    if not subscription or not subscription.is_active:
        raise HTTPException(status_code=400, detail="No active subscription")

    # Check device limit
    existing_ids = _get_user_client_ids(db, user_id)
    max_devices = subscription.max_devices or 1
    if len(existing_ids) >= max_devices:
        raise HTTPException(
            status_code=400,
            detail="Cannot create client: device limit reached"
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
        if not sub or sub.status.value != "active":
            raise HTTPException(status_code=400, detail="No active subscription")

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
    """Download VPN Management Studio APK"""
    apk_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web", "static", "vpn-manager.apk")
    if not os.path.isfile(apk_path):
        raise HTTPException(status_code=404, detail="APK not found")
    return FileResponse(apk_path, filename="vpn-manager.apk", media_type="application/vnd.android.package-archive")


# ═══════════════════════════════════════════════════════════════════════════
# SERVERS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/servers")
async def get_servers(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of available servers (public-safe fields only)"""
    servers = db.query(Server).all()
    return [
        {
            "id": s.id,
            "name": getattr(s, 'display_name', None) or s.name,
            "location": s.location,
            "status": s.status.value if hasattr(s.status, 'value') else str(s.status),
            "server_category": getattr(s, 'server_category', 'vpn'),
            "server_type": getattr(s, 'server_type', 'wireguard'),
        }
        for s in servers
    ]


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

    # Auto-create WG client if user has none
    if not client_ids:
        user = manager.get_user_by_id(user_id)
        if user:
            client_name = f"{user.username}-1"
            result = await admin_api.create_client(
                name=client_name,
                bandwidth_limit=subscription.bandwidth_limit_mbps,
                traffic_limit_mb=int(subscription.traffic_limit_gb * 1024) if subscription.traffic_limit_gb else None,
                expiry_days=(
                    max(1, round((subscription._aware_expiry() - datetime.now(timezone.utc)).total_seconds() / 86400))
                    if subscription.expiry_date else 30
                ),
            )
            if result:
                link = ClientUserClients(client_user_id=user_id, client_id=result["id"])
                db.add(link)
                db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# REFERRAL SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/referral")
async def get_referral_info(
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
async def validate_promo_client(
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
async def toggle_auto_renew(
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
async def send_support_message(
    data: SupportMessageRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a support message from client to admin"""
    from src.modules.subscription.subscription_models import SupportMessage

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
async def get_support_messages(
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
async def reply_to_support_ticket(
    ticket_id: int,
    data: SupportReplyRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """User replies to their own support ticket"""
    from src.modules.subscription.subscription_models import SupportMessage

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
async def get_unread_support_count(
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
async def get_notifications(
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
async def mark_notification_read(
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
# SUBSCRIPTION LINK
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/subscription-link")
async def get_subscription_link(
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
async def regenerate_subscription_link(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Regenerate subscription link token"""
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
async def get_subscription_config(
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
