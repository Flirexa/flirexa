"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `payments` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "payments"
_UPGRADE_HINT = (
    "This component requires the payments commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


class BalanceError(ValueError):
    pass

def usd_to_minor(value) -> int:
    raise RuntimeError(_UPGRADE_HINT)

def get_balance_snapshot(*args, **kwargs) -> dict:
    raise RuntimeError(_UPGRADE_HINT)

def settle_topup(*args, **kwargs) -> bool:
    raise RuntimeError(_UPGRADE_HINT)

def purchase_subscription(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def adjust_balance(*args, **kwargs) -> dict:
    raise RuntimeError(_UPGRADE_HINT)
