"""
TUIC protocol manager — STUB.

The full implementation lives in the closed-source `extra-protocols` plugin
distributed by the official Flirexa license server. See the docstring in
hysteria2.py in this same directory for the full rationale.
"""

from __future__ import annotations

DEFAULT_CONFIG_PATH  = "/etc/tuic/config.json"
DEFAULT_CERT_PATH    = "/etc/tuic/server.crt"
DEFAULT_KEY_PATH     = "/etc/tuic/server.key"
DEFAULT_SERVICE_NAME = "tuic-server"
DEFAULT_PORT         = 8443


_PREMIUM_PLUGIN_REQUIRED = (
    "TUIC support is part of the 'extra-protocols' premium plugin. "
    "It is not bundled with the open-core repository. "
    "Upgrade to a paid plan to enable it; see "
    "https://flirexa.biz/pricing or contact support@flirexa.biz."
)


class TUICManager:
    """Stub. Real implementation ships in the extra-protocols plugin."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(_PREMIUM_PLUGIN_REQUIRED)
