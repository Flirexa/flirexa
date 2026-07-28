"""License-feature gating helpers for FastAPI routes.

Use ``require_license_feature(feature_name)`` as a dependency on routes that
should be unavailable to FREE installs (or any tier missing that feature):

    from ..middleware.license_gate import require_license_feature

    @router.post(
        "/{server_id}/install",
        dependencies=[Depends(require_license_feature("multi_server"))],
    )
    async def install_agent(...): ...

The dependency:
- Reads the global LicenseManager
- Returns silently if the feature is granted (license is valid + has flag)
- Raises 403 with an upgrade hint otherwise
- Fails closed only on programmer error; license-server downtime returns
  the gate's verdict from cache, so paid users keep working
"""

from __future__ import annotations

from fastapi import HTTPException
from loguru import logger


UPGRADE_URL = "https://flirexa.biz/#pricing"

# Customer-facing plan names.  Keep retired internal aliases (standard/pro)
# out of upgrade responses: the public checkout and current licence catalogue
# sell Starter, Business, and Enterprise.
FEATURE_MINIMUM_TIER = {
    "proxy_protocols": "starter",
    "promo_codes": "starter",
    "auto_renewal": "starter",
    "multi_server": "business",
    "mikrotik_adapter": "business",
    "telegram_client_bot": "business",
    "payments": "business",
    "traffic_rules": "business",
    # All built-in appearance controls are Enterprise-only. Keep the legacy
    # feature name mapped to Enterprise so an old caller cannot advertise
    # Business as sufficient.
    "white_label_basic": "enterprise",
    "auto_backup": "business",
    "white_label": "enterprise",
    "corporate_vpn": "enterprise",
    "manager_rbac": "enterprise",
    "app_integration": "enterprise",
}


def feature_required_detail(
    feature_name: str,
    *,
    current_plan: str | None = None,
    message: str | None = None,
    upgrade_tier: str | None = None,
) -> dict[str, str]:
    """Return the stable 403 payload consumed by both admin UIs.

    FastAPI nests this object under ``detail`` when it is raised through
    ``HTTPException``.  The global frontend interceptor accepts both that
    standard shape and the older top-level JSONResponse shape.
    """

    tier = (upgrade_tier or FEATURE_MINIMUM_TIER.get(feature_name) or "business").lower()
    plan_suffix = f" Current plan: {current_plan}." if current_plan else ""
    return {
        "message": message or (
            f"This action requires the '{feature_name}' feature."
            f"{plan_suffix} Upgrade to {tier.title()} to enable it."
        ),
        "license_feature_required": feature_name,
        "upgrade_tier": tier,
        "upgrade_url": UPGRADE_URL,
    }


def raise_feature_required(
    feature_name: str,
    *,
    current_plan: str | None = None,
    message: str | None = None,
    upgrade_tier: str | None = None,
) -> None:
    """Raise the canonical paid-feature denial response."""

    raise HTTPException(
        status_code=403,
        detail=feature_required_detail(
            feature_name,
            current_plan=current_plan,
            message=message,
            upgrade_tier=upgrade_tier,
        ),
    )


def ensure_current_license_feature(feature_name: str):
    """Return current ``LicenseInfo`` or raise the canonical 403/503.

    This synchronous helper is for mixed endpoints where only part of a
    request is commercial (for example NOWPayments settings are free while
    card-provider settings are Business).  Whole routes should normally use
    ``require_license_feature`` below.
    """

    try:
        from ...modules.license.manager import get_license_manager

        info = get_license_manager().get_license_info()
    except Exception as exc:
        logger.error("License gate could not load LicenseManager: {}", exc)
        raise HTTPException(
            status_code=503,
            detail="License verification unavailable. Please retry shortly.",
        )
    if not info.has_feature(feature_name):
        plan_type = getattr(info, "type", None)
        current_plan = getattr(plan_type, "value", None) or (
            str(plan_type) if plan_type is not None else None
        )
        raise_feature_required(feature_name, current_plan=current_plan)
    return info


def require_license_feature(feature_name: str):
    """Return a FastAPI dependency that enforces ``feature_name``.

    Args:
        feature_name: license feature flag (e.g. "multi_server", "proxy_protocols")

    Returns:
        A callable suitable for ``Depends(...)`` that raises HTTPException(403)
        when the active license is missing the feature.
    """

    async def _dependency() -> None:
        # Late import inside ``ensure_current_license_feature`` avoids circular
        # imports and keeps this dependency usable before DB initialisation.
        ensure_current_license_feature(feature_name)

    return _dependency
