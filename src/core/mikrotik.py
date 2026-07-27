"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `mikrotik_adapter` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "mikrotik_adapter"
_UPGRADE_HINT = (
    "This component requires the mikrotik_adapter commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


from typing import Any

class MikrotikWireGuardManager:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(_UPGRADE_HINT)
