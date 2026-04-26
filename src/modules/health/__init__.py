"""
Centralized system health monitoring module.
"""
from .checker import HealthStatus, ComponentHealth, SystemHealth, SystemHealthChecker
from .server_checker import ServerHealth, ServerHealthChecker
from .cache import health_cache
from .state_store import health_state_store, HealthEvent, TargetState, StateStore
from .alerting import alert_manager, AlertManager
from .status import (
    COMPONENT_CRITICALITY,
    STATUS_PRIORITY,
    aggregate_status,
    is_degraded,
    is_severe,
)

__all__ = [
    "HealthStatus",
    "ComponentHealth",
    "SystemHealth",
    "SystemHealthChecker",
    "ServerHealth",
    "ServerHealthChecker",
    "health_cache",
    "health_state_store",
    "HealthEvent",
    "TargetState",
    "StateStore",
    "alert_manager",
    "AlertManager",
    "COMPONENT_CRITICALITY",
    "STATUS_PRIORITY",
    "aggregate_status",
    "is_degraded",
    "is_severe",
]
