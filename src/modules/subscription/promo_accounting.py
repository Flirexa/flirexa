"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `promo_codes` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "promo_codes"
_UPGRADE_HINT = (
    "This component requires the promo_codes commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


def record_redemption(db, payment, invoice_id: str) -> None:
    return None
