"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `dns_policy_advanced` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "dns_policy_advanced"
_UPGRADE_HINT = (
    "This component requires the dns_policy_advanced commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


def upsert_assignment(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def delete_assignment(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)
