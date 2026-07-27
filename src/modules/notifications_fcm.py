"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `app_integration` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "app_integration"
_UPGRADE_HINT = (
    "This component requires the app_integration commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


def send_to_user(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)
