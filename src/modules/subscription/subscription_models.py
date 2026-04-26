"""
VPN Management Studio Client Portal - Subscription Models
Database models for subscription and payment management
"""

from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, Float, Text, ForeignKey, Enum as SQLEnum, UniqueConstraint, Index, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
import json

from src.database.models import Base


class SubscriptionTier(str, Enum):
    """Subscription tiers"""
    FREE = "free"
    BASIC = "basic"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    """Subscription status"""
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"
    PENDING = "pending"  # Waiting for payment


class PaymentMethod(str, Enum):
    """Payment methods"""
    BTC = "btc"
    USDT_TRC20 = "usdt_trc20"
    USDT_ERC20 = "usdt_erc20"
    TON = "ton"
    ETH = "eth"
    PAYPAL = "paypal"
    USD = "usd"
    EUR = "eur"


# ═══════════════════════════════════════════════════════════════════════════
# CLIENT USER MODEL
# ═══════════════════════════════════════════════════════════════════════════

class ClientUser(Base):
    """
    Client user account (for web portal)
    Separate from WireGuard clients
    """
    __tablename__ = "client_users"

    id = Column(Integer, primary_key=True)

    # Authentication
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    telegram_id = Column(String(50), unique=True, nullable=True, index=True)  # Link to Telegram bot

    # Profile
    username = Column(String(100), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=True)
    language = Column(String(10), default="en")  # en, ru, etc.

    # Verification
    email_verified = Column(Boolean, default=False)
    verification_token = Column(String(255), nullable=True)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_token_created_at = Column(DateTime, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(Text, nullable=True)

    # Role (RBAC for mobile app)
    role = Column(String(20), default="user", nullable=False)  # "user" or "admin"

    # Subscription link token
    subscription_token = Column(String(64), unique=True, nullable=True, index=True)
    subscription_token_created_at = Column(DateTime, nullable=True)

    # Referral system
    referral_code = Column(String(20), unique=True, nullable=True, index=True)
    referred_by_id = Column(Integer, ForeignKey("client_users.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    subscription = relationship("ClientPortalSubscription", back_populates="user", uselist=False, cascade="all, delete-orphan")
    payments = relationship("ClientPortalPayment", back_populates="user", cascade="all, delete-orphan")
    wireguard_clients = relationship("Client", secondary="client_user_clients")  # Link to WG clients
    referred_by = relationship("ClientUser", remote_side="ClientUser.id", foreign_keys=[referred_by_id])
    referrals = relationship("ClientUser", foreign_keys=[referred_by_id], back_populates="referred_by", viewonly=True)

    def __repr__(self):
        return f"<ClientUser {self.username} ({self.email})>"


# ═══════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION MODEL
# ═══════════════════════════════════════════════════════════════════════════

class ClientPortalSubscription(Base):
    """User subscription"""
    __tablename__ = "client_portal_subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("client_users.id"), unique=True, nullable=False)

    # Subscription details
    tier = Column(String(50), default="free", nullable=False)
    status = Column(SQLEnum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, nullable=False)

    # Limits
    max_devices = Column(Integer, default=1)  # Number of WireGuard clients
    traffic_limit_gb = Column(Integer, nullable=True)  # Monthly traffic limit (None = unlimited)
    bandwidth_limit_mbps = Column(Integer, nullable=True)  # Speed limit (None = unlimited)

    # Billing
    price_monthly_usd = Column(Float, nullable=True)  # Monthly price in USD
    billing_cycle_days = Column(Integer, default=30)  # Billing cycle

    # Dates
    start_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expiry_date = Column(DateTime, nullable=True)
    last_renewal = Column(DateTime, nullable=True)
    next_billing_date = Column(DateTime, nullable=True)

    # Auto-renewal
    auto_renew = Column(Boolean, default=False)
    auto_renew_failures = Column(Integer, default=0)

    # Notification dedup: {"3day": "iso", "1day": "iso", "0day": "iso"}
    notification_sent_at = Column(JSON, default=lambda: {})

    # Traffic tracking
    traffic_used_rx = Column(BigInteger, default=0)  # Bytes received
    traffic_used_tx = Column(BigInteger, default=0)  # Bytes transmitted
    traffic_reset_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))  # When to reset traffic counter

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("ClientUser", back_populates="subscription")

    __table_args__ = (
        Index("ix_cps_status", "status"),
        Index("ix_cps_expiry_date", "expiry_date"),
        Index("ix_cps_status_tier", "status", "tier"),
    )

    def _aware_expiry(self):
        """Return expiry_date as timezone-aware datetime"""
        if not self.expiry_date:
            return None
        if self.expiry_date.tzinfo is None:
            return self.expiry_date.replace(tzinfo=timezone.utc)
        return self.expiry_date

    @property
    def is_active(self) -> bool:
        """Check if subscription is currently active"""
        if self.status != SubscriptionStatus.ACTIVE:
            return False
        expiry = self._aware_expiry()
        if expiry and datetime.now(timezone.utc) >= expiry:
            return False
        return True

    @property
    def is_expired(self) -> bool:
        """Check if subscription has expired"""
        expiry = self._aware_expiry()
        if not expiry:
            return False
        return datetime.now(timezone.utc) >= expiry

    @property
    def days_remaining(self) -> Optional[int]:
        """Days until expiry (ceiling — e.g. 23h remaining → 1 day, not 0)"""
        expiry = self._aware_expiry()
        if not expiry:
            return None
        delta = expiry - datetime.now(timezone.utc)
        total_seconds = delta.total_seconds()
        if total_seconds <= 0:
            return 0
        import math
        return math.ceil(total_seconds / 86400)

    @property
    def traffic_used_total_gb(self) -> float:
        """Total traffic used in GB"""
        return (self.traffic_used_rx + self.traffic_used_tx) / (1024 ** 3)

    @property
    def traffic_remaining_gb(self) -> Optional[float]:
        """Remaining traffic in GB"""
        if self.traffic_limit_gb is None:
            return None
        return max(0, self.traffic_limit_gb - self.traffic_used_total_gb)

    @property
    def traffic_percentage_used(self) -> Optional[int]:
        """Percentage of traffic used (0-100)"""
        if self.traffic_limit_gb is None:
            return None
        if self.traffic_limit_gb == 0:
            return 100
        return min(100, int((self.traffic_used_total_gb / self.traffic_limit_gb) * 100))

    def __repr__(self):
        return f"<Subscription user_id={self.user_id} tier={self.tier} status={self.status.value}>"


# ═══════════════════════════════════════════════════════════════════════════
# PAYMENT MODEL
# ═══════════════════════════════════════════════════════════════════════════

class ClientPortalPayment(Base):
    """Payment transaction"""
    __tablename__ = "client_portal_payments"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("client_users.id"), nullable=False)

    # Payment details
    invoice_id = Column(String(255), unique=True, nullable=False, index=True)
    amount_usd = Column(Float, nullable=False)  # Amount in USD
    payment_method = Column(SQLEnum(PaymentMethod), nullable=False)

    # Crypto details
    crypto_amount = Column(String(50), nullable=True)  # Amount in crypto
    crypto_address = Column(String(255), nullable=True)  # Payment address
    crypto_tx_hash = Column(String(255), nullable=True, index=True)  # Transaction hash
    confirmations = Column(Integer, default=0)

    # Status
    status = Column(String(50), default="pending")  # pending, completed, expired, failed

    # Purpose
    subscription_tier = Column(String(50), nullable=True)
    duration_days = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)

    # Promo code applied
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=True)
    discount_amount_usd = Column(Float, nullable=True)  # Discount applied

    # Provider details
    provider_name = Column(String(50), nullable=True)  # nowpayments, coingate, etc.
    provider_invoice_id = Column(String(255), nullable=True)
    provider_data = Column(Text, nullable=True)  # JSON data from provider

    # Payment pipeline tracing
    trace_id = Column(String(64), nullable=True, index=True)  # e.g. "pay_<invoice_id>_<ts>"
    pipeline_log = Column(Text, nullable=True)  # JSON array of pipeline steps
    pipeline_status = Column(String(20), default="ok")  # ok | inconsistent

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    expires_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("ClientUser", back_populates="payments")

    @property
    def is_completed(self) -> bool:
        """Check if payment is completed"""
        return self.status == "completed"

    @property
    def is_pending(self) -> bool:
        """Check if payment is pending"""
        return self.status == "pending"

    @property
    def is_expired(self) -> bool:
        """Check if payment has expired"""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    def set_provider_data(self, data: dict):
        """Set provider data as JSON"""
        self.provider_data = json.dumps(data)

    def get_provider_data(self) -> dict:
        """Get provider data from JSON"""
        if not self.provider_data:
            return {}
        try:
            return json.loads(self.provider_data)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to parse provider_data for payment: {e}")
            return {}

    __table_args__ = (
        Index("ix_cpp_user_id", "user_id"),
        Index("ix_cpp_status", "status"),
        Index("ix_cpp_user_status", "user_id", "status"),
    )

    def __repr__(self):
        return f"<Payment {self.invoice_id} {self.amount_usd} USD via {self.payment_method.value}>"


# ═══════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION PLAN MODEL
# ═══════════════════════════════════════════════════════════════════════════

class SubscriptionPlan(Base):
    """Available subscription plans"""
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True)

    # Plan details
    tier = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Features
    max_devices = Column(Integer, default=1)
    traffic_limit_gb = Column(Integer, nullable=True)  # None = unlimited
    bandwidth_limit_mbps = Column(Integer, nullable=True)  # None = unlimited

    # Pricing
    price_monthly_usd = Column(Float, nullable=False)
    price_quarterly_usd = Column(Float, nullable=True)
    price_yearly_usd = Column(Float, nullable=True)

    # Availability
    is_active = Column(Boolean, default=True)
    is_visible = Column(Boolean, default=True)

    # Order (for display)
    display_order = Column(Integer, default=0)

    # Extended features (e.g. {"corp_networks": 5, "corp_sites": 10})
    features = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<SubscriptionPlan {self.tier} - ${self.price_monthly_usd}/mo>"


# ═══════════════════════════════════════════════════════════════════════════
# PROMO CODE MODEL
# ═══════════════════════════════════════════════════════════════════════════

class PromoCode(Base):
    """Promotional codes for discounts and free days"""
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)

    # Discount type: 'percent' or 'days'
    discount_type = Column(String(20), nullable=False, default="percent")  # percent | days
    discount_value = Column(Float, nullable=False)  # e.g. 20 (=20%) or 7 (=7 free days)

    # Restrictions
    max_uses = Column(Integer, nullable=True)  # None = unlimited
    used_count = Column(Integer, default=0)
    applies_to_tier = Column(String(50), nullable=True)  # None = all tiers
    min_duration_days = Column(Integer, nullable=True)  # Min subscription duration to apply

    # Validity
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)

    # Metadata
    created_by = Column(String(100), nullable=True)  # admin username
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        if self.expires_at:
            exp = self.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= exp:
                return False
        return True

    def __repr__(self):
        return f"<PromoCode {self.code} {self.discount_type}={self.discount_value}>"


# ═══════════════════════════════════════════════════════════════════════════
# LINKING TABLE
# ═══════════════════════════════════════════════════════════════════════════

class ClientUserClients(Base):
    """Link ClientUser to WireGuard Clients"""
    __tablename__ = "client_user_clients"
    __table_args__ = (
        UniqueConstraint('client_user_id', 'client_id', name='uq_user_client'),
    )

    id = Column(Integer, primary_key=True)
    client_user_id = Column(Integer, ForeignKey("client_users.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<ClientUserClients user={self.client_user_id} client={self.client_id}>"


# ═══════════════════════════════════════════════════════════════════════════
# SUPPORT MESSAGE MODEL
# ═══════════════════════════════════════════════════════════════════════════

class SupportMessage(Base):
    """Support ticket / message between user and admin"""
    __tablename__ = "support_messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("client_users.id"), nullable=False)

    # Message content
    subject = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)

    # Direction: 'user' = from user, 'admin' = admin reply
    direction = Column(String(10), nullable=False, default="user")  # user | admin

    # Threading: replies reference parent message
    parent_id = Column(Integer, ForeignKey("support_messages.id"), nullable=True)

    # Status (only on root messages, not replies)
    status = Column(String(20), default="open")  # open | answered | closed

    # Read tracking
    is_read = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    user = relationship("ClientUser", backref="support_messages")
    replies = relationship("SupportMessage", backref="parent", remote_side=[id], foreign_keys=[parent_id])

    __table_args__ = (
        Index("ix_sm_user_id", "user_id"),
        Index("ix_sm_parent_id", "parent_id"),
        Index("ix_sm_status", "status"),
    )

    def __repr__(self):
        return f"<SupportMessage id={self.id} user={self.user_id} dir={self.direction} status={self.status}>"
