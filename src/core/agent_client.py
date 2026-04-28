"""Stub for the multi-server agent HTTP client.

The real implementation lives in the closed-source `flirexa-pro` package
(`multi-server/src/core/agent_client.py`) and is overlaid by `install.sh`
on hosts whose subscription includes the `multi_server` license feature.

Open-core (FREE / Starter) installs never reach this code path: those tiers
cap at one server (`max_servers = 1`), and the API blocks creating a second
server before any code here would run. This file exists so module-level
imports keep working.
"""

from __future__ import annotations

from typing import Any


_UPGRADE_HINT = (
    "Multi-server orchestration is a paid feature. "
    "Subscribe to the Business tier or higher at https://flirexa.biz/#pricing "
    "and reinstall to activate the multi-server agent."
)


class _StubAgentClient:
    """Sentinel object — instantiation always raises with an upgrade hint."""

    def __init__(self, *_: Any, **__: Any):
        raise RuntimeError(_UPGRADE_HINT)


# Match the public symbol the real implementation exports.
AgentClient = _StubAgentClient
