"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `traffic_rules` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "traffic_rules"
_UPGRADE_HINT = (
    "This component requires the traffic_rules commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


from fastapi import APIRouter

router = APIRouter()
