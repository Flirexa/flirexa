"""Operator-controlled browser experience for the customer portal.

The setting changes presentation only.  DeviceSlot, device binding, config
delivery, and the native application API remain identical in both modes.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.database.models import SystemConfig


PORTAL_MODE_KEY = "client_portal_mode"
PORTAL_MODES = frozenset({"simple", "advanced"})


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def get_client_portal_mode(db: Session) -> str:
    """Return the explicit mode or a compatibility-safe default.

    Existing operators who enabled official app integration keep the familiar
    advanced browser portal after updating.  Everyone else receives the new
    customer-friendly flow.  Once saved, the explicit value always wins.
    """
    rows = (
        db.query(SystemConfig)
        .filter(SystemConfig.key.in_((PORTAL_MODE_KEY, "app_integration_enabled")))
        .all()
    )
    values = {row.key: row.value for row in rows}
    explicit = str(values.get(PORTAL_MODE_KEY) or "").strip().lower()
    if explicit in PORTAL_MODES:
        return explicit
    return "advanced" if _truthy(values.get("app_integration_enabled")) else "simple"


def set_client_portal_mode(db: Session, mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized not in PORTAL_MODES:
        raise ValueError("Client portal mode must be simple or advanced")
    row = db.query(SystemConfig).filter(SystemConfig.key == PORTAL_MODE_KEY).first()
    if row is None:
        row = SystemConfig(
            key=PORTAL_MODE_KEY,
            value=normalized,
            value_type="string",
            description=(
                "Browser customer portal presentation. Both modes use the "
                "same DeviceSlot and native application APIs."
            ),
        )
        db.add(row)
    else:
        row.value = normalized
        row.value_type = "string"
    db.commit()
    return normalized
