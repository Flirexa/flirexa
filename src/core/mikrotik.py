"""Stub for the Mikrotik RouterOS adapter.

The real implementation lives in the closed-source `flirexa-pro` package
and is overlaid into the install tree only when the customer's license
includes the `mikrotik_adapter` feature (Pro tier or higher).

Open-core (FREE / Starter) installs never reach this code path: the
server-create API blocks `agent_mode='mikrotik'` for licenses without
the entitlement before any code here would run. This file exists so
module-level imports keep working at startup.
"""

from __future__ import annotations

from typing import Any


_UPGRADE_HINT = (
    "RouterOS / Mikrotik adapter is a paid feature. "
    "Subscribe to the Pro tier or higher at https://flirexa.biz/#pricing "
    "and reinstall to activate it."
)


class _StubMikrotikManager:
    """Sentinel object — instantiation always raises with an upgrade hint."""

    def __init__(self, *_: Any, **__: Any):
        raise RuntimeError(_UPGRADE_HINT)


# Match the public symbol the real implementation exports so callers
# that `from .mikrotik import MikrotikWireGuardManager` don't ImportError
# at module load.
MikrotikWireGuardManager = _StubMikrotikManager
