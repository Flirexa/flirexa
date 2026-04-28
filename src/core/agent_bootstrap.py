"""Stub for the multi-server agent SSH bootstrapper.

The real implementation (which SSHes into a remote VPN node, installs
`agent.py`, sets up the systemd unit, and registers the agent with the
master) lives in the closed-source `flirexa-pro` package
(`multi-server/src/core/agent_bootstrap.py`).

Open-core (FREE / Starter) installs cap at one server, so the bootstrap
flow is never invoked there. This file exists so the module imports
cleanly.
"""

from __future__ import annotations

from typing import Any


_UPGRADE_HINT = (
    "Multi-server orchestration is a paid feature. "
    "Subscribe to the Business tier or higher at https://flirexa.biz/#pricing "
    "and reinstall to activate the agent installer."
)


class _StubAgentBootstrap:
    def __init__(self, *_: Any, **__: Any):
        raise RuntimeError(_UPGRADE_HINT)


AgentBootstrap = _StubAgentBootstrap
