"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `proxy_protocols` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "proxy_protocols"
_UPGRADE_HINT = (
    "This component requires the proxy_protocols commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


from typing import Any

def split_endpoint_host(endpoint: str) -> str:
    raise RuntimeError(_UPGRADE_HINT)

def build_proxy_uri(*args: Any, **kwargs: Any) -> str:
    raise RuntimeError(_UPGRADE_HINT)

class ProxyBaseManager:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(_UPGRADE_HINT)
