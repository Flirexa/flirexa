"""
VPN Management Studio Client Portal - ClientPortalSubscription Manager
Business logic for subscription management
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
import bcrypt
import secrets
import logging

from src.modules.subscription.subscription_models import (
    ClientUser, ClientPortalSubscription, ClientPortalPayment, SubscriptionPlan,
    SubscriptionTier, SubscriptionStatus, PaymentMethod, ClientUserClients
)

# Client model import — only needed for legacy direct-DB operations (admin bot).
# Client portal uses AdminAPIClient instead.
try:
    from src.database.models import Client, ClientStatus
except ImportError:
    Client = None
    ClientStatus = None

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """
    Manages user subscriptions, upgrades, renewals, and billing

    Usage:
        manager = SubscriptionManager(db_session)
        user = manager.create_user("user@example.com", "password123", "johndoe")
        subscription = manager.create_subscription(user.id, SubscriptionTier.BASIC)
    """

    def __init__(self, db: Session):
        self.db = db

    # ═══════════════════════════════════════════════════════════════════════
    # USER MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════

    def create_user(
        self,
        email: str,
        password: str,
        username: str,
        full_name: Optional[str] = None,
        telegram_id: Optional[str] = None
    ) -> Tuple[Optional[ClientUser], Optional[str]]:
        """
        Create a new client user

        Returns:
            (user, error_message)
        """
        # Validate email uniqueness
        if self.db.query(ClientUser).filter(ClientUser.email == email).first():
            return None, "Email already registered"

        # Validate username uniqueness
        if self.db.query(ClientUser).filter(ClientUser.username == username).first():
            return None, "Username already taken"

        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Generate verification token
        verification_token = secrets.token_urlsafe(32)

        # Create user
        user = ClientUser(
            email=email,
            password_hash=password_hash,
            username=username,
            full_name=full_name,
            telegram_id=telegram_id,
            verification_token=verification_token,
            email_verified=False
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        # Create free subscription (graceful — skip if no free plan defined)
        try:
            self.create_subscription(user.id, "free")
        except ValueError:
            # No free plan found — create a minimal free subscription directly
            sub = ClientPortalSubscription(
                user_id=user.id,
                tier="free",
                status=SubscriptionStatus.ACTIVE,
                max_devices=1,
                traffic_limit_gb=10,
                bandwidth_limit_mbps=50,
                price_monthly_usd=0,
            )
            self.db.add(sub)
            self.db.commit()

        logger.info(f"Created user: {username} ({email})")
        return user, None

    def authenticate_user(self, email: str, password: str) -> Optional[ClientUser]:
        """Authenticate user by email and password"""
        user = self.db.query(ClientUser).filter(ClientUser.email == email).first()
        if not user:
            return None

        if not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            return None

        if not user.is_active or user.is_banned:
            return None

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        self.db.commit()

        return user

    def verify_email(self, token: str) -> bool:
        """Verify user email with token"""
        user = self.db.query(ClientUser).filter(ClientUser.verification_token == token).first()
        if not user:
            return False

        user.email_verified = True
        user.verification_token = None
        self.db.commit()

        logger.info(f"Email verified: {user.email}")
        return True

    def get_user_by_id(self, user_id: int) -> Optional[ClientUser]:
        """Get user by ID"""
        return self.db.query(ClientUser).filter(ClientUser.id == user_id).first()

    def get_user_by_telegram_id(self, telegram_id: str) -> Optional[ClientUser]:
        """Get user by Telegram ID"""
        return self.db.query(ClientUser).filter(ClientUser.telegram_id == telegram_id).first()

    # ═══════════════════════════════════════════════════════════════════════
    # SUBSCRIPTION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════

    def create_subscription(
        self,
        user_id: int,
        tier: str,
        duration_days: int = 30
    ) -> ClientPortalSubscription:
        """Create a new subscription for user"""
        # Get plan details
        plan = self.get_plan_by_tier(tier)
        if not plan:
            raise ValueError(f"Plan not found for tier: {tier}")

        # Check if user already has subscription
        existing = self.get_subscription(user_id)
        if existing:
            raise ValueError("User already has a subscription")

        expiry_date = datetime.now(timezone.utc) + timedelta(days=duration_days) if tier != "free" else None

        subscription = ClientPortalSubscription(
            user_id=user_id,
            tier=tier,
            status=SubscriptionStatus.ACTIVE,
            max_devices=plan.max_devices,
            traffic_limit_gb=plan.traffic_limit_gb,
            bandwidth_limit_mbps=plan.bandwidth_limit_mbps,
            price_monthly_usd=plan.price_monthly_usd,
            billing_cycle_days=duration_days,
            expiry_date=expiry_date,
            next_billing_date=expiry_date
        )

        self.db.add(subscription)
        self.db.commit()
        self.db.refresh(subscription)

        logger.info(f"Created subscription for user {user_id}: {tier} for {duration_days} days")
        return subscription

    def get_subscription(self, user_id: int) -> Optional[ClientPortalSubscription]:
        """Get user's subscription"""
        return self.db.query(ClientPortalSubscription).filter(ClientPortalSubscription.user_id == user_id).first()

    def ensure_subscription(self, user_id: int) -> Optional[ClientPortalSubscription]:
        """Get or create subscription for user. Creates free tier if none exists."""
        sub = self.get_subscription(user_id)
        if sub:
            return sub
        # Try to create via create_subscription (picks limits from free plan in DB)
        try:
            return self.create_subscription(user_id, "free")
        except Exception as _free_err:
            logger.warning(
                "ensure_subscription: create_subscription(free) failed for user %d: %s — using hardcoded fallback",
                user_id, _free_err,
            )
        # Ultimate fallback: hardcoded minimal free subscription
        sub = ClientPortalSubscription(
            user_id=user_id,
            tier="free",
            status=SubscriptionStatus.ACTIVE,
            max_devices=1,
            traffic_limit_gb=10,
            bandwidth_limit_mbps=50,
            price_monthly_usd=0,
        )
        self.db.add(sub)
        self.db.commit()
        self.db.refresh(sub)
        logger.info(f"Auto-created free subscription for user {user_id}")
        return sub

    def upgrade_subscription(
        self,
        user_id: int,
        new_tier: str,
        duration_days: int = 30
    ) -> Tuple[Optional[ClientPortalSubscription], Optional[str]]:
        """
        Upgrade user subscription

        Returns:
            (subscription, error_message)
        """
        subscription = self.get_subscription(user_id)
        if not subscription:
            return None, "No subscription found"

        plan = self.get_plan_by_tier(new_tier)
        if not plan:
            return None, "Plan not found"

        # Update subscription — use canonical tier name from DB (preserves original casing)
        subscription.tier = plan.tier
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.max_devices = plan.max_devices
        subscription.traffic_limit_gb = plan.traffic_limit_gb
        subscription.bandwidth_limit_mbps = plan.bandwidth_limit_mbps
        subscription.price_monthly_usd = plan.price_monthly_usd
        subscription.billing_cycle_days = duration_days

        # Extend expiry date
        if subscription.expiry_date:
            expiry = subscription.expiry_date.replace(tzinfo=timezone.utc) if subscription.expiry_date.tzinfo is None else subscription.expiry_date
            subscription.expiry_date = max(expiry, datetime.now(timezone.utc)) + timedelta(days=duration_days)
        else:
            subscription.expiry_date = datetime.now(timezone.utc) + timedelta(days=duration_days)

        subscription.next_billing_date = subscription.expiry_date
        subscription.last_renewal = datetime.now(timezone.utc)

        # Reset traffic counters on upgrade
        subscription.traffic_used_rx = 0
        subscription.traffic_used_tx = 0
        subscription.traffic_reset_date = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(subscription)

        logger.info(f"Upgraded subscription for user {user_id} to {new_tier}")
        return subscription, None

    def renew_subscription(self, user_id: int, duration_days: int = 30) -> Tuple[Optional[ClientPortalSubscription], Optional[str]]:
        """Renew user subscription"""
        subscription = self.get_subscription(user_id)
        if not subscription:
            return None, "No subscription found"

        # Extend expiry date
        if subscription.expiry_date:
            expiry = subscription.expiry_date.replace(tzinfo=timezone.utc) if subscription.expiry_date.tzinfo is None else subscription.expiry_date
            subscription.expiry_date = max(expiry, datetime.now(timezone.utc)) + timedelta(days=duration_days)
        else:
            subscription.expiry_date = datetime.now(timezone.utc) + timedelta(days=duration_days)

        subscription.status = SubscriptionStatus.ACTIVE
        subscription.next_billing_date = subscription.expiry_date
        subscription.last_renewal = datetime.now(timezone.utc)

        # Reset traffic counters on renewal
        subscription.traffic_used_rx = 0
        subscription.traffic_used_tx = 0
        subscription.traffic_reset_date = datetime.now(timezone.utc)

        # Clear notification dedup flags
        subscription.notification_sent_at = {}

        self.db.commit()
        self.db.refresh(subscription)

        logger.info(f"Renewed subscription for user {user_id} for {duration_days} days")
        return subscription, None

    def cancel_subscription(self, user_id: int) -> bool:
        """Cancel user subscription (downgrade to free at expiry)"""
        subscription = self.get_subscription(user_id)
        if not subscription:
            return False

        subscription.auto_renew = False
        subscription.status = SubscriptionStatus.CANCELLED

        self.db.commit()

        logger.info(f"Cancelled subscription for user {user_id}")
        return True

    def check_and_expire_subscriptions(self) -> int:
        """
        Check all subscriptions and expire if needed
        Run this periodically (e.g., hourly cron job)

        Returns:
            Number of expired subscriptions
        """
        expired_subs = self.db.query(ClientPortalSubscription).filter(
            ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
            ClientPortalSubscription.expiry_date <= datetime.now(timezone.utc).replace(tzinfo=None)  # naive comparison — expiry_date column is tz-naive
        ).with_for_update(skip_locked=True).all()

        count = 0
        expired_user_ids = []
        free_plan = self.get_plan_by_tier("free")  # Cache: one query instead of N
        for sub in expired_subs:
            sub.status = SubscriptionStatus.EXPIRED
            # Downgrade to free tier
            if free_plan:
                sub.tier = "free"
                sub.max_devices = free_plan.max_devices
                sub.traffic_limit_gb = free_plan.traffic_limit_gb
                sub.bandwidth_limit_mbps = free_plan.bandwidth_limit_mbps

            expired_user_ids.append(sub.user_id)
            logger.info(f"Expired subscription for user {sub.user_id}")
            count += 1

        if count > 0:
            self.db.commit()
            # Downgrade WG limits and disable clients for expired users
            for uid in expired_user_ids:
                try:
                    self.apply_subscription_limits(uid)
                    # Disable WG clients (subscription expired, no more access)
                    self._disable_user_clients(uid, reason="SUBSCRIPTION_EXPIRED")
                except Exception as e:
                    logger.error(f"Failed to apply limits after expiry for user {uid}: {e}")

        return count

    # ═══════════════════════════════════════════════════════════════════════
    # SUBSCRIPTION PLANS
    # ═══════════════════════════════════════════════════════════════════════

    def get_plan_by_tier(self, tier) -> Optional[SubscriptionPlan]:
        """Get subscription plan by tier (case-insensitive)"""
        from sqlalchemy import func as sa_func
        # Accept both enum and string
        tier_str = tier.value if hasattr(tier, 'value') else str(tier)
        return self.db.query(SubscriptionPlan).filter(
            sa_func.lower(SubscriptionPlan.tier) == tier_str.lower()
        ).first()

    def get_all_plans(self, active_only: bool = True) -> List[SubscriptionPlan]:
        """Get all subscription plans"""
        query = self.db.query(SubscriptionPlan)
        if active_only:
            query = query.filter(SubscriptionPlan.is_active == True, SubscriptionPlan.is_visible == True)
        return query.order_by(SubscriptionPlan.display_order).all()

    def create_default_plans(self):
        """Create default subscription plans"""
        plans = [
            {
                "tier": "free",
                "name": "Free",
                "description": "Basic access for testing",
                "max_devices": 1,
                "traffic_limit_gb": 10,
                "bandwidth_limit_mbps": 10,
                "price_monthly_usd": 0,
                "display_order": 0
            },
            {
                "tier": "basic",
                "name": "Basic",
                "description": "Perfect for casual users",
                "max_devices": 2,
                "traffic_limit_gb": 50,
                "bandwidth_limit_mbps": 50,
                "price_monthly_usd": 5.0,
                "price_quarterly_usd": 13.5,
                "price_yearly_usd": 48.0,
                "display_order": 1
            },
            {
                "tier": "standard",
                "name": "Standard",
                "description": "For regular users",
                "max_devices": 5,
                "traffic_limit_gb": 200,
                "bandwidth_limit_mbps": 100,
                "price_monthly_usd": 10.0,
                "price_quarterly_usd": 27.0,
                "price_yearly_usd": 96.0,
                "display_order": 2,
                "features": {"corp_networks": 1, "corp_sites": 5},
            },
            {
                "tier": "premium",
                "name": "Premium",
                "description": "Unlimited traffic and maximum speed",
                "max_devices": 10,
                "traffic_limit_gb": None,  # Unlimited
                "bandwidth_limit_mbps": None,  # Unlimited
                "price_monthly_usd": 20.0,
                "price_quarterly_usd": 54.0,
                "price_yearly_usd": 192.0,
                "display_order": 3,
                "features": {"corp_networks": 3, "corp_sites": 20},
            },
        ]

        for plan_data in plans:
            existing = self.get_plan_by_tier(plan_data["tier"])
            if not existing:
                plan = SubscriptionPlan(**plan_data)
                self.db.add(plan)

        self.db.commit()
        logger.info("Created default subscription plans")

    # ═══════════════════════════════════════════════════════════════════════
    # PAYMENT MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════

    def create_payment(
        self,
        user_id: int,
        amount_usd: float,
        payment_method: PaymentMethod,
        subscription_tier: str,
        duration_days: int,
        invoice_id: str,
        provider_name: str
    ) -> ClientPortalPayment:
        """Create a payment record. Cancels any existing pending payments for the user
        before creating a new one to avoid orphaned invoices."""
        # Fix M-4: cancel duplicate pending payments so the user doesn't end up
        # with multiple open invoices that could all complete independently.
        now_cancel = datetime.now(timezone.utc)
        pending = self.db.query(ClientPortalPayment).filter(
            ClientPortalPayment.user_id == user_id,
            ClientPortalPayment.status == "pending",
        ).all()
        for old in pending:
            old.status = "cancelled"
            old.completed_at = now_cancel
        if pending:
            self.db.flush()
            logger.info(f"Cancelled {len(pending)} pending payment(s) for user {user_id} before creating new invoice")

        payment = ClientPortalPayment(
            user_id=user_id,
            invoice_id=invoice_id,
            amount_usd=amount_usd,
            payment_method=payment_method,
            subscription_tier=subscription_tier,
            duration_days=duration_days,
            provider_name=provider_name,
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )

        self.db.add(payment)
        self.db.commit()
        self.db.refresh(payment)

        logger.info(f"Created payment {invoice_id} for user {user_id}: ${amount_usd} via {payment_method.value}")
        return payment

    def complete_payment(self, invoice_id: str, tx_hash: Optional[str] = None, sync_wg: bool = True) -> bool:
        """
        Mark payment as completed and activate subscription.

        Args:
            invoice_id: Payment invoice ID
            tx_hash: Optional transaction hash
            sync_wg: If True, apply WG limits via direct DB (legacy/admin mode).
                      If False, caller handles WG sync via admin API.
        """
        from sqlalchemy import text as _sql_text

        # Acquire row-level lock to prevent duplicate processing under concurrent webhooks.
        # with_for_update() translates to SELECT FOR UPDATE on PostgreSQL (serializes concurrent
        # calls for the same invoice). SQLite ignores the hint gracefully.
        try:
            payment = (
                self.db.query(ClientPortalPayment)
                .filter(ClientPortalPayment.invoice_id == invoice_id)
                .with_for_update()
                .first()
            )
        except Exception as _fup_err:
            logger.debug(
                "complete_payment: with_for_update() not supported (invoice=%s): %s — using plain query",
                invoice_id, _fup_err,
            )
            # Fallback for DBs that don't support FOR UPDATE (e.g. SQLite in tests)
            payment = self.db.query(ClientPortalPayment).filter(
                ClientPortalPayment.invoice_id == invoice_id
            ).first()

        if not payment:
            logger.error(
                "[PAY] complete_payment: invoice_id=%s not found in DB", invoice_id
            )
            return False

        # Attach pipeline tracer
        try:
            from src.modules.payment.payment_tracer import PaymentTracer
            tracer = PaymentTracer(self.db, payment)
        except Exception as _tr_err:
            logger.debug("PaymentTracer init failed for %s: %s", invoice_id, _tr_err)
            tracer = None

        # Idempotency: re-check status inside lock — concurrent call will see "completed" here
        if payment.status == "completed":
            logger.info(f"Payment {invoice_id} already completed, skipping")
            return True

        payment.status = "completed"
        payment.completed_at = datetime.now(timezone.utc)
        if tx_hash:
            payment.crypto_tx_hash = tx_hash

        if tracer:
            tracer.step("activate", status="ok", detail={
                "user_id": payment.user_id,
                "tier": payment.subscription_tier,
                "days": payment.duration_days,
                "tx_hash": tx_hash,
            })

        # Atomic promo code increment — avoids lost-update from ORM read-modify-write
        if payment.promo_code_id:
            try:
                self.db.execute(
                    _sql_text(
                        "UPDATE promo_codes SET used_count = COALESCE(used_count, 0) + 1 WHERE id = :id"
                    ),
                    {"id": payment.promo_code_id},
                )
            except Exception as _e:
                logger.warning(f"Promo code increment failed for id={payment.promo_code_id}: {_e}")

        # Check if user is banned/inactive — record payment but don't activate subscription
        user = self.get_user_by_id(payment.user_id)
        if user and (user.is_banned or not user.is_active):
            self.db.commit()
            logger.warning(
                "[PAY:%s] completed for restricted user %d — subscription NOT activated",
                invoice_id, payment.user_id,
            )
            if tracer:
                tracer.step("activate", status="warn", detail={"reason": "user_banned_or_inactive"})
            return True

        # Activate or upgrade subscription (ensure one exists)
        subscription = self.ensure_subscription(payment.user_id)
        if subscription and payment.subscription_tier:
            self.upgrade_subscription(
                payment.user_id,
                payment.subscription_tier,
                payment.duration_days or 30
            )

        self.db.commit()

        # Apply WG limits only in direct-DB mode (admin bot, simulate-payment)
        if sync_wg and Client is not None:
            try:
                self.apply_subscription_limits(payment.user_id, reset_traffic=True)
                existing_clients = self.get_user_wireguard_clients(payment.user_id)
                if not existing_clients:
                    try:
                        self.auto_create_wireguard_client(payment.user_id)
                    except Exception as e:
                        logger.error(
                            "[PAY:%s] Failed to auto-create WG client for user %d: %s",
                            invoice_id, payment.user_id, e,
                        )
                if tracer:
                    tracer.step("sync_wg", status="ok", detail={"sync_wg": True})
            except Exception as e:
                logger.error(
                    "[PAY:%s] sync_wg failed for user %d: %s", invoice_id, payment.user_id, e
                )
                if tracer:
                    tracer.step("sync_wg", status="error", detail={"error": str(e)})

        # Referral reward: add 7 days to referrer on first paid subscription
        try:
            user = self.get_user_by_id(payment.user_id)
            if user and user.referred_by_id and payment.subscription_tier and payment.subscription_tier != "free":
                # Check if this is user's first completed paid payment
                first_paid = self.db.query(ClientPortalPayment).filter(
                    ClientPortalPayment.user_id == payment.user_id,
                    ClientPortalPayment.status == "completed",
                    ClientPortalPayment.subscription_tier != "free",
                ).count()
                if first_paid == 1:  # This is the first one (just completed)
                    referrer_sub = self.get_subscription(user.referred_by_id)
                    if referrer_sub and referrer_sub.expiry_date and referrer_sub.status == SubscriptionStatus.ACTIVE:
                        from datetime import timedelta
                        expiry = referrer_sub.expiry_date
                        if expiry.tzinfo is None:
                            expiry = expiry.replace(tzinfo=timezone.utc)
                        referrer_sub.expiry_date = max(expiry, datetime.now(timezone.utc)) + timedelta(days=7)
                        self.db.commit()
                        logger.info(f"Referral reward: +7 days for user {user.referred_by_id} (referred {user.username})")
        except Exception as e:
            logger.error(f"Referral reward error: {e}")

        # Send notifications
        try:
            from src.modules.notifications import NotificationService
            ns = NotificationService(self.db)
            user = self.get_user_by_id(payment.user_id)
            sub = self.get_subscription(payment.user_id)
            if user and sub:
                expiry_str = sub.expiry_date.strftime("%Y-%m-%d") if sub.expiry_date else "N/A"
                ns.notify_user_payment_confirmed(payment.user_id, sub.tier, payment.duration_days or 30, expiry_str)
                ns.notify_admin_new_payment(user.username, payment.amount_usd, sub.tier, payment.payment_method.value if payment.payment_method else "unknown")
        except Exception as e:
            logger.debug(f"Payment notification error (non-critical): {e}")

        logger.info(f"Completed payment {invoice_id} for user {payment.user_id}")
        return True

    def get_payment_by_invoice(self, invoice_id: str) -> Optional[ClientPortalPayment]:
        """Get payment by invoice ID"""
        return self.db.query(ClientPortalPayment).filter(ClientPortalPayment.invoice_id == invoice_id).first()

    def get_user_payments(self, user_id: int, limit: int = 50) -> List[ClientPortalPayment]:
        """Get user's payment history"""
        return self.db.query(ClientPortalPayment).filter(
            ClientPortalPayment.user_id == user_id
        ).order_by(ClientPortalPayment.created_at.desc()).limit(limit).all()

    # ═══════════════════════════════════════════════════════════════════════
    # STATISTICS
    # ═══════════════════════════════════════════════════════════════════════

    def get_dashboard_stats(self, user_id: int) -> dict:
        """Get dashboard statistics for user"""
        subscription = self.get_subscription(user_id)
        if not subscription:
            return {}

        return {
            "subscription": {
                "tier": subscription.tier,
                "status": subscription.status.value,
                "expires_at": subscription.expiry_date.isoformat() if subscription.expiry_date else None,
                "days_remaining": subscription.days_remaining,
                "auto_renew": subscription.auto_renew
            },
            "limits": {
                "max_devices": subscription.max_devices,
                "traffic_limit_gb": subscription.traffic_limit_gb,
                "traffic_used_gb": round(subscription.traffic_used_total_gb, 2),
                "traffic_remaining_gb": round(subscription.traffic_remaining_gb, 2) if subscription.traffic_remaining_gb else None,
                "traffic_percentage": subscription.traffic_percentage_used,
                "bandwidth_limit_mbps": subscription.bandwidth_limit_mbps
            },
            "billing": {
                "price_monthly_usd": subscription.price_monthly_usd,
                "next_billing_date": subscription.next_billing_date.isoformat() if subscription.next_billing_date else None
            }
        }

    # ═══════════════════════════════════════════════════════════════════════
    # WIREGUARD LIMITS SYNC
    # ═══════════════════════════════════════════════════════════════════════

    def apply_subscription_limits(self, user_id: int, reset_traffic: bool = False) -> int:
        """
        Apply subscription limits to all linked WireGuard clients.
        Called after payment completion or subscription change.

        Args:
            reset_traffic: If True, reset WG client traffic counters (call on renewal to avoid
                           immediate re-ban: sync_traffic_from_wg_clients would otherwise
                           overwrite the subscription's reset with the old exceeded value).

        Returns:
            Number of WireGuard clients updated
        """
        subscription = self.get_subscription(user_id)
        if not subscription:
            logger.warning(f"No subscription found for user {user_id}")
            return 0

        # Find linked WireGuard clients
        links = self.db.query(ClientUserClients).filter(
            ClientUserClients.client_user_id == user_id
        ).all()

        if not links:
            logger.info(f"No WireGuard clients linked to user {user_id}")
            return 0

        client_ids = [link.client_id for link in links]
        wg_clients = self.db.query(Client).filter(Client.id.in_(client_ids)).all()

        updated = 0
        for wg_client in wg_clients:
            # Apply bandwidth limit (Mbps)
            if subscription.bandwidth_limit_mbps:
                wg_client.bandwidth_limit = subscription.bandwidth_limit_mbps

            # Apply traffic limit (convert GB to MB)
            if subscription.traffic_limit_gb:
                wg_client.traffic_limit_mb = int(subscription.traffic_limit_gb * 1024)
                wg_client.traffic_limit_expiry = subscription._aware_expiry()

            # Apply expiry date
            if subscription.expiry_date:
                wg_client.expiry_date = subscription._aware_expiry()

            updated += 1

        # Commit limit field updates first
        self.db.commit()

        # Reset WG traffic counters if requested (renewal path).
        # Without this, sync_traffic_from_wg_clients() reads the old exceeded counter
        # from Client.traffic_used_rx/tx and immediately overwrites sub.traffic_used_rx = 0,
        # causing check_traffic_exceeded() to re-ban the client on the next cycle.
        if reset_traffic and updated > 0:
            try:
                from src.core.management import ManagementCore
                core = ManagementCore(self.db)
                for wg_client in wg_clients:
                    core.reset_traffic_counter(wg_client.id)
            except Exception as e:
                logger.warning(f"Failed to reset WG traffic counters for user {user_id}: {e}")

        # Enable any disabled clients if subscription is active (adds WG peers)
        if subscription.status == SubscriptionStatus.ACTIVE:
            try:
                from src.core.client_manager import ClientManager
                cm = ClientManager(self.db)
                for wg_client in wg_clients:
                    if not wg_client.enabled:
                        cm.enable_client(wg_client.id)
            except Exception as e:
                logger.warning(f"Failed to re-enable WG peers for user {user_id}: {e}")

        # Fix H-1/H-3: enforce TC bandwidth rules on the server so the kernel-level
        # rate limiter reflects the new subscription tier immediately.
        # Proxy clients are silently skipped inside set_bandwidth_limit().
        if updated > 0:
            try:
                from src.core.traffic_manager import TrafficManager
                tm = TrafficManager(self.db)
                for wg_client in wg_clients:
                    bw = wg_client.bandwidth_limit or 0
                    iface = (wg_client.server.interface if wg_client.server else None) or "wg0"
                    try:
                        tm.set_bandwidth_limit(wg_client.id, bw, interface=iface)
                    except Exception as _e:
                        logger.warning(f"TC bandwidth enforcement failed for {wg_client.name}: {_e}")
            except Exception as e:
                logger.warning(f"TrafficManager init failed for user {user_id} TC enforcement: {e}")

        logger.info(f"Applied subscription limits to {updated} WireGuard clients for user {user_id}")
        return updated

    def _disable_user_clients(self, user_id: int, reason: str = "DISABLED") -> int:
        """Disable all WG clients for a user (removes WireGuard peers). Returns count of disabled clients."""
        if Client is None:
            return 0
        links = self.db.query(ClientUserClients).filter(
            ClientUserClients.client_user_id == user_id
        ).all()
        if not links:
            return 0
        client_ids = [link.client_id for link in links]
        wg_clients = self.db.query(Client).filter(
            Client.id.in_(client_ids), Client.enabled == True
        ).all()
        # Fix M-6: handle each client individually so that a failure on one peer
        # does not prevent the remaining clients from being processed.
        from src.core.client_manager import ClientManager
        cm = None
        try:
            cm = ClientManager(self.db)
        except Exception as e:
            logger.error(f"Cannot create ClientManager for user {user_id}: {e}")

        wg_reason = reason.lower() if reason.lower() in ("expired", "traffic") else None
        for c in wg_clients:
            try:
                if cm:
                    cm.disable_client(c.id, reason=wg_reason)
                else:
                    raise RuntimeError("ClientManager unavailable")
            except Exception as e:
                logger.warning(f"WG peer removal failed for client {c.name}: {e} — applying DB-only disable")
                c.enabled = False
                c.status = ClientStatus.DISABLED
                self.db.commit()
        return len(wg_clients)

    def get_user_wireguard_clients(self, user_id: int) -> list:
        """Get WireGuard clients linked to a portal user"""
        links = self.db.query(ClientUserClients).filter(
            ClientUserClients.client_user_id == user_id
        ).all()

        if not links:
            return []

        client_ids = [link.client_id for link in links]
        return self.db.query(Client).filter(Client.id.in_(client_ids)).all()

    def auto_create_wireguard_client(self, user_id: int, name: str = None) -> Optional[Client]:
        """
        Auto-create WireGuard client for a user after payment.
        Uses default server. Creates ClientUserClients link.
        Respects max_devices limit from subscription.

        Returns:
            Created Client or None if cannot create
        """
        subscription = self.get_subscription(user_id)
        if not subscription or subscription.status != SubscriptionStatus.ACTIVE:
            logger.warning(f"Cannot auto-create WG client for user {user_id}: no active subscription")
            return None

        # Check device limit
        existing_count = self.db.query(ClientUserClients).filter(
            ClientUserClients.client_user_id == user_id
        ).count()
        max_devices = subscription.max_devices or 1
        if existing_count >= max_devices:
            logger.info(f"User {user_id} already at device limit ({existing_count}/{max_devices})")
            return None

        # Get user info for naming
        user = self.db.query(ClientUser).filter(ClientUser.id == user_id).first()
        if not user:
            logger.error(f"User {user_id} not found")
            return None

        # Create WG client via ManagementCore
        from src.core.management import ManagementCore
        core = ManagementCore(self.db)

        client_name = (name.strip() if name and name.strip() else None) or f"{user.username}-{existing_count + 1}"

        # Calculate expiry days from actual expiry date to avoid days_remaining rounding issues
        if subscription.expiry_date:
            expiry = subscription._aware_expiry()
            import math as _math
            _delta_secs = (expiry - datetime.now(timezone.utc)).total_seconds()
            _expiry_days = max(1, _math.ceil(_delta_secs / 86400))
        else:
            _expiry_days = 30

        wg_client = core.create_client(
            name=client_name,
            server_id=None,  # uses get_default_server()
            bandwidth_limit=subscription.bandwidth_limit_mbps,
            traffic_limit_mb=int(subscription.traffic_limit_gb * 1024) if subscription.traffic_limit_gb else None,
            expiry_days=_expiry_days,
        )

        if not wg_client:
            logger.error(f"Failed to create WG client for user {user_id}")
            return None

        # Create link between portal user and WG client
        link = ClientUserClients(client_user_id=user_id, client_id=wg_client.id)
        self.db.add(link)
        self.db.commit()

        logger.info(f"Auto-created WG client '{client_name}' (id={wg_client.id}) for user {user_id}")
        return wg_client

    # ═══════════════════════════════════════════════════════════════════════
    # TRAFFIC SYNC (Portal subscriptions ← WireGuard clients)
    # ═══════════════════════════════════════════════════════════════════════

    def sync_traffic_from_wg_clients(self) -> int:
        """
        Sum rx/tx from linked WireGuard clients and write into portal subscription.
        Called periodically from monitoring loop. Uses batch query to avoid N+1.

        Returns:
            Number of subscriptions updated
        """
        if Client is None:
            return 0

        # Batch: one query to get aggregated traffic per portal user (avoids N+1)
        rows = self.db.query(
            ClientUserClients.client_user_id,
            func.coalesce(func.sum(Client.traffic_used_rx), 0).label("rx"),
            func.coalesce(func.sum(Client.traffic_used_tx), 0).label("tx"),
        ).join(Client, Client.id == ClientUserClients.client_id
        ).group_by(ClientUserClients.client_user_id).all()

        traffic_by_user = {r[0]: (r[1], r[2]) for r in rows}

        if not traffic_by_user:
            return 0

        subs = self.db.query(ClientPortalSubscription).filter(
            ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
            ClientPortalSubscription.user_id.in_(traffic_by_user.keys()),
        ).all()

        from datetime import timedelta
        updated = 0
        for sub in subs:
            total_rx, total_tx = traffic_by_user.get(sub.user_id, (0, 0))
            # Skip sync if subscription was just renewed in the last 60 seconds.
            # Without this guard, sync_traffic_from_wg_clients() would read the old
            # exceeded WG counter (Client.traffic_used_rx/tx) and overwrite the
            # subscription's freshly-reset counter, causing immediate re-ban.
            if sub.traffic_reset_date:
                reset_dt = sub.traffic_reset_date
                if reset_dt.tzinfo is None:
                    reset_dt = reset_dt.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - reset_dt).total_seconds() < 60:
                    continue
            if sub.traffic_used_rx != total_rx or sub.traffic_used_tx != total_tx:
                sub.traffic_used_rx = total_rx
                sub.traffic_used_tx = total_tx
                updated += 1

        if updated > 0:
            self.db.commit()

        return updated

    def check_traffic_exceeded(self) -> int:
        """
        Disable WireGuard clients for subscriptions that exceeded traffic limit.
        Uses batch queries to avoid N+1.

        Returns:
            Number of subscriptions that exceeded limit
        """
        if Client is None:
            return 0

        subs = self.db.query(ClientPortalSubscription).filter(
            ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
            ClientPortalSubscription.traffic_limit_gb.isnot(None),
            ClientPortalSubscription.traffic_limit_gb > 0,
        ).all()

        # Filter exceeded subs in Python
        exceeded_user_ids = [
            sub.user_id for sub in subs
            if sub.traffic_used_total_gb >= sub.traffic_limit_gb
        ]
        if not exceeded_user_ids:
            return 0

        # Batch: get all links for exceeded users
        links = self.db.query(ClientUserClients).filter(
            ClientUserClients.client_user_id.in_(exceeded_user_ids)
        ).all()
        if not links:
            return 0

        # Group client IDs by user
        from collections import defaultdict
        user_client_ids = defaultdict(list)
        for link in links:
            user_client_ids[link.client_user_id].append(link.client_id)

        all_client_ids = [link.client_id for link in links]

        # Batch: get all enabled WG clients
        wg_clients = self.db.query(Client).filter(
            Client.id.in_(all_client_ids),
            Client.enabled == True
        ).all()

        exceeded = 0
        exceeded_client_ids = set()
        for uid in exceeded_user_ids:
            exceeded_client_ids.update(user_client_ids.get(uid, []))

        disabled_count = 0
        try:
            from src.core.client_manager import ClientManager
            cm = ClientManager(self.db)
            for wg_client in wg_clients:
                if wg_client.id in exceeded_client_ids:
                    cm.disable_client(wg_client.id, reason="traffic")
                    disabled_count += 1
        except Exception as _cm_err:
            logger.error(
                "check_traffic_exceeded: ClientManager.disable_client failed — falling back to DB-only disable: %s",
                _cm_err,
            )
            # Fallback: update DB only if WG removal fails
            for wg_client in wg_clients:
                if wg_client.id in exceeded_client_ids:
                    wg_client.enabled = False
                    try:
                        from src.database.models import ClientStatus
                        wg_client.status = ClientStatus.TRAFFIC_EXCEEDED
                    except (ImportError, AttributeError):
                        wg_client.status = "TRAFFIC_EXCEEDED"
                    disabled_count += 1

        # Count how many users were affected
        affected_users = set()
        for wg_client in wg_clients:
            for uid, cids in user_client_ids.items():
                if wg_client.id in cids:
                    affected_users.add(uid)

        exceeded = len(affected_users)
        if exceeded > 0:
            for sub in subs:
                if sub.user_id in affected_users:
                    logger.info(
                        f"Traffic exceeded for user {sub.user_id}: "
                        f"{sub.traffic_used_total_gb:.1f}/{sub.traffic_limit_gb} GB"
                    )
            self.db.commit()

        return exceeded

    def migrate_telegram_clients(self) -> int:
        """
        Link existing Client.telegram_user_id clients to ClientUser accounts.
        One-time migration helper for bridging legacy Telegram user links.

        Returns:
            Number of new links created
        """
        clients_with_tg = self.db.query(Client).filter(
            Client.telegram_user_id.isnot(None)
        ).all()

        migrated = 0
        for client in clients_with_tg:
            tg_id = str(client.telegram_user_id)
            client_user = self.db.query(ClientUser).filter(
                ClientUser.telegram_id == tg_id
            ).first()

            if not client_user:
                continue

            # Check if link already exists
            existing = self.db.query(ClientUserClients).filter(
                ClientUserClients.client_user_id == client_user.id,
                ClientUserClients.client_id == client.id
            ).first()

            if not existing:
                link = ClientUserClients(client_user_id=client_user.id, client_id=client.id)
                self.db.add(link)
                migrated += 1

        self.db.commit()
        logger.info(f"Migrated {migrated} telegram client links")
        return migrated
