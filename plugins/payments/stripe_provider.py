"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `payments` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "payments"
_UPGRADE_HINT = (
    "This component requires the payments commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


class StripeProvider:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(_UPGRADE_HINT)

PROVIDER_CLASS = StripeProvider
