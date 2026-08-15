"""
Flirexa — Background Task Scheduler

Extracted from main.py to keep the FastAPI app file thin.
Contains monitoring cycle, backup scheduler, and task start/stop helpers.

Usage from main.py lifespan:
    from .scheduler import start_background_tasks, stop_background_tasks
    tasks = start_background_tasks()
    yield
    await stop_background_tasks(tasks)
"""

import asyncio
import os
import threading
from datetime import datetime, timedelta, timezone

from loguru import logger

from ..database.connection import SessionLocal


def _send_expiry_email_for_subscription(db, sub, days_left: int) -> None:
    """Look up the user, the panel's SMTP + branding config, and shoot
    off the expiry-warning email. Wrapped in try/except by the caller so
    SMTP misconfiguration / missing email never blocks the rest of the
    scheduler cycle.

    Returns silently on any of:
      * SMTP not configured (no host set)
      * user has no email on file
      * EmailService failed (returns False internally)
    """
    import os as _os
    from ..modules.email.email_service import EmailService
    from ..modules.subscription.subscription_models import ClientUser

    user = db.query(ClientUser).filter(ClientUser.id == sub.user_id).first()
    if not user or not user.email:
        return

    smtp_host = _os.getenv("SMTP_HOST", "").strip()
    if not smtp_host:
        return
    smtp_enabled = _os.getenv("SMTP_ENABLED", "false").lower() == "true"
    if not smtp_enabled:
        return

    service = EmailService(
        host=smtp_host,
        port=int(_os.getenv("SMTP_PORT", "587")),
        username=_os.getenv("SMTP_USERNAME", ""),
        password=_os.getenv("SMTP_PASSWORD", ""),
        tls=_os.getenv("SMTP_TLS", "true").lower() == "true",
        from_address=_os.getenv("SMTP_FROM", smtp_host),
    )

    expiry_str = sub.expiry_date.strftime("%Y-%m-%d") if sub.expiry_date else ""
    service.send_expiry_warning_email(
        to=user.email,
        username=user.username or (user.email or "user").split("@")[0],
        tier=sub.tier,
        days_left=days_left,
        expiry_date=expiry_str,
        portal_url=_os.getenv("CLIENT_PORTAL_URL", ""),
        app_name=_os.getenv("APP_NAME", "Flirexa"),
        support_email=_os.getenv("SUPPORT_EMAIL", ""),
        lang=(user.language or "en"),
    )


MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "60"))
_MONITOR_TIMEOUT = int(os.getenv("MONITOR_TIMEOUT", str(max(10, int(MONITOR_INTERVAL * 0.9)))))
_RECONCILE_TIMEOUT = int(os.getenv("RECONCILE_TIMEOUT", "120"))
_PENDING_PAYMENT_RECOVERY_BATCH = max(
    1, min(int(os.getenv("PENDING_PAYMENT_RECOVERY_BATCH", "3")), 10)
)
_PENDING_PAYMENT_RECOVERY_RETRY_SECONDS = max(
    60, min(int(os.getenv("PENDING_PAYMENT_RECOVERY_RETRY_SECONDS", "600")), 3600)
)
_PENDING_PAYMENT_EXPIRY_GRACE_SECONDS = max(
    60, min(int(os.getenv("PENDING_PAYMENT_EXPIRY_GRACE_SECONDS", "900")), 3600)
)
_STALE_PAYMENT_EXPIRY_BATCH = max(
    10, min(int(os.getenv("STALE_PAYMENT_EXPIRY_BATCH", "200")), 1000)
)
_monitor_cycle_lock = threading.Lock()
_reconcile_cycle_lock = threading.Lock()
_health_stamp_lock = threading.Lock()
# Health-stamp cadence: must stay well under client_portal's
# AUTO_HIDE_THRESHOLD_SECONDS (300) or visible servers would flap.
_HEALTH_STAMP_TIMEOUT = int(os.getenv("HEALTH_STAMP_TIMEOUT", "120"))


def _add_notification_marker(
    existing: dict | None, marker: str, when: datetime
) -> dict:
    """Return a new JSON value so SQLAlchemy persists the dedup marker."""

    updated = dict(existing or {})
    updated[marker] = when.isoformat()
    return updated


# ─── Pending payment recovery ────────────────────────────────────────────────

def _try_recover_pending_payments(db) -> None:
    """
    Re-check a small persisted batch of pending payments with the provider.
    This is the self-healing path for dropped webhooks.

    We ONLY recover payments that:
    - status == 'pending'
    - old enough to give the normal webhook a head start
    - not checked during the persisted retry window
    - have a known provider with a working check_payment()

    On a "completed" answer we call SubscriptionManager.complete_payment(),
    which is idempotent and will activate the subscription + sync WG. PayPal
    is routed through the portal's stricter capture-and-amount-verification
    helper instead of trusting its coarse status enum.
    """
    import asyncio as _asyncio
    from ..modules.subscription.subscription_models import ClientPortalPayment
    from ..modules.subscription.subscription_manager import SubscriptionManager
    from ..modules.payment.base import PaymentStatus
    from sqlalchemy import or_ as _or

    try:
        from ..api.routes import client_portal as _portal
    except ImportError:
        from ..api.routes.client_portal import (  # type: ignore[no-redef]
            cryptopay_adapter, paypal_provider, nowpayments_provider,
        )
        _portal = None

    now = datetime.now(timezone.utc)
    # Don't try to recover the absolute newest invoices — give the webhook
    # a head start (15s) so we don't race normal completion.
    young = now - timedelta(seconds=15)
    retry_before = now - timedelta(
        seconds=_PENDING_PAYMENT_RECOVERY_RETRY_SECONDS
    )
    candidates = db.query(ClientPortalPayment).filter(
        ClientPortalPayment.status == "pending",
        ClientPortalPayment.created_at <= young,
        _or(
            ClientPortalPayment.updated_at.is_(None),
            ClientPortalPayment.updated_at <= retry_before,
        ),
    ).order_by(
        # Rescue invoices nearest/past local expiry first; newer invoices still
        # have the normal webhook path and can wait for a later bounded batch.
        ClientPortalPayment.expires_at.asc(),
        ClientPortalPayment.updated_at.asc(),
        ClientPortalPayment.created_at.asc(),
    ).limit(_PENDING_PAYMENT_RECOVERY_BATCH).all()
    if not candidates:
        return

    manager = SubscriptionManager(db)
    recovered = 0

    for p in candidates:
        provider_name = (p.provider_name or "").lower()
        provider_invoice = p.provider_invoice_id or p.invoice_id
        if not provider_name or not provider_invoice:
            continue

        # Pick the right provider object (built-in or plugin).
        if _portal is not None:
            prov_obj = (
                getattr(_portal, "cryptopay_adapter", None) if provider_name == "cryptopay" else
                getattr(_portal, f"{provider_name}_provider", None)
            )
        else:
            prov_obj = None
        if not prov_obj or not hasattr(prov_obj, "check_payment"):
            continue

        # Claim the retry window before network I/O. The worker's overlap lock
        # protects normal cycles, while this persisted timestamp also prevents
        # a concurrent/manual cycle or process restart from hammering the same
        # provider record. A failed check becomes eligible again after the
        # bounded backoff.
        p.updated_at = now
        db.commit()

        if provider_name == "paypal" and _portal is not None:
            try:
                status = _asyncio.run(_portal._settle_paypal_payment(db, p))
            except RuntimeError:
                try:
                    loop = _asyncio.new_event_loop()
                    status = loop.run_until_complete(
                        _portal._settle_paypal_payment(db, p)
                    )
                    loop.close()
                except Exception as _e:
                    logger.debug(
                        "Recovery PayPal settlement({}) inner failed: {}",
                        p.invoice_id,
                        _e,
                    )
                    continue
            except Exception as _e:
                logger.debug(
                    "Recovery PayPal settlement({}) failed: {}",
                    p.invoice_id,
                    _e,
                )
                continue

            if str(status).lower() == "completed":
                recovered += 1
                logger.warning(
                    "Recovered dropped-webhook PayPal payment: invoice={} user={}",
                    p.invoice_id,
                    p.user_id,
                )
            continue

        try:
            status = _asyncio.run(prov_obj.check_payment(provider_invoice))
        except RuntimeError:
            # asyncio.run() can't nest inside an existing loop — fall back.
            try:
                loop = _asyncio.new_event_loop()
                status = loop.run_until_complete(prov_obj.check_payment(provider_invoice))
                loop.close()
            except Exception as _e:
                logger.debug("Recovery check_payment({}) inner failed: {}", p.invoice_id, _e)
                continue
        except Exception as _e:
            logger.debug("Recovery check_payment({}) failed: {}", p.invoice_id, _e)
            continue

        completed = (
            status == PaymentStatus.COMPLETED
            if isinstance(status, PaymentStatus)
            else str(status).lower() in ("completed", "paid", "finished", "success")
        )
        if not completed:
            continue

        try:
            manager.complete_payment(p.invoice_id, sync_wg=True)
            recovered += 1
            logger.warning(
                "Recovered dropped-webhook payment: invoice={} provider={} user={}",
                p.invoice_id, provider_name, p.user_id,
            )
        except Exception as _ce:
            logger.error("Recovery complete_payment failed for {}: {}", p.invoice_id, _ce)

    if recovered:
        logger.info("Pending-payment recovery: {} invoice(s) self-healed this cycle", recovered)


def _expire_stale_pending_payments(db, *, now: datetime | None = None) -> int:
    """Expire a bounded batch only after the provider-recovery grace window."""

    from ..modules.subscription.subscription_models import ClientPortalPayment

    current = now or datetime.now(timezone.utc)
    stale_before = current - timedelta(
        seconds=_PENDING_PAYMENT_EXPIRY_GRACE_SECONDS
    )
    rows = db.query(ClientPortalPayment).filter(
        ClientPortalPayment.status == "pending",
        ClientPortalPayment.expires_at != None,
        ClientPortalPayment.expires_at <= stale_before,
    ).order_by(
        ClientPortalPayment.expires_at.asc(),
        ClientPortalPayment.id.asc(),
    ).limit(_STALE_PAYMENT_EXPIRY_BATCH).all()
    if not rows:
        return 0
    for payment in rows:
        payment.status = "expired"
    db.commit()
    return len(rows)


# ─── Monitoring ───────────────────────────────────────────────────────────────

def monitoring_cycle():
    """Single monitoring cycle — runs synchronous DB/SSH work in a thread."""
    from ..core.management import ManagementCore
    from ..modules.subscription.subscription_manager import SubscriptionManager

    db = SessionLocal()
    try:
        # Portal traffic sync first (WG → subscription counters)
        mgr = SubscriptionManager(db)
        synced = mgr.sync_traffic_from_wg_clients()
        if synced > 0:
            logger.debug(f"Monitoring: synced traffic for {synced} portal subscriptions")

        # Automatic renewal is temporarily fail-closed. The protected adapter
        # clears historical opt-ins and grants no time until every renewal can
        # be tied to one newly verified provider settlement.
        try:
            from ..modules.subscription.auto_renewal import process_auto_renewals

            process_auto_renewals(db, mgr)
        except Exception as exc:
            logger.error("Auto-renewal cycle error: {}", exc)

        # Expire subscriptions after the safety pass above.
        expired = mgr.check_and_expire_subscriptions()
        if expired > 0:
            logger.info(f"Monitoring: expired {expired} portal subscriptions")

        exceeded = mgr.check_traffic_exceeded()
        if exceeded > 0:
            logger.info(f"Monitoring: {exceeded} portal subscriptions exceeded traffic limit")

        # Proactive notifications with dedup (multi-stage: 3d, 1d, 0d)
        try:
            from ..modules.notifications import NotificationService
            from ..modules.subscription.subscription_models import ClientUser, ClientPortalSubscription, SubscriptionStatus
            import math as _math
            ns = NotificationService(db)
            now = datetime.now(timezone.utc)
            now_naive = now.replace(tzinfo=None)
            warn_date_naive = now_naive + timedelta(days=7)

            expiring_subs = db.query(ClientPortalSubscription).filter(
                ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
                ClientPortalSubscription.tier != "free",
                ClientPortalSubscription.expiry_date != None,
                ClientPortalSubscription.expiry_date <= warn_date_naive,
                ClientPortalSubscription.expiry_date > now_naive,
            ).all()
            for sub in expiring_subs:
                expiry = sub._aware_expiry()
                secs_left = (expiry - now).total_seconds()
                days_left = _math.ceil(secs_left / 86400) if secs_left > 0 else 0
                original_sent = dict(sub.notification_sent_at or {})
                sent = dict(original_sent)

                # Email-side notification is best-effort. Fires alongside
                # Telegram / portal-push so customers who only gave us
                # an email still hear about expiry. SMTP failures / missing
                # config silently fall through to no-op.
                def _email_expiry(days):
                    try:
                        _send_expiry_email_for_subscription(db, sub, days)
                    except Exception as _ee:
                        logger.warning(
                            f"expiry email at {days}d for user {sub.user_id} failed: {_ee}"
                        )

                if days_left >= 6 and days_left <= 7 and "7day" not in sent:
                    ns.notify_user_expiry_warning(sub.user_id, "", 7, sub.tier)
                    ns.create_portal_notification(sub.user_id, "Subscription expiring soon", f"Your {sub.tier} plan expires in {days_left} days")
                    _email_expiry(days_left)
                    sent = _add_notification_marker(sent, "7day", now)
                elif days_left > 1 and days_left <= 3 and "3day" not in sent:
                    ns.notify_user_expiry_warning(sub.user_id, "", 3, sub.tier)
                    ns.create_portal_notification(sub.user_id, "Subscription expiring", f"Your {sub.tier} plan expires in {days_left} days")
                    _email_expiry(days_left)
                    sent = _add_notification_marker(sent, "3day", now)
                elif days_left == 1 and "1day" not in sent:
                    ns.notify_user_expiry_warning(sub.user_id, "", 1, sub.tier)
                    ns.create_portal_notification(sub.user_id, "Subscription expiring tomorrow", f"Your {sub.tier} plan expires tomorrow")
                    _email_expiry(1)
                    sent = _add_notification_marker(sent, "1day", now)

                if sent != original_sent:
                    sub.notification_sent_at = sent
            db.commit()

            active_subs = db.query(ClientPortalSubscription).filter(
                ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
                ClientPortalSubscription.traffic_limit_gb != None,
                ClientPortalSubscription.traffic_limit_gb > 0,
            ).all()
            for sub in active_subs:
                pct = sub.traffic_percentage_used
                sent = dict(sub.notification_sent_at or {})
                if pct and pct >= 90 and "traffic_90" not in sent:
                    ns.notify_user_traffic_warning(sub.user_id, "", pct, sub.tier)
                    ns.create_portal_notification(sub.user_id, "Traffic limit warning", f"You've used {pct}% of your traffic limit")
                    sub.notification_sent_at = _add_notification_marker(
                        sent, "traffic_90", now
                    )
                elif pct and pct >= 80 and "traffic_80" not in sent:
                    ns.notify_user_traffic_warning(sub.user_id, "", pct, sub.tier)
                    ns.create_portal_notification(sub.user_id, "Traffic limit warning", f"You've used {pct}% of your traffic limit")
                    sub.notification_sent_at = _add_notification_marker(
                        sent, "traffic_80", now
                    )
            db.commit()

            if expired > 0:
                for sub in db.query(ClientPortalSubscription).filter(
                    ClientPortalSubscription.status == SubscriptionStatus.EXPIRED
                ).order_by(ClientPortalSubscription.updated_at.desc()).limit(expired).all():
                    user = db.query(ClientUser).filter(ClientUser.id == sub.user_id).first()
                    if user:
                        ns.notify_admin_subscription_expired(user.username, sub.tier)
        except Exception as e:
            logger.debug(f"Notification check error (non-critical): {e}")

        # Recover a provider-confirmed payment before considering its local
        # invoice stale. A provider can confirm near expiry while its webhook
        # is lost; expiring the row first would suppress the only recovery
        # path and leave a paid customer without service.
        from ..modules.subscription.subscription_models import ClientPortalPayment
        try:
            _try_recover_pending_payments(db)
        except Exception as _rerr:
            logger.error("Pending-payment recovery failed: {}", _rerr)

        # Expire in bounded batches after a short reconciliation grace window.
        # Webhooks remain authoritative and complete_payment is idempotent, so
        # a genuinely late confirmed callback can still settle an expired row.
        expired_payments = _expire_stale_pending_payments(db)
        if expired_payments:
            logger.info(
                "Monitoring: expired {} stale pending payments",
                expired_payments,
            )

        # Older bucket: still pending after 6h with no recovery → louder warning
        # so admins can chase the provider directly.
        stuck_cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
        stuck_payment_count = db.query(ClientPortalPayment).filter(
            ClientPortalPayment.status == "pending",
            ClientPortalPayment.created_at <= stuck_cutoff,
        ).count()
        if stuck_payment_count:
            logger.warning(
                "Monitoring: {} payment(s) still pending for more than 6h "
                "after recovery attempts; review them in the admin panel or "
                "provider dashboard",
                stuck_payment_count,
            )

        # Core WG limits check (expiry, traffic for non-portal clients)
        core = ManagementCore(db)
        result = core.check_all_limits()
        if result["total_disabled"] > 0:
            logger.info(
                f"Monitoring: disabled {result['total_disabled']} clients "
                f"(expired: {result['expired_clients']}, "
                f"traffic: {result['traffic_exceeded_clients']})"
            )
    except Exception as e:
        logger.error(f"Monitoring cycle error: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _monitoring_cycle_guarded() -> bool:
    """Prevent overlapping monitoring cycles when a previous one is stuck."""
    if not _monitor_cycle_lock.acquire(blocking=False):
        logger.warning("Monitoring cycle still running — skipping overlapping run")
        return False
    try:
        monitoring_cycle()
        return True
    finally:
        _monitor_cycle_lock.release()


def _reconciliation_cycle_guarded() -> bool:
    """Prevent overlapping reconciliation cycles when a previous one is stuck."""
    if not _reconcile_cycle_lock.acquire(blocking=False):
        logger.warning("Reconciliation cycle still running — skipping overlapping run")
        return False
    try:
        from ..modules.state_reconciler import run_reconciliation
        run_reconciliation()
        return True
    finally:
        _reconcile_cycle_lock.release()


def _health_stamp_cycle_guarded() -> bool:
    """Run the server health checker from the WORKER on a fixed cadence.

    `last_good_health_at` (the input to the customer-facing auto-hide filter,
    see client_portal._server_auto_hidden) used to be stamped ONLY when the
    admin UI polled /health/servers — the checker had no scheduled runner. An
    operator who closes the dashboard (or a dashboard that stops calling the
    health endpoints) starves the stamp, and the auto-hide threshold can then
    hide healthy servers from portals and apps.

    quick=True keeps it cheap (no network pings beyond the health probe);
    the checker stamps each reachable server via its own thread-safe session.
    """
    if not _health_stamp_lock.acquire(blocking=False):
        logger.warning("Health-stamp cycle still running — skipping overlapping run")
        return False
    try:
        from ..modules.health.server_checker import ServerHealthChecker
        from ..database.models import Server
        db = SessionLocal()
        try:
            servers = db.query(Server).all()
            if servers:
                ServerHealthChecker(db_session=db).check_all(servers, quick=True)
        finally:
            db.close()
        return True
    finally:
        _health_stamp_lock.release()


async def monitoring_loop():
    """Background loop that runs monitoring_cycle in a thread."""
    logger.info(f"Monitoring started (interval: {MONITOR_INTERVAL}s)")
    _reconcile_counter = 0
    _RECONCILE_EVERY = max(1, 300 // MONITOR_INTERVAL)
    _health_counter = 0
    _HEALTH_EVERY = max(1, 120 // MONITOR_INTERVAL)
    while True:
        try:
            await asyncio.sleep(MONITOR_INTERVAL)
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(_monitoring_cycle_guarded),
                    timeout=_MONITOR_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Monitoring cycle exceeded timeout ({}s) — continuing without blocking API loop",
                    _MONITOR_TIMEOUT,
                )
            _health_counter += 1
            if _health_counter >= _HEALTH_EVERY:
                _health_counter = 0
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(_health_stamp_cycle_guarded),
                        timeout=_HEALTH_STAMP_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "Health-stamp cycle exceeded timeout ({}s) — continuing",
                        _HEALTH_STAMP_TIMEOUT,
                    )
                except Exception as _he:
                    logger.error(f"Health-stamp error: {_he}")
            _reconcile_counter += 1
            if _reconcile_counter >= _RECONCILE_EVERY:
                _reconcile_counter = 0
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(_reconciliation_cycle_guarded),
                        timeout=_RECONCILE_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "Reconciliation cycle exceeded timeout ({}s) — continuing without blocking API loop",
                        _RECONCILE_TIMEOUT,
                    )
                except Exception as _re:
                    logger.error(f"Reconciliation error: {_re}")
        except asyncio.CancelledError:
            logger.info("Monitoring stopped")
            break
        except Exception as e:
            logger.error(f"Monitoring error: {e}")


# ─── Commercial scheduled backup delegation ─────────────────────────────────

def backup_cycle():
    """Run one protected auto-backup cycle when the licence permits it."""
    from ..modules.auto_backup_scheduler import backup_cycle as protected_cycle

    return protected_cycle()


async def backup_loop():
    """Delegate the paid scheduler loop through its protected module."""
    from ..modules.auto_backup_scheduler import backup_loop as protected_loop

    return await protected_loop()


# ─── Start / stop ─────────────────────────────────────────────────────────────

def start_background_tasks() -> list:
    """
    Start monitoring and backup asyncio tasks.
    Returns list of tasks for later cancellation via stop_background_tasks().
    """
    monitor = asyncio.create_task(monitoring_loop())
    backup  = asyncio.create_task(backup_loop())
    return [monitor, backup]


async def stop_background_tasks(tasks: list) -> None:
    """Cancel and await background tasks started by start_background_tasks()."""
    for task in tasks:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
