"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `manager_rbac` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "manager_rbac"
_UPGRADE_HINT = (
    "This component requires the manager_rbac commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


from fastapi import APIRouter

router = APIRouter()
