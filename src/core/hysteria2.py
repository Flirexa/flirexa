"""
Hysteria2 protocol manager — STUB.

The full implementation lives in the closed-source `extra-protocols` plugin
distributed by the official Flirexa license server. This stub exists so the
public open-core repository can still import and reference the symbol
without the actual code, and so plugin discovery sees a clear failure mode
rather than a broken import on FREE installs.

If the runtime tries to actually instantiate Hysteria2Manager on a FREE
install, that means a license-feature gate failed somewhere — open an
issue. On paid installs the official installer overlays the real
implementation on top of this file.
"""

from __future__ import annotations

# Defaults preserved so admin-panel / installer scripts that read these
# constants for default values don't crash on FREE.
DEFAULT_CONFIG_PATH  = "/etc/hysteria/config.yaml"
DEFAULT_CERT_PATH    = "/etc/hysteria/server.crt"
DEFAULT_KEY_PATH     = "/etc/hysteria/server.key"
DEFAULT_SERVICE_NAME = "hysteria-server"
DEFAULT_PORT         = 8443


_PREMIUM_PLUGIN_REQUIRED = (
    "Hysteria2 support is part of the 'extra-protocols' premium plugin. "
    "It is not bundled with the open-core repository. "
    "Upgrade to a paid plan to enable it; see "
    "https://flirexa.biz/pricing or contact support@flirexa.biz."
)


class Hysteria2Manager:
    """Stub. Real implementation ships in the extra-protocols plugin."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(_PREMIUM_PLUGIN_REQUIRED)
