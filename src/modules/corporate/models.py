"""
Corporate VPN ORM models — STUB.

The actual SQLAlchemy models for `corporate_network`, `corporate_network_site`,
and `corporate_network_event` ship with the closed-source `corporate-vpn`
premium plugin. The plugin runs its own Alembic migration branch to create
the tables when activated; on FREE installs the tables simply don't exist
and no code path tries to query them (the corporate router is gated at the
license-feature level).

This stub keeps imports from elsewhere in the codebase from blowing up.
"""

from __future__ import annotations


# Sentinel placeholders. Any code that actually references these on FREE
# is a bug — the license gate should have prevented the call.
class CorporateNetwork:
    """Stub model. Real implementation in corporate-vpn plugin."""


class CorporateNetworkSite:
    """Stub model. Real implementation in corporate-vpn plugin."""


class CorporateNetworkEvent:
    """Stub model. Real implementation in corporate-vpn plugin."""
