"""
Corporate VPN diagnostics — STUB.

See manager.py in this directory for the full rationale. The real
diagnostics module ships in the corporate-vpn premium plugin.
"""

from __future__ import annotations


_PREMIUM_PLUGIN_REQUIRED = (
    "Corporate VPN diagnostics are part of the 'corporate-vpn' "
    "premium plugin (Enterprise tier). Upgrade to enable."
)


def run_diagnostics(*args, **kwargs):
    raise NotImplementedError(_PREMIUM_PLUGIN_REQUIRED)
