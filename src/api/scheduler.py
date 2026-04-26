"""
VPN Management Studio — Background Task Scheduler

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
from pathlib import Path

from loguru import logger

from ..database.connection import SessionLocal

MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "60"))
_MONITOR_TIMEOUT = int(os.getenv("MONITOR_TIMEOUT", str(max(10, int(MONITOR_INTERVAL * 0.9)))))
_RECONCILE_TIMEOUT = int(os.getenv("RECONCILE_TIMEOUT", "120"))
_monitor_cycle_lock = threading.Lock()
_reconcile_cycle_lock = threading.Lock()


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

        # ── Auto-renewal MUST run before check_and_expire_subscriptions ──
        try:
            import math as _math
            from ..modules.notifications import NotificationService
            from ..modules.subscription.subscription_models import ClientUser, ClientPortalSubscription, SubscriptionStatus
            from ..database.models import AuditLog, AuditAction
            ns = NotificationService(db)
            now = datetime.now(timezone.utc)
            now_naive = now.replace(tzinfo=None)

            auto_renew_subs = db.query(ClientPortalSubscription).filter(
                ClientPortalSubscription.auto_renew == True,
                ClientPortalSubscription.tier != "free",
                ClientPortalSubscription.expiry_date != None,
                ClientPortalSubscription.expiry_date <= now_naive,
            ).all()
            for sub in auto_renew_subs:
                if sub.last_renewal:
                    last = sub.last_renewal
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    if (now - last).total_seconds() < 86400:
                        continue

                if (sub.auto_renew_failures or 0) >= 3:
                    sub.auto_renew = False
                    ns.notify_user(sub.user_id,
                        f"<b>Auto-renewal disabled</b>\n\n"
                        f"After 3 failed attempts, auto-renewal has been disabled for your <b>{sub.tier}</b> subscription.\n"
                        f"Please renew manually."
                    )
                    ns.create_portal_notification(sub.user_id, "Auto-renewal disabled", "Auto-renewal disabled after 3 failures")
                    db.commit()
                    continue

                try:
                    tier_before = sub.tier
                    renewed, err = mgr.renew_subscription(sub.user_id, sub.billing_cycle_days or 30)
                    if renewed:
                        mgr.apply_subscription_limits(sub.user_id, reset_traffic=True)
                        sub.auto_renew_failures = 0
                        user = db.query(ClientUser).filter(ClientUser.id == sub.user_id).first()
                        if user:
                            ns.notify_user(sub.user_id,
                                f"<b>Subscription renewed!</b>\n\n"
                                f"Your <b>{tier_before}</b> subscription has been auto-renewed for {sub.billing_cycle_days or 30} days."
                            )
                            ns.create_portal_notification(sub.user_id, "Subscription renewed", f"Your {tier_before} plan was auto-renewed")
                            logger.info(f"Auto-renewed subscription for {user.username} ({tier_before}, {sub.billing_cycle_days or 30}d)")
                        db.add(AuditLog(
                            user_type="system",
                            action=AuditAction.SUBSCRIPTION_RENEW,
                            target_type="subscription",
                            target_id=sub.id,
                            target_name=f"auto-renew user {sub.user_id}",
                            details={"tier": tier_before, "days": sub.billing_cycle_days or 30},
                        ))
                    else:
                        sub.auto_renew_failures = (sub.auto_renew_failures or 0) + 1
                        logger.warning(f"Auto-renewal failed for user {sub.user_id}: {err}")
                except Exception as e:
                    sub.auto_renew_failures = (sub.auto_renew_failures or 0) + 1
                    logger.error(f"Auto-renewal exception for user {sub.user_id}: {e}")
            db.commit()
        except Exception as e:
            logger.error(f"Auto-renewal cycle error: {e}")

        # Expire subscriptions (after auto-renewal so successfully renewed subs are not expired)
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
                sent = sub.notification_sent_at or {}

                if days_left >= 6 and days_left <= 7 and "7day" not in sent:
                    ns.notify_user_expiry_warning(sub.user_id, "", 7, sub.tier)
                    ns.create_portal_notification(sub.user_id, "Subscription expiring soon", f"Your {sub.tier} plan expires in {days_left} days")
                    sent["7day"] = now.isoformat()
                elif days_left > 1 and days_left <= 3 and "3day" not in sent:
                    ns.notify_user_expiry_warning(sub.user_id, "", 3, sub.tier)
                    ns.create_portal_notification(sub.user_id, "Subscription expiring", f"Your {sub.tier} plan expires in {days_left} days")
                    sent["3day"] = now.isoformat()
                elif days_left == 1 and "1day" not in sent:
                    ns.notify_user_expiry_warning(sub.user_id, "", 1, sub.tier)
                    ns.create_portal_notification(sub.user_id, "Subscription expiring tomorrow", f"Your {sub.tier} plan expires tomorrow")
                    sent["1day"] = now.isoformat()

                if sent != (sub.notification_sent_at or {}):
                    sub.notification_sent_at = sent
            db.commit()

            active_subs = db.query(ClientPortalSubscription).filter(
                ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
                ClientPortalSubscription.traffic_limit_gb != None,
                ClientPortalSubscription.traffic_limit_gb > 0,
            ).all()
            for sub in active_subs:
                pct = sub.traffic_percentage_used
                sent = sub.notification_sent_at or {}
                if pct and pct >= 90 and "traffic_90" not in sent:
                    ns.notify_user_traffic_warning(sub.user_id, "", pct, sub.tier)
                    ns.create_portal_notification(sub.user_id, "Traffic limit warning", f"You've used {pct}% of your traffic limit")
                    sent["traffic_90"] = now.isoformat()
                    sub.notification_sent_at = sent
                elif pct and pct >= 80 and "traffic_80" not in sent:
                    ns.notify_user_traffic_warning(sub.user_id, "", pct, sub.tier)
                    ns.create_portal_notification(sub.user_id, "Traffic limit warning", f"You've used {pct}% of your traffic limit")
                    sent["traffic_80"] = now.isoformat()
                    sub.notification_sent_at = sent
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

        # Expire stale pending payments
        from ..modules.subscription.subscription_models import ClientPortalPayment
        stale_payments = db.query(ClientPortalPayment).filter(
            ClientPortalPayment.status == "pending",
            ClientPortalPayment.expires_at != None,
            ClientPortalPayment.expires_at <= datetime.now(timezone.utc)
        ).all()
        if stale_payments:
            for p in stale_payments:
                p.status = "expired"
            db.commit()
            logger.info(f"Monitoring: expired {len(stale_payments)} stale pending payments")

        stuck_cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
        stuck_payments = db.query(ClientPortalPayment).filter(
            ClientPortalPayment.status == "pending",
            ClientPortalPayment.created_at <= stuck_cutoff,
        ).all()
        if stuck_payments:
            ids = [p.invoice_id for p in stuck_payments]
            logger.warning(
                f"Monitoring: {len(stuck_payments)} payment(s) stuck in 'pending' for >6h — "
                f"invoice IDs: {ids}. Check provider dashboards or confirm manually in admin panel."
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


async def monitoring_loop():
    """Background loop that runs monitoring_cycle in a thread."""
    logger.info(f"Monitoring started (interval: {MONITOR_INTERVAL}s)")
    _reconcile_counter = 0
    _RECONCILE_EVERY = max(1, 300 // MONITOR_INTERVAL)
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
                    "Monitoring cycle exceeded timeout (%ss) — continuing without blocking API loop",
                    _MONITOR_TIMEOUT,
                )
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
                        "Reconciliation cycle exceeded timeout (%ss) — continuing without blocking API loop",
                        _RECONCILE_TIMEOUT,
                    )
                except Exception as _re:
                    logger.error(f"Reconciliation error: {_re}")
        except asyncio.CancelledError:
            logger.info("Monitoring stopped")
            break
        except Exception as e:
            logger.error(f"Monitoring error: {e}")


# ─── Backup ───────────────────────────────────────────────────────────────────

def _get_backup_config() -> dict:
    """Read backup config from SystemConfig DB."""
    from ..database.models import SystemConfig
    defaults = {
        "backup_enabled": "true",
        "backup_interval_hours": "24",
        "backup_hour_utc": "3",
        "backup_retention_count": "7",
        "backup_auto_cleanup": "true",
        "backup_storage_type": "local",
        "backup_path": str(Path(__file__).parent.parent.parent / "backups"),
        "backup_mount_point": "/mnt/vpnmanager-backup",
    }
    db = SessionLocal()
    try:
        rows = db.query(SystemConfig).filter(
            SystemConfig.key.in_(list(defaults.keys()))
        ).all()
        config = {r.key: r.value for r in rows}
    except Exception:
        config = {}
    finally:
        db.close()

    return {key: config.get(key, default) for key, default in defaults.items()}


def backup_cycle():
    """Single backup cycle — runs in thread, uses DB config."""
    from ..modules.backup_manager import BackupManager

    config = _get_backup_config()
    storage_type = config.get("backup_storage_type", "local")
    if storage_type == "network":
        backup_dir = config.get("backup_mount_point", "/mnt/vpnmanager-backup")
    else:
        backup_dir = config.get("backup_path", str(Path(__file__).parent.parent.parent / "backups"))

    retention = int(config.get("backup_retention_count", "7"))
    auto_cleanup = config.get("backup_auto_cleanup", "true").lower() == "true"

    db = SessionLocal()
    try:
        mgr = BackupManager(db, backup_dir=backup_dir)
        manifest = mgr.create_full_backup()
        if auto_cleanup:
            mgr.cleanup_old_backups(keep=retention)
        logger.info(f"Scheduled backup completed: {manifest.get('backup_size_mb', 0)} MB")

        try:
            from ..modules.notifications import NotificationService
            ns = NotificationService(db)
            ns.notify_admin(
                f"<b>Backup completed</b>\n"
                f"Servers: {manifest.get('server_count', 0)}\n"
                f"Clients: {manifest.get('client_count', 0)}\n"
                f"Size: {manifest.get('backup_size_mb', 0)} MB"
            )
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Scheduled backup failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        try:
            from ..modules.notifications import NotificationService
            ns = NotificationService(db)
            ns.notify_admin(f"<b>Backup FAILED</b>\n{str(e)[:200]}")
        except Exception:
            pass
    finally:
        db.close()


async def backup_loop():
    """Background loop that creates backups using DB-configured schedule."""
    logger.info("Backup scheduler started")
    last_backup_hour = None
    while True:
        try:
            await asyncio.sleep(60)

            config = _get_backup_config()
            enabled = config.get("backup_enabled", "true").lower() == "true"
            if not enabled:
                continue

            interval_hours = int(config.get("backup_interval_hours", "24"))
            backup_hour = int(config.get("backup_hour_utc", "3"))

            now = datetime.now(timezone.utc)
            current_slot = (now.date(), now.hour)

            if current_slot == last_backup_hour:
                continue

            if interval_hours <= 24:
                hours_step = interval_hours
                if now.hour % hours_step == backup_hour % hours_step:
                    last_backup_hour = current_slot
                    await asyncio.to_thread(backup_cycle)
            else:
                if now.hour == backup_hour:
                    days_interval = interval_hours // 24
                    last_date = last_backup_hour[0] if last_backup_hour else None
                    if last_date is None or (now.date() - last_date).days >= days_interval:
                        last_backup_hour = current_slot
                        await asyncio.to_thread(backup_cycle)
        except asyncio.CancelledError:
            logger.info("Backup scheduler stopped")
            break
        except Exception as e:
            logger.error(f"Backup scheduler error: {e}")


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
