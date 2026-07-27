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

DEFAULT_CONFIG_PATH = "/etc/xray/config.json"
DEFAULT_SERVICE_NAME = "xray-reality"
DEFAULT_PORT = 443
DEFAULT_DEST = "www.microsoft.com"
DEFAULT_FLOW = "xtls-rprx-vision"

def generate_reality_keys():
    raise RuntimeError(_UPGRADE_HINT)

class VlessRealityManager:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(_UPGRADE_HINT)
