"""
Proxy protocol base manager — STUB.

The full implementation lives in the closed-source `extra-protocols` plugin
distributed by the official Flirexa license server. See hysteria2.py for the
full rationale.
"""

from __future__ import annotations

from urllib.parse import quote


def build_proxy_uri(
    scheme: str,
    user: str,
    password: str,
    host: str,
    port: int,
    params: str = "",
    label: str = "",
) -> str:
    """Build a generic proxy URI. Kept in the open core because it contains
    no protocol-specific logic — used by clients that already have credentials
    issued by a paid Hysteria2/TUIC install.
    """
    auth = f"{quote(user, safe='')}:{quote(password, safe='')}" if user else quote(password, safe="")
    base = f"{scheme}://{auth}@{host}:{port}"
    if params:
        base += f"?{params}"
    if label:
        base += f"#{quote(label, safe='')}"
    return base


_PREMIUM_PLUGIN_REQUIRED = (
    "Proxy-protocol management is part of the 'extra-protocols' premium "
    "plugin. It is not bundled with the open-core repository. "
    "Upgrade to a paid plan to enable it; see https://flirexa.biz/pricing "
    "or contact support@flirexa.biz."
)


class ProxyBaseManager:
    """Stub. Real implementation ships in the extra-protocols plugin."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(_PREMIUM_PLUGIN_REQUIRED)
