"""
Corporate VPN manager — STUB.

The full implementation lives in the closed-source `corporate-vpn` plugin
distributed by the official Flirexa license server. This stub satisfies
imports in the open-core repository so the rest of the codebase remains
testable; instantiation always fails on FREE installs because the
license-feature gate (`corporate_vpn`) refuses the request before this
class is reached.
"""

from __future__ import annotations


_PREMIUM_PLUGIN_REQUIRED = (
    "Corporate VPN (site-to-site mesh) is part of the 'corporate-vpn' "
    "premium plugin (Enterprise tier). It is not bundled with the "
    "open-core repository. See https://flirexa.biz/pricing or contact "
    "support@flirexa.biz."
)


class CorporateManager:
    """Stub. Real implementation ships in the corporate-vpn plugin."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(_PREMIUM_PLUGIN_REQUIRED)
