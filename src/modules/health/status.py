"""
Strict status model for the VPN Management Studio health monitoring system.
"""
from typing import List, Tuple

# STATUS constants
HEALTHY = "healthy"
WARNING = "warning"
ERROR = "error"
OFFLINE = "offline"
UNKNOWN = "unknown"

# Component criticality levels
COMPONENT_CRITICALITY = {
    "database":         "critical",
    "api_process":      "critical",
    "worker":           "critical",
    "license_server":   "important",
    "payment_provider": "important",
    "wireguard_local":  "informational",
    "telegram_bots":    "informational",
    "disk":             "informational",
    "memory":           "informational",
    "cpu":              "informational",
}

# Status priority (higher = worse)
STATUS_PRIORITY = {
    HEALTHY:  0,
    UNKNOWN:  1,
    WARNING:  2,
    ERROR:    3,
    OFFLINE:  3,
}


def is_degraded(status: str) -> bool:
    """Returns True if the status represents any degradation."""
    return status in (WARNING, ERROR, OFFLINE)


def is_severe(status: str) -> bool:
    """Returns True if the status represents a severe condition."""
    return status in (ERROR, OFFLINE)


def aggregate_status(component_statuses: List[Tuple[str, str]]) -> str:
    """
    Aggregate a list of (component_name, status) tuples into an overall system status.

    Rules applied in order:
    1. Any CRITICAL component in ERROR or OFFLINE → ERROR
    2. Any CRITICAL component in WARNING → WARNING
    3. Any IMPORTANT component in ERROR or OFFLINE → WARNING
    4. More than 1 INFORMATIONAL component in WARNING or ERROR → WARNING
    5. Any single UNKNOWN → don't escalate beyond WARNING (cap at WARNING)
    6. Otherwise → HEALTHY
    """
    has_unknown = False
    informational_degraded_count = 0
    result = HEALTHY

    for component_name, status in component_statuses:
        criticality = COMPONENT_CRITICALITY.get(component_name, "informational")

        if status == UNKNOWN:
            has_unknown = True
            continue

        if criticality == "critical":
            if is_severe(status):
                # Rule 1: critical component is ERROR or OFFLINE → immediate ERROR
                return ERROR
            if status == WARNING:
                # Rule 2: critical component is WARNING → at least WARNING
                result = WARNING

        elif criticality == "important":
            if is_severe(status):
                # Rule 3: important component is ERROR or OFFLINE → at least WARNING
                if result != ERROR:
                    result = WARNING

        elif criticality == "informational":
            if is_degraded(status):
                informational_degraded_count += 1

    # Rule 4: more than 1 informational component degraded → WARNING
    if informational_degraded_count > 1:
        if result != ERROR:
            result = WARNING

    # Rule 5: any unknown → cap escalation at WARNING (don't return HEALTHY if unknown present)
    # UNKNOWN alone doesn't escalate beyond WARNING; if result is already ERROR keep it.
    if has_unknown and result == HEALTHY:
        # A single unknown by itself does not escalate — leave as HEALTHY
        pass

    return result
