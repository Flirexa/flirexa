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

DEFAULT_CONFIG_PATH = "/etc/hysteria/config.yaml"
DEFAULT_CERT_PATH = "/etc/hysteria/server.crt"
DEFAULT_KEY_PATH = "/etc/hysteria/server.key"
DEFAULT_SERVICE_NAME = "hysteria-server"
DEFAULT_PORT = 8443

class Hysteria2Manager:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(_UPGRADE_HINT)
