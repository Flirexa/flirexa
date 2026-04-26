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


def require_license_feature(feature_name: str):
    """Return a FastAPI dependency that enforces ``feature_name``.

    Args:
        feature_name: license feature flag (e.g. "multi_server", "proxy_protocols")

    Returns:
        A callable suitable for ``Depends(...)`` that raises HTTPException(403)
        when the active license is missing the feature.
    """

    async def _dependency() -> None:
        try:
            # Late import: avoids circular import at module load time and
            # keeps this helper usable without DB initialisation.
            from ...modules.license.manager import get_license_manager
            mgr = get_license_manager()
            info = mgr.get_license_info()
        except Exception as exc:
            # If license verification machinery is itself broken, fail closed
            # for paid features — better safe than letting FREE bypass via crash.
            logger.error("License gate could not load LicenseManager: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="License verification unavailable. Please retry shortly.",
            )

        if not info.has_feature(feature_name):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"This action requires the '{feature_name}' feature. "
                    f"Current plan: {info.type.value}. Upgrade to enable it."
                ),
            )

    return _dependency
