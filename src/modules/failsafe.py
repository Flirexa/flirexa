"""
VPN Management Studio — Fail-Safe Mode

When the system is in a critical state (mass WG errors or all servers
drifted), new payments are blocked and users get a clear error message
instead of creating broken/orphaned state.

Fail-safe conditions (checked at startup and every 5 min by worker):
  - All WG servers drifted (no ONLINE server with a healthy WG connection)
  - Mass WG error rate: >10 errors per component in last cycle
  - For PAID-tier installs: invalid license (FREE never triggers this)

Usage
-----
    from src.modules.failsafe import FailSafeManager, FailSafeError

    fsm = FailSafeManager.instance()
    fsm.check_payment_allowed()    # raises FailSafeError if blocked
    fsm.check_client_creation()    # raises FailSafeError if blocked

    # From worker or startup:
    fsm.refresh(db)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from loguru import logger


# ─── error type ──────────────────────────────────────────────────────────────

class FailSafeError(Exception):
    """Raised when a payment or client operation is blocked by fail-safe mode."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"System in fail-safe mode: {reason}")


# ─── state ───────────────────────────────────────────────────────────────────

@dataclass
class FailSafeState:
    active: bool = False
    reasons: List[str] = field(default_factory=list)
    activated_at: Optional[datetime] = None
    last_check: Optional[datetime] = None

    def add_reason(self, reason: str):
        if reason not in self.reasons:
            self.reasons.append(reason)

    def clear(self):
        self.active = False
        self.reasons.clear()
        self.activated_at = None


# ─── manager ─────────────────────────────────────────────────────────────────

class FailSafeManager:
    """
    Singleton. Tracks whether the system should block new payments/enrollments.
    Thread-safe via a simple lock.
    """

    _instance: Optional["FailSafeManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._state = FailSafeState()
        self._error_counts: dict = {}  # component → recent error count
        self._state_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "FailSafeManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── public checks ─────────────────────────────────────────────────────────

    def is_active(self) -> bool:
        with self._state_lock:
            return self._state.active

    def get_state(self) -> FailSafeState:
        with self._state_lock:
            return FailSafeState(
                active=self._state.active,
                reasons=list(self._state.reasons),
                activated_at=self._state.activated_at,
                last_check=self._state.last_check,
            )

    def check_payment_allowed(self):
        """Raise FailSafeError if new payments should be blocked."""
        with self._state_lock:
            if self._state.active:
                reasons = "; ".join(self._state.reasons[:3])
                raise FailSafeError(
                    f"New payments are temporarily blocked: {reasons}. "
                    "Please try again later or contact support."
                )

    def check_client_creation(self):
        """Raise FailSafeError if new client creation should be blocked."""
        with self._state_lock:
            if self._state.active:
                reasons = "; ".join(self._state.reasons[:3])
                raise FailSafeError(
                    f"New client creation is temporarily blocked: {reasons}. "
                    "Please try again later."
                )

    # ── refresh from worker / startup ─────────────────────────────────────────

    def refresh(self, db=None):
        """
        Re-evaluate fail-safe conditions and update state.
        Safe to call periodically (every 5 min from worker).
        """
        now = datetime.now(timezone.utc)
        new_state = FailSafeState()
        new_state.last_check = now

        # ── Condition 1: License invalid (paid tiers only) ───────────────────
        # FREE tier never triggers this — open-core mode is always "valid".
        # Only block payments if a paid license exists and is in an invalid
        # state (e.g. signature mismatch, hardware mismatch).
        try:
            from .license.manager import get_license_manager
            lm = get_license_manager()
            if not lm.is_free():
                info = lm.get_license_info()
                if not info.is_valid or info.is_expired():
                    new_state.add_reason(f"license_invalid: {info.validation_message}")
        except Exception as exc:
            logger.debug("failsafe: license check failed: %s", exc)

        # ── Condition 2: All WG servers drifted / unreachable ─────────────────
        try:
            if db is not None:
                from ..database.models import Server
                online_servers = db.query(Server).filter(
                    Server.lifecycle_status == "online"
                ).all()
                if online_servers:
                    all_drifted = all(getattr(s, "drift_detected", False) for s in online_servers)
                    if all_drifted:
                        new_state.add_reason(
                            f"all_{len(online_servers)}_wg_servers_drifted"
                        )
        except Exception as exc:
            logger.debug("failsafe: server check failed: %s", exc)

        # ── Condition 3: Mass WG errors (tracked via record_error) ───────────
        with self._state_lock:
            for component, count in self._error_counts.items():
                if count > 10:  # >10 errors since last reset
                    new_state.add_reason(f"mass_errors:{component}:{count}")

        # ── Apply new state ───────────────────────────────────────────────────
        state_changed = False
        with self._state_lock:
            was_active = self._state.active
            if new_state.reasons:
                new_state.active = True
                if not new_state.activated_at:
                    new_state.activated_at = (
                        self._state.activated_at if was_active else now
                    )
                if not was_active:
                    logger.critical(
                        "[FAILSAFE] ACTIVATED — reasons: %s",
                        ", ".join(new_state.reasons),
                    )
                    state_changed = True
                else:
                    logger.warning(
                        "[FAILSAFE] still active — reasons: %s",
                        ", ".join(new_state.reasons),
                    )
            else:
                if was_active:
                    logger.info("[FAILSAFE] Deactivated — system healthy")
                    state_changed = True
            self._state = new_state
            # Reset error counters after each refresh cycle
            self._error_counts.clear()

        # Persist to DB on state change so restarts restore correct state
        if state_changed and db is not None:
            self._persist_state(db)

        return new_state

    def record_error(self, component: str):
        """
        Record a WG/proxy operation error. If count exceeds threshold,
        next refresh() will activate fail-safe.
        """
        with self._state_lock:
            self._error_counts[component] = self._error_counts.get(component, 0) + 1

    def force_activate(self, reason: str, db=None):
        """Manually activate fail-safe (e.g. from admin panel)."""
        with self._state_lock:
            self._state.active = True
            self._state.add_reason(f"manual: {reason}")
            self._state.activated_at = datetime.now(timezone.utc)
            logger.critical("[FAILSAFE] Manually activated: %s", reason)
        if db is not None:
            self._persist_state(db)

    def force_deactivate(self, db=None):
        """Manually deactivate fail-safe (e.g. from admin panel)."""
        with self._state_lock:
            self._state.clear()
            logger.info("[FAILSAFE] Manually deactivated")
        if db is not None:
            self._persist_state(db)

    # ── DB persistence ────────────────────────────────────────────────────────

    def _persist_state(self, db):
        """Persist fail-safe state to SystemConfig so it survives API restarts."""
        try:
            import json as _json
            from ..database.models import SystemConfig

            def _upsert(key: str, value: str):
                row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
                if row:
                    row.value = value
                else:
                    db.add(SystemConfig(key=key, value=value, value_type="string",
                                       description="failsafe persistence"))

            with self._state_lock:
                active = self._state.active
                reasons = list(self._state.reasons)
                activated_at = self._state.activated_at

            _upsert("failsafe_active", "true" if active else "false")
            _upsert("failsafe_reasons", _json.dumps(reasons))
            _upsert("failsafe_activated_at",
                    activated_at.isoformat() if activated_at else "")
            db.commit()
        except Exception as exc:
            logger.debug("[FAILSAFE] persist_state failed: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass

    def load_persisted_state(self, db):
        """
        Load fail-safe state from SystemConfig at API startup.
        Restores active state that was saved before a restart.
        """
        try:
            import json as _json
            from ..database.models import SystemConfig

            def _get(key: str):
                row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
                return row.value if row else None

            active_raw = _get("failsafe_active")
            reasons_raw = _get("failsafe_reasons")
            activated_at_raw = _get("failsafe_activated_at")

            active = active_raw == "true"
            reasons = _json.loads(reasons_raw) if reasons_raw else []
            activated_at = None
            if activated_at_raw:
                try:
                    activated_at = datetime.fromisoformat(activated_at_raw)
                    if activated_at.tzinfo is None:
                        activated_at = activated_at.replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            with self._state_lock:
                if active and reasons:
                    self._state.active = True
                    self._state.reasons = reasons
                    self._state.activated_at = activated_at or datetime.now(timezone.utc)
                    logger.warning("[FAILSAFE] Restored persisted state on startup: %s", reasons)
                else:
                    logger.debug("[FAILSAFE] No persisted fail-safe state to restore")
        except Exception as exc:
            logger.debug("[FAILSAFE] load_persisted_state failed: %s", exc)
