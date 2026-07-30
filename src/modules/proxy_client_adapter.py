"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `proxy_protocols` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "proxy_protocols"
_UPGRADE_HINT = (
    "This component requires the proxy_protocols commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


def create_proxy_client(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def apply_proxy_config(*args, **kwargs) -> bool:
    return False

def get_proxy_client_config_dict(*args, **kwargs):
    return None
