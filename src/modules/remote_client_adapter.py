"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `multi_server` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "multi_server"
_UPGRADE_HINT = (
    "This component requires the multi_server commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


def create_remote_manager(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def get_live_peer_ip_offsets(*args, **kwargs) -> set[int]:
    return set()
