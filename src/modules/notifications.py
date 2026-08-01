"""
Flirexa Notification System
Send notifications to users (Telegram) and admins (Telegram + Email)
Uses direct Telegram Bot API calls (no bot process dependency)
"""

import html
import os
import time
import httpx
from typing import Optional
from sqlalchemy.orm import Session
from loguru import logger


class NotificationService:
    """Send notifications via Telegram Bot API and Email"""

    def __init__(self, db: Session):
        self.db = db
        self._settings = None

    def _get_settings(self) -> dict:
        """Load notification settings from system_config table"""
        if self._settings:
            return self._settings
        from src.database.models import SystemConfig
        rows = self.db.query(SystemConfig).filter(
            SystemConfig.key.in_([
                "client_bot_token",
                "admin_bot_token",
                "admin_telegram_chat_id",
                "ADMIN_TELEGRAM_CHAT_ID",
                "notifications_enabled",
                "notify_admin_new_user",
                "notify_admin_new_payment",
                "notify_admin_subscription_expired",
                "notify_user_expiry_warning",
                "notify_user_traffic_warning",
                "notify_user_payment_confirmed",
            ])
        ).all()
        self._settings = {r.key: r.value for r in rows}
        return self._settings

    def _send_telegram(self, bot_token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
        """Send a Telegram message using Bot API"""
        if not bot_token or not chat_id:
            return False
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            with httpx.Client(timeout=10) as client:
                payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                }
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    return True
                # Telegram occasionally rate-limits or transiently returns 5xx.
                # One bounded retry improves delivery without making callers hang.
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    delay = 1.0
                    if resp.status_code == 429:
                        try:
                            delay = min(2.0, max(0.1, float(resp.json().get("parameters", {}).get("retry_after", 1))))
                        except (AttributeError, TypeError, ValueError):
                            pass
                    time.sleep(delay)
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        return True
                logger.warning(f"Telegram API returned {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            # httpx exception text may include the token-bearing Telegram URL.
            logger.error(
                "Failed to send Telegram notification ({})", type(e).__name__
            )
            return False

    # =========================================================================
    # ADMIN NOTIFICATIONS
    # =========================================================================

    def notify_admin(self, text: str) -> bool:
        """Send notification to admin via Telegram"""
        settings = self._get_settings()
        if settings.get("notifications_enabled") == "false":
            return False
        token = (
            os.getenv("ADMIN_BOT_TOKEN", "").strip()
            or settings.get("admin_bot_token")
            or os.getenv("CLIENT_BOT_TOKEN", "").strip()
            or settings.get("client_bot_token")
        )
        chat_id = (
            os.getenv("ADMIN_TELEGRAM_CHAT_ID", "").strip()
            or settings.get("ADMIN_TELEGRAM_CHAT_ID")
            or settings.get("admin_telegram_chat_id")
        )
        if not chat_id:
            allowed = os.getenv("ADMIN_BOT_ALLOWED_USERS", "")
            chat_id = next((part.strip() for part in allowed.split(",") if part.strip().isdigit()), "")
        if not token or not chat_id:
            return False
        return self._send_telegram(token, chat_id, text)

    def notify_admin_new_user(self, username: str, email: str):
        """Admin notification: new portal user registered"""
        settings = self._get_settings()
        if settings.get("notify_admin_new_user") == "false":
            return
        self.notify_admin(
            f"👤 <b>New user registered</b>\n"
            f"Username: {html.escape(str(username))}\n"
            f"Email: {html.escape(str(email))}"
        )

    def notify_admin_new_payment(self, username: str, amount: float, tier: str, method: str):
        """Admin notification: new payment received"""
        settings = self._get_settings()
        if settings.get("notify_admin_new_payment") == "false":
            return
        self.notify_admin(
            f"💰 <b>Payment received</b>\n"
            f"User: {html.escape(str(username))}\n"
            f"Amount: ${amount:.2f}\n"
            f"Tier: {html.escape(str(tier))}\n"
            f"Method: {html.escape(str(method))}"
        )

    def notify_admin_subscription_expired(self, username: str, tier: str):
        """Admin notification: user subscription expired"""
        settings = self._get_settings()
        if settings.get("notify_admin_subscription_expired") == "false":
            return
        self.notify_admin(
            f"⏰ <b>Subscription expired</b>\n"
            f"User: {html.escape(str(username))}\n"
            f"Tier: {html.escape(str(tier))}"
        )

    # =========================================================================
    # USER NOTIFICATIONS (via client bot token)
    # =========================================================================

    def _get_user_telegram_id(self, user_id: int) -> Optional[str]:
        """Get user's Telegram chat ID"""
        from src.modules.subscription.subscription_models import ClientUser
        user = self.db.query(ClientUser).filter(ClientUser.id == user_id).first()
        return user.telegram_id if user else None

    def _get_client_bot_token(self) -> Optional[str]:
        settings = self._get_settings()
        return os.getenv("CLIENT_BOT_TOKEN", "").strip() or settings.get("client_bot_token")

    def notify_user(self, user_id: int, text: str) -> bool:
        """Send notification to a portal user via Telegram"""
        settings = self._get_settings()
        if settings.get("notifications_enabled") == "false":
            return False
        token = self._get_client_bot_token()
        chat_id = self._get_user_telegram_id(user_id)
        if not token or not chat_id:
            return False
        return self._send_telegram(token, chat_id, text)

    def notify_user_expiry_warning(self, user_id: int, username: str, days_left: int, tier: str):
        """User notification: subscription expiring soon"""
        settings = self._get_settings()
        if settings.get("notify_user_expiry_warning") == "false":
            return
        self.notify_user(user_id,
            f"⚠️ <b>Subscription expiring</b>\n\n"
            f"Your <b>{html.escape(str(tier))}</b> subscription expires in <b>{int(days_left)} days</b>.\n"
            f"Renew now to keep your VPN access!\n\n"
            f"Use /subscribe to renew."
        )

    def notify_user_traffic_warning(self, user_id: int, username: str, percent_used: int, tier: str):
        """User notification: traffic limit approaching"""
        settings = self._get_settings()
        if settings.get("notify_user_traffic_warning") == "false":
            return
        self.notify_user(user_id,
            f"📊 <b>Traffic warning</b>\n\n"
            f"You've used <b>{int(percent_used)}%</b> of your traffic limit.\n"
            f"{'Consider upgrading your plan.' if percent_used >= 90 else 'Monitor your usage.'}\n\n"
            f"Use /traffic to check details."
        )

    def create_portal_notification(self, user_id: int, title: str, message: str):
        """Create a push notification record for portal users.

        Persists to ``push_notifications`` so the in-app inbox shows it,
        then best-effort dispatches via FCM to every registered
        installation so the user gets a system-level push too. FCM
        failure (no server key, network drop, dead tokens) is logged
        but never surfaced — the inbox row is the source of truth.
        """
        try:
            from src.database.models import PushNotification
            notification = PushNotification(
                user_id=user_id,
                title=title,
                message=message,
                notification_type="info",
            )
            self.db.add(notification)
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to create portal notification: {e}")
            return

        try:
            from src.modules.notifications_fcm import send_to_user
            send_to_user(self.db, user_id, title, message)
        except Exception as e:
            logger.debug("FCM dispatch failed for user {}: {}", user_id, e)

    def notify_user_payment_confirmed(self, user_id: int, tier: str, days: int, expiry_date: str):
        """User notification: payment confirmed, subscription active"""
        settings = self._get_settings()
        if settings.get("notify_user_payment_confirmed") == "false":
            return
        from src.modules.subscription.subscription_models import ClientUserClients

        has_device = self.db.query(ClientUserClients).filter(
            ClientUserClients.client_user_id == user_id
        ).first() is not None
        next_step = (
            "Use /config to download your VPN config."
            if has_device
            else "Use Add Device to choose a location and create your VPN config."
        )
        self.notify_user(user_id,
            f"✅ <b>Payment confirmed!</b>\n\n"
            f"Your <b>{html.escape(str(tier))}</b> subscription is now active.\n"
            f"Duration: {int(days)} days\n"
            f"Expires: {html.escape(str(expiry_date))}\n\n"
            f"{next_step}"
        )
