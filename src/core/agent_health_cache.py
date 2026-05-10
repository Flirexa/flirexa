"""In-memory cache of last-successful agent /health and /stats responses.

Why this exists
---------------
Self-hosted operators routinely run their main WG box on a home connection
with port-forwarding. Home internet is bursty: 5-30 second blips from DHCP
renewal, NAT-table eviction, the router rebooting itself, ISP route flaps.
During each blip the panel's HTTP poll to the agent fails and the UI used
to flip the server to "unreachable", panicking customers who saw their
server "disappear".

This module keeps the last successful poll in process memory, keyed by
agent host:port. When the next poll fails, callers can retrieve the cached
value and surface it to the UI tagged ``is_stale=True`` instead of showing
zero peers / offline. The cache evaporates on API restart — we don't try
to persist it; a 30-minute window covers ~all transient connectivity blips
we've actually seen, and longer than that the UI deserves to show
"unreachable" for real.

The cache is read-through only: callers explicitly call ``record_*`` after
a successful HTTP call and ``get_cached_*`` on a failure. There is no
implicit decoration of HTTP calls — keeping it boring and easy to audit.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse


# 30 minutes. Longer than any real network blip; shorter than the next
# "is the box still alive?" question an operator would reasonably ask.
DEFAULT_MAX_AGE_SEC = 30 * 60


@dataclass
class _Entry:
    data: Any
    recorded_at: float  # time.monotonic()
    wall_time: float    # time.time() — for display only


# kind in {"health", "stats"} — keep them in separate buckets so a stale
# /stats doesn't accidentally satisfy a /health probe.
_cache: Dict[Tuple[str, str], _Entry] = {}


def _key(agent_url: str) -> str:
    p = urlparse(agent_url)
    return f"{p.hostname}:{p.port}" if p.hostname else agent_url


def record_health(agent_url: str, data: Any) -> None:
    if not agent_url:
        return
    _cache[(_key(agent_url), "health")] = _Entry(
        data=data, recorded_at=time.monotonic(), wall_time=time.time(),
    )


def record_stats(agent_url: str, data: Any) -> None:
    if not agent_url:
        return
    _cache[(_key(agent_url), "stats")] = _Entry(
        data=data, recorded_at=time.monotonic(), wall_time=time.time(),
    )


def _get(
    agent_url: str,
    kind: str,
    max_age_sec: int = DEFAULT_MAX_AGE_SEC,
) -> Optional[Tuple[Any, int]]:
    """Return (data, age_seconds) if the cached entry is still fresh enough,
    else None. ``age_seconds`` is monotonic and integer-rounded — callers
    pass it straight to the UI."""
    if not agent_url:
        return None
    entry = _cache.get((_key(agent_url), kind))
    if entry is None:
        return None
    age = time.monotonic() - entry.recorded_at
    if age > max_age_sec:
        return None
    return entry.data, int(age)


def get_cached_health(
    agent_url: str, max_age_sec: int = DEFAULT_MAX_AGE_SEC,
) -> Optional[Tuple[Any, int]]:
    return _get(agent_url, "health", max_age_sec)


def get_cached_stats(
    agent_url: str, max_age_sec: int = DEFAULT_MAX_AGE_SEC,
) -> Optional[Tuple[Any, int]]:
    return _get(agent_url, "stats", max_age_sec)


def forget(agent_url: str) -> None:
    """Drop both buckets for an agent. Called when an agent is deleted or
    its URL changes — old cached data shouldn't survive a re-host."""
    if not agent_url:
        return
    k = _key(agent_url)
    _cache.pop((k, "health"), None)
    _cache.pop((k, "stats"), None)
