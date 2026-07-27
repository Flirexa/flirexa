"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `auto_renewal` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "auto_renewal"
_UPGRADE_HINT = (
    "This component requires the auto_renewal commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


def process_auto_renewals(db, manager) -> int:
    return 0
