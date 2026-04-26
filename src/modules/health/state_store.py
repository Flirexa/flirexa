"""
In-memory thread-safe state store for health monitoring events and target states.
"""
from threading import Lock
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timezone
import time

from .status import HEALTHY, WARNING, ERROR, OFFLINE, UNKNOWN, is_degraded, is_severe

# ---------------------------------------------------------------------------
# Anti-flap configuration
# (target_type, is_critical, direction): consecutive_checks_needed
# direction: "degrade" (good→bad/warn), "recover" (bad→good)
# ---------------------------------------------------------------------------
ANTI_FLAP: Dict[Tuple[str, bool, str], int] = {
    ("component", True,  "degrade"): 2,
    ("component", True,  "recover"): 1,
    ("component", False, "degrade"): 2,
    ("component", False, "recover"): 1,
    ("server",    True,  "degrade"): 2,
    ("server",    True,  "recover"): 2,
    ("server",    False, "degrade"): 2,
    ("server",    False, "recover"): 2,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HealthEvent:
    id: int
    timestamp: str
    target_type: str    # "component" | "server"
    target_id: str      # component name or str(server_id)
    target_name: str
    old_status: str
    new_status: str
    severity: str       # "info" | "warning" | "critical"
    event_code: str     # e.g. "status_change", "server_offline", "resource_threshold"
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class TargetState:
    target_type: str
    target_id: str
    target_name: str
    current_status: str = UNKNOWN
    previous_status: Optional[str] = None
    last_status_change: Optional[str] = None
    last_healthy: Optional[str] = None
    last_error: Optional[str] = None
    last_checked: Optional[str] = None
    consecutive_same: int = 0           # consecutive checks with same outcome direction
    pending_status: Optional[str] = None  # status waiting for confirmation
    pending_count: int = 0


# ---------------------------------------------------------------------------
# StateStore
# ---------------------------------------------------------------------------

class StateStore:
    """
    Singleton-style in-memory store for health events and component/server states.
    All public methods are thread-safe.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._events: deque = deque(maxlen=1000)
        self._component_states: Dict[str, TargetState] = {}
        self._server_states: Dict[str, TargetState] = {}
        self._event_counter: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now() -> str:
        """Return current UTC time as ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()

    def _compute_severity(self, old_status: str, new_status: str) -> str:
        """
        Compute event severity based on the status transition.
        - info: recovering (going to healthy) or any unknown transition
        - warning: new_status is warning
        - critical: new_status is error or offline
        """
        if new_status == HEALTHY:
            return "info"
        if new_status == WARNING:
            return "warning"
        if new_status in (ERROR, OFFLINE):
            return "critical"
        return "info"

    def _make_event(
        self,
        target_state: TargetState,
        old: str,
        new: str,
        event_code: str,
        message: str,
        details: dict = None,
    ) -> HealthEvent:
        """Create a new HealthEvent and append it to the event deque."""
        if details is None:
            details = {}

        self._event_counter += 1
        event = HealthEvent(
            id=self._event_counter,
            timestamp=self._now(),
            target_type=target_state.target_type,
            target_id=target_state.target_id,
            target_name=target_state.target_name,
            old_status=old,
            new_status=new,
            severity=self._compute_severity(old, new),
            event_code=event_code,
            message=message,
            details=details,
        )
        self._events.append(event)
        return event

    def _get_direction(self, current_status: str, new_raw_status: str) -> str:
        """
        Determine flap direction:
        - "degrade" if moving from good/unknown toward worse
        - "recover" if moving from bad toward healthy
        """
        if is_degraded(current_status) and not is_degraded(new_raw_status):
            return "recover"
        return "degrade"

    def _should_confirm(
        self,
        state: TargetState,
        new_raw_status: str,
        is_critical: bool,
    ) -> bool:
        """
        Apply anti-flapping logic to decide whether a raw check result should
        actually change the confirmed (current) state.

        Returns True if the status change should be committed, False otherwise.
        """
        # Determine threshold based on direction
        direction = self._get_direction(state.current_status, new_raw_status)
        threshold = ANTI_FLAP.get(
            (state.target_type, is_critical, direction),
            2,  # safe default
        )

        if new_raw_status == state.pending_status:
            # Continuing to see the same pending status
            state.pending_count += 1
            if state.pending_count >= threshold:
                return True
            return False
        else:
            # New raw status differs from what we were tracking
            state.pending_status = new_raw_status
            state.pending_count = 1
            if threshold == 1:
                return True
            return False

    def _get_or_create_state(
        self,
        target_type: str,
        target_id: str,
        target_name: str,
    ) -> TargetState:
        """Retrieve existing state or create a new one. Caller must hold the lock."""
        store = (
            self._component_states
            if target_type == "component"
            else self._server_states
        )
        if target_id not in store:
            store[target_id] = TargetState(
                target_type=target_type,
                target_id=target_id,
                target_name=target_name,
            )
        else:
            # Keep name up-to-date in case it changed
            store[target_id].target_name = target_name
        return store[target_id]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_check(
        self,
        target_type: str,
        target_id: str,
        target_name: str,
        raw_status: str,
        is_critical: bool = False,
        event_code: str = "status_check",
        message: str = "",
        details: dict = None,
    ) -> Optional[HealthEvent]:
        """
        Record a raw health check result, apply anti-flapping, and emit an
        event if the confirmed state changes.

        Returns the HealthEvent if a state transition occurred, else None.
        """
        if details is None:
            details = {}

        with self._lock:
            state = self._get_or_create_state(target_type, target_id, target_name)
            now = self._now()
            state.last_checked = now

            confirmed = self._should_confirm(state, raw_status, is_critical)

            if not confirmed:
                return None

            confirmed_status = raw_status

            if confirmed_status == state.current_status:
                # No transition even after confirmation
                return None

            # --- State transition ---
            old_status = state.current_status
            state.previous_status = old_status
            state.current_status = confirmed_status
            state.last_status_change = now
            state.consecutive_same = 1

            # Reset pending after confirmed transition
            state.pending_status = None
            state.pending_count = 0

            if confirmed_status == HEALTHY:
                state.last_healthy = now
            if is_severe(confirmed_status):
                state.last_error = now

            event = self._make_event(
                state,
                old=old_status,
                new=confirmed_status,
                event_code=event_code,
                message=message,
                details=details,
            )
            return event

    def get_events(
        self,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[HealthEvent]:
        """Return recent events, optionally filtered."""
        with self._lock:
            events = list(self._events)

        # Apply filters (most recent first)
        events.reverse()

        if target_type is not None:
            events = [e for e in events if e.target_type == target_type]
        if target_id is not None:
            events = [e for e in events if e.target_id == target_id]
        if severity is not None:
            events = [e for e in events if e.severity == severity]

        return events[:limit]

    def get_component_state(self, name: str) -> Optional[TargetState]:
        """Return the current state for a named component."""
        with self._lock:
            return self._component_states.get(name)

    def get_server_state(self, server_id: int) -> Optional[TargetState]:
        """Return the current state for a server by integer ID."""
        with self._lock:
            return self._server_states.get(str(server_id))

    def get_all_component_states(self) -> Dict[str, TargetState]:
        """Return a shallow copy of all component states."""
        with self._lock:
            return dict(self._component_states)

    def get_all_server_states(self) -> Dict[str, TargetState]:
        """Return a shallow copy of all server states (keyed by str(server_id))."""
        with self._lock:
            return dict(self._server_states)

    def get_active_issues(self) -> List[dict]:
        """
        Return a list of dicts describing components and servers whose
        current_status is degraded (warning, error, or offline), including
        how long they have been in that state.
        """
        now_ts = time.time()
        issues: List[dict] = []

        with self._lock:
            all_states = list(self._component_states.values()) + list(
                self._server_states.values()
            )

        for state in all_states:
            if not is_degraded(state.current_status):
                continue

            duration_seconds: Optional[float] = None
            if state.last_status_change:
                try:
                    change_dt = datetime.fromisoformat(state.last_status_change)
                    duration_seconds = int(now_ts - change_dt.timestamp())
                except (ValueError, TypeError):
                    duration_seconds = None

            issues.append(
                {
                    "target_type": state.target_type,
                    "target_id": state.target_id,
                    "target_name": state.target_name,
                    "current_status": state.current_status,
                    "previous_status": state.previous_status,
                    "last_status_change": state.last_status_change,
                    "duration_seconds": duration_seconds,
                    "last_error": state.last_error,
                }
            )

        return issues

    def get_recent_recoveries(self, since_seconds: int = 3600) -> List[HealthEvent]:
        """
        Return HealthEvents where new_status == HEALTHY that occurred within
        the last `since_seconds` seconds.
        """
        cutoff = time.time() - since_seconds
        recoveries: List[HealthEvent] = []

        with self._lock:
            events = list(self._events)

        for event in reversed(events):
            if event.new_status != HEALTHY:
                continue
            try:
                event_ts = datetime.fromisoformat(event.timestamp).timestamp()
            except (ValueError, TypeError):
                continue
            if event_ts >= cutoff:
                recoveries.append(event)

        return recoveries


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
health_state_store = StateStore()
