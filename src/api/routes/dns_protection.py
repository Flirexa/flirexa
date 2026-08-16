"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `dns_protection` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "dns_protection"
_UPGRADE_HINT = (
    "This component requires the dns_protection commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


from fastapi import APIRouter

router = APIRouter()
