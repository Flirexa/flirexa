"""
VPN Management Studio Client Portal - API Routes
FastAPI routes for client portal (registration, subscriptions, payments)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import jwt
import os
import hashlib

from src.database.connection import get_db
from src.modules.subscription.subscription_models import SubscriptionTier, PaymentMethod
from src.modules.subscription.subscription_manager import SubscriptionManager
from src.modules.subscription.cryptopay_adapter import CryptoPayAdapter, create_subscription_invoice

# JWT configuration
_jwt_fallback = ""
try:
    with open("/etc/machine-id", "r", encoding="utf-8") as f:
        _jwt_fallback = hashlib.sha256(
            f"vpnmanager-legacy-portal-jwt-{f.read().strip()}".encode()
        ).hexdigest()
except Exception:
    _jwt_fallback = hashlib.sha256(b"vpnmanager-legacy-portal-fallback-key").hexdigest()
JWT_SECRET = os.getenv("JWT_SECRET", _jwt_fallback)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Security
security = HTTPBearer()

# Router
router = APIRouter(prefix="/client-portal", tags=["Client Portal"])

# CryptoPay adapter (initialize in main.py)
cryptopay_adapter = None


def get_cryptopay() -> CryptoPayAdapter:
    """Get CryptoPay adapter instance"""
    if not cryptopay_adapter:
        raise HTTPException(status_code=500, detail="CryptoPay not configured")
    return cryptopay_adapter


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    username: str = Field(min_length=3, max_length=50)
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class CreateInvoiceRequest(BaseModel):
    plan_tier: SubscriptionTier
    duration_days: int = Field(30, ge=7, le=365)
    currency: str = Field("USDT", pattern="^(BTC|TON|USDT|USDC|BUSD|ETH)$")


class InvoiceResponse(BaseModel):
    invoice_id: str
    amount_usd: float
    amount_crypto: float
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

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user_id


# ═══════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: Session = Depends(get_db)):
    """Register new client user"""
    manager = SubscriptionManager(db)

    user, error = manager.create_user(
        email=data.email,
        password=data.password,
        username=data.username,
        full_name=data.full_name
    )

    if error:
        raise HTTPException(status_code=400, detail=error)

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
async def login(data: UserLogin, db: Session = Depends(get_db)):
    """Login with email and password"""
    manager = SubscriptionManager(db)
    user = manager.authenticate_user(data.email, data.password)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

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
        "created_at": user.created_at.isoformat()
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
        raise HTTPException(status_code=404, detail="No subscription found")

    return {
        "id": subscription.id,
        "tier": subscription.tier.value,
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
            "tier": plan.tier.value,
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
    cryptopay: CryptoPayAdapter = Depends(get_cryptopay)
):
    """Create payment invoice for subscription"""
    manager = SubscriptionManager(db)

    # Get plan details
    plan = manager.get_plan_by_tier(data.plan_tier)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Calculate price based on duration
    if data.duration_days >= 365:
        amount_usd = plan.price_yearly_usd or (plan.price_monthly_usd * 12)
    elif data.duration_days >= 90:
        amount_usd = plan.price_quarterly_usd or (plan.price_monthly_usd * 3)
    else:
        amount_usd = plan.price_monthly_usd * (data.duration_days / 30)

    # Create invoice via CryptoPay
    invoice_data = await create_subscription_invoice(
        adapter=cryptopay,
        user_id=user_id,
        plan_name=plan.name,
        amount_usd=amount_usd,
        currency=data.currency,
        duration_days=data.duration_days
    )

    # Save payment record
    payment = manager.create_payment(
        user_id=user_id,
        amount_usd=amount_usd,
        payment_method=PaymentMethod(data.currency.lower()),
        subscription_tier=data.plan_tier,
        duration_days=data.duration_days,
        invoice_id=invoice_data["invoice_id"],
        provider_name="cryptopay"
    )

    payment.crypto_amount = str(invoice_data["amount_crypto"])
    payment.set_provider_data(invoice_data)
    db.commit()

    return InvoiceResponse(**invoice_data)


@router.get("/payments/check/{invoice_id}")
async def check_payment_status(
    invoice_id: str,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    cryptopay: CryptoPayAdapter = Depends(get_cryptopay)
):
    """Check payment status"""
    manager = SubscriptionManager(db)

    # Get payment from database
    payment = manager.get_payment_by_invoice(invoice_id)
    if not payment or payment.user_id != user_id:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Check status via CryptoPay
    status = await cryptopay.check_payment(int(invoice_id))

    # Update payment status
    if status == "paid" and payment.status != "completed":
        manager.complete_payment(invoice_id)

    return {
        "invoice_id": invoice_id,
        "status": status,
        "amount_usd": payment.amount_usd,
        "currency": payment.payment_method.value,
        "created_at": payment.created_at.isoformat(),
        "expires_at": payment.expires_at.isoformat() if payment.expires_at else None
    }


@router.get("/payments/history")
async def get_payment_history(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50
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
            "subscription_tier": p.subscription_tier.value if p.subscription_tier else None,
            "duration_days": p.duration_days,
            "created_at": p.created_at.isoformat(),
            "completed_at": p.completed_at.isoformat() if p.completed_at else None
        }
        for p in payments
    ]


# ═══════════════════════════════════════════════════════════════════════════
# WEBHOOK ROUTE
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/webhooks/cryptopay")
async def cryptopay_webhook(
    request: Request,
    db: Session = Depends(get_db),
    cryptopay: CryptoPayAdapter = Depends(get_cryptopay)
):
    """Handle CryptoPay webhook for payment notifications"""
    body = await request.body()
    headers = dict(request.headers)

    # Process webhook
    update = await cryptopay.process_webhook(body, headers)

    if not update:
        raise HTTPException(status_code=400, detail="Invalid webhook")

    if update["type"] == "invoice_paid":
        invoice_id = update["invoice_id"]

        # Complete payment and activate subscription
        manager = SubscriptionManager(db)
        manager.complete_payment(invoice_id)

        return {"status": "ok", "message": "Payment processed"}

    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
# CRYPTO INFO ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/crypto/currencies")
async def get_crypto_currencies(cryptopay: CryptoPayAdapter = Depends(get_cryptopay)):
    """Get supported cryptocurrencies"""
    currencies = await cryptopay.get_currencies()
    return currencies


@router.get("/crypto/rates")
async def get_exchange_rates(cryptopay: CryptoPayAdapter = Depends(get_cryptopay)):
    """Get current exchange rates"""
    rates = await cryptopay.get_exchange_rates()
    return rates
