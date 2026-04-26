"""
Alert manager with cooldown and deduplication for health monitoring events.
"""
import os
import time
from threading import Lock
from typing import Dict, Optional

from loguru import logger

from .state_store import HealthEvent

COOLDOWN_SECONDS = 900    # 15 min between repeated alerts for same target
RECOVERY_COOLDOWN = 300   # 5 min recovery alert cooldown
CRITICAL_COOLDOWN = 300   # 5 min for critical alerts


class AlertManager:
    """
    Manages outbound health alerts with per-key cooldowns to prevent
    alert fatigue from repeated transitions on the same target.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._cooldowns: Dict[str, float] = {}  # key -> last_alerted_ts

    # ------------------------------------------------------------------
    # Cooldown helpers
    # ------------------------------------------------------------------

    def _cooldown_key(self, event: HealthEvent) -> str:
        return f"{event.target_type}:{event.target_id}:{event.new_status}"

    def _is_in_cooldown(self, key: str, cooldown: int) -> bool:
        last = self._cooldowns.get(key, 0)
        return (time.time() - last) < cooldown

    def _record_sent(self, key: str) -> None:
        self._cooldowns[key] = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def maybe_alert(self, event: HealthEvent, db=None) -> None:
        """
        Evaluate a HealthEvent and send alerts if the transition is significant
        and the cooldown period for this target+status has elapsed.
        """
        # Never alert on a no-op transition
        if event.old_status == event.new_status:
            return

        should_alert = False
        cooldown = COOLDOWN_SECONDS

        # Recovery alerts: target came back from error/offline
        if event.new_status == "healthy" and event.old_status in ("error", "offline"):
            should_alert = True
            cooldown = RECOVERY_COOLDOWN

        # Critical degradation: target went to error or offline
        elif event.new_status in ("error", "offline"):
            should_alert = True
            cooldown = (
                CRITICAL_COOLDOWN if event.severity == "critical" else COOLDOWN_SECONDS
            )

        # Warning transitions: healthy → warning
        elif event.new_status == "warning" and event.old_status == "healthy":
            should_alert = True
            cooldown = COOLDOWN_SECONDS

        if not should_alert:
            return

        key = self._cooldown_key(event)
        with self._lock:
            if self._is_in_cooldown(key, cooldown):
                return
            self._record_sent(key)

        # Dispatch notifications
        if db is not None:
            self._send_admin_telegram(event, db)
            self._store_portal_notification(event, db)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_message(self, event: HealthEvent) -> str:
        icon = {
            "healthy": "✅",
            "warning": "⚠️",
            "error":   "❌",
            "offline": "🔴",
            "unknown": "❓",
        }.get(event.new_status, "•")

        recovery = event.new_status == "healthy"
        prefix = "✅ <b>Recovered</b>" if recovery else f"{icon} <b>Health Alert</b>"

        return (
            f"{prefix}\n"
            f"<b>{event.target_name}</b> [{event.target_type}]\n"
            f"{event.old_status} → <b>{event.new_status}</b>\n"
            f"{event.message}"
        )

    # ------------------------------------------------------------------
    # Delivery backends
    # ------------------------------------------------------------------

    def _send_admin_telegram(self, event: HealthEvent, db) -> None:
        try:
            from ..notifications import NotificationService
            ns = NotificationService(db)
            ns.notify_admin(self._format_message(event))
        except Exception as e:
            logger.debug(f"Health alert telegram send failed: {e}")

    def _store_portal_notification(self, event: HealthEvent, db) -> None:
        """Store as a portal admin notification in push_notifications table if it exists."""
        try:
            from ...database.models import PushNotification
            from datetime import datetime, timezone

            notif = PushNotification(
                user_id=None,
                title=f"Health: {event.target_name} → {event.new_status}",
                body=event.message,
                type="health_alert",
                created_at=datetime.now(timezone.utc),
            )
            db.add(notif)
            db.commit()
        except Exception as e:
            logger.debug(f"Health portal notification store failed: {e}")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
alert_manager = AlertManager()
