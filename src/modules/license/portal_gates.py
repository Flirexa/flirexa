"""Per-operator client-portal feature gates.

Cosmetic/behaviour toggles an operator can be opted OUT of, carried as
"deny" flags in their license (`portal_no_*`). Default = everything ON, so an
operator without any flag behaves exactly as before (backward compatible).

The flags gate BOTH the portal UI (the SPA reads `/features`) AND the backend
endpoint (the route returns 403) — hiding the button alone is not enough, a
client could hit the API directly.

Reads the OPERATOR's panel-wide license (`get_license_manager`), so a gate
applies to that operator's whole portal. Add a new gate by adding a
`portal_no_<thing>` key here + a `v-if` in the SPA + a 403 in the endpoint.

Design: docs/superpowers/specs/2026-06-16-per-operator-portal-gates-design.md
"""
from __future__ import annotations

from typing import Optional

# flag in the license  →  capability key returned to the SPA / checked by routes
_DENY_FLAGS = {
    "portal_no_config_download": "config_download",
    "portal_no_qr": "qr",
}


def portal_gates(license_info: Optional[object] = None) -> dict:
    """Return {capability: bool} for the current operator. True = available."""
    if license_info is None:
        try:
            from .manager import get_license_manager
            license_info = get_license_manager().get_license_info()
        except Exception:
            # Fail OPEN: a license read hiccup must never silently disable a
            # customer-facing capability for everyone.
            return {cap: True for cap in _DENY_FLAGS.values()}

    def _has(flag: str) -> bool:
        try:
            return bool(license_info.has_feature(flag))
        except Exception:
            return False

    return {cap: (not _has(flag)) for flag, cap in _DENY_FLAGS.items()}


def is_gated(capability: str) -> bool:
    """True when `capability` is DISABLED for the current operator (→ 403)."""
    return not portal_gates().get(capability, True)
