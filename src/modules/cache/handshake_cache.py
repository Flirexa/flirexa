"""Peer snapshot cache + background refresher.

Why this exists
---------------
Three hot endpoints used to do the same expensive thing on every request:
``/clients`` (handshake column), ``/clients/map-data`` (peer endpoint IPs
+ handshake for the world map), and ``/servers/{id}/bandwidth`` (per-peer
rx/tx counters for the rate dashboard). Each one polled every customer-
visible server's WireGuard interface — over SSH / Mikrotik REST / local
``wg show`` — **sequentially**, ~200-500ms per server. With 5 servers
that's 1.5-2.5 s blocked on network I/O per request; with 100 servers
(real-world target) it would be 20-50 s and the panel would brown out.

This module replaces that with a single shared **peer-snapshot cache**:

1.  In-memory ``{server_id: {pubkey: PeerSnapshot}}`` map. Reads are
    free — dict access under a short-lived lock. Each snapshot carries
    everything we actually need on the request path: live handshake
    time, peer endpoint IP, and cumulative rx/tx counters.
2.  A background asyncio task that refreshes every active server
    **in parallel** every ``REFRESH_INTERVAL_SECONDS`` (default 8s).
    Each per-server fetch is hard-capped at ``PER_SERVER_TIMEOUT_SECONDS``
    so one unreachable agent can't stall the refresh round for the others.
3.  Per-server lazy fallback: if the cache has never been populated for
    a particular server (panel just started, or this server was added
    between refresh ticks), the calling code does a one-off blocking
    fetch and seeds the cache — same cost as before, but only once.

Worst-case data staleness is the refresh interval. 8 seconds of
staleness on "is this peer online" or "what's their rate" is invisible
to a human reading the panel; explicit user actions (enable/disable
client) call :py:func:`invalidate_server` to force a fresh poll on
next read so the UI flips immediately.

Sizing
------
Target: 100 servers × ~1000 peers/server = 100k snapshots.
Each ``PeerSnapshot`` is roughly 200 bytes (pubkey + endpoint + 2 ints
+ datetime) → ~20 MB resident. Refresh round at that scale completes
in ~2-3 s assuming a 64-thread executor (one slow server doesn't
block the others because each fetch runs in the executor + has its
own ``asyncio.wait_for`` cap).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# How often the background task refreshes every server in parallel.
# 8s is fast enough that a customer enabling/disabling on the portal
# sees the UI flip within one tick, but slow enough that we're not
# hammering the agents during heavy panel usage.
REFRESH_INTERVAL_SECONDS = 8.0

# How long after the last successful refresh of a particular server we
# still consider its data "fresh enough" to skip the lazy fetch.
# Slightly longer than the refresh interval so transient agent
# failures (one slow round) don't trigger lazy refetches in every
# route handler.
STALE_AFTER_SECONDS = 20.0

# Hard cap on a single per-server fetch. If an agent doesn't respond
# in this window, that server is skipped this round and the previous
# snapshot stays in cache. Keeps a single unreachable server from
# eating a refresh window or piling up in the executor.
PER_SERVER_TIMEOUT_SECONDS = 5.0

# Threadpool size for the background refresher. Default executor would
# be min(32, cpu+4), which queues badly at the 100-server target. We
# only need workers during the refresh tick burst (a few seconds out of
# every REFRESH_INTERVAL_SECONDS), so the pool sits idle most of the
# time.
REFRESHER_EXECUTOR_WORKERS = 64


@dataclass
class PeerSnapshot:
    """A single peer's state at the last refresh tick.

    All fields are point-in-time, captured together from one
    ``wg show dump`` (or remote-adapter equivalent). Callers should
    treat instances as immutable — the cache may replace them on the
    next tick rather than mutating in place.
    """
    public_key: str
    handshake: Optional[datetime] = None
    endpoint: Optional[str] = None  # "ip:port" or None
    transfer_rx: int = 0
    transfer_tx: int = 0

    @property
    def endpoint_ip(self) -> Optional[str]:
        """Strip the ``:port`` suffix from ``endpoint`` for GeoIP lookups."""
        if not self.endpoint or self.endpoint == "(none)":
            return None
        return self.endpoint.rsplit(":", 1)[0] if ":" in self.endpoint else self.endpoint


class PeerCache:
    """Thread-safe ``server_id -> {pubkey: PeerSnapshot}`` map.

    Single shared instance — see ``get_cache()`` below. Don't construct
    your own; the background task is bound to the module-level singleton.
    """

    def __init__(self) -> None:
        self._data: Dict[int, Dict[str, PeerSnapshot]] = {}
        self._server_last_refresh: Dict[int, float] = {}
        self._lock = threading.RLock()

    def get_handshake_for(self, server_id: int, pubkey: str) -> Optional[datetime]:
        """Back-compat shortcut used by ``_enrich_handshakes``."""
        with self._lock:
            server = self._data.get(server_id)
            if not server:
                return None
            snap = server.get(pubkey)
            return snap.handshake if snap else None

    def get_for(self, server_id: int, pubkey: str) -> Optional[datetime]:
        """Alias — older callers expected this name to return a handshake."""
        return self.get_handshake_for(server_id, pubkey)

    def get_peer(self, server_id: int, pubkey: str) -> Optional[PeerSnapshot]:
        with self._lock:
            server = self._data.get(server_id)
            if not server:
                return None
            return server.get(pubkey)

    def get_server_peers(self, server_id: int) -> Dict[str, PeerSnapshot]:
        """Return a *copy* of the per-server map so callers can iterate
        without holding the lock. At 1000 peers/server this is a cheap
        shallow copy (~10µs)."""
        with self._lock:
            server = self._data.get(server_id)
            return dict(server) if server else {}

    def has_fresh_data_for(self, server_id: int) -> bool:
        with self._lock:
            last = self._server_last_refresh.get(server_id, 0)
        return (time.time() - last) <= STALE_AFTER_SECONDS

    def replace_server(self, server_id: int, peers_by_pubkey: Dict[str, PeerSnapshot]) -> None:
        """Atomically swap the cached map for one server.

        Removing the old entries first ensures peers that were deleted
        on the node side (via the customer portal between refresh ticks)
        don't linger forever in the cache.
        """
        with self._lock:
            self._data[server_id] = dict(peers_by_pubkey)
            self._server_last_refresh[server_id] = time.time()

    def drop_server(self, server_id: int) -> None:
        """Forget a server entirely (call after server deletion)."""
        with self._lock:
            self._data.pop(server_id, None)
            self._server_last_refresh.pop(server_id, None)

    def invalidate_server(self, server_id: int) -> None:
        """Drop a server's freshness marker so the next read fires a
        fresh fetch. Call after an admin enable/disable so the UI can
        flip immediately instead of waiting up to ``STALE_AFTER_SECONDS``."""
        with self._lock:
            self._server_last_refresh.pop(server_id, None)
            # We don't drop the data itself — stale snapshots are still
            # better than nothing while the lazy refetch runs.

    def stats(self) -> Dict[str, int]:
        """Diagnostic stats used by /debug pages."""
        with self._lock:
            return {
                "servers_with_data": len(self._data),
                "total_peers": sum(len(s) for s in self._data.values()),
                "servers_fresh": len(self._server_last_refresh),
            }


# Back-compat alias — older imports referenced HandshakeCache.
HandshakeCache = PeerCache


_cache: Optional[PeerCache] = None
_refresher_task: Optional[asyncio.Task] = None
_refresher_started = False
_refresher_lock = threading.Lock()
_executor: Optional[ThreadPoolExecutor] = None


def get_cache() -> PeerCache:
    """Module-level singleton getter.

    Initialises lazily so importing this module doesn't allocate state
    in test runs that never need it.
    """
    global _cache
    if _cache is None:
        _cache = PeerCache()
    return _cache


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=REFRESHER_EXECUTOR_WORKERS,
            thread_name_prefix="peer-refresh",
        )
    return _executor


# ── Single-server fetch helper, used both by the background task and
#    by the per-request lazy fallback. ──────────────────────────────────

def fetch_server_peers_sync(server) -> Dict[str, PeerSnapshot]:
    """Poll a single server's WG interface and return a
    ``{pubkey: PeerSnapshot}`` map.

    Synchronous (subprocess / SSH / HTTP). Catches its own exceptions
    and returns an empty dict on failure — the caller treats that as
    "no fresh data" and falls back to the previous snapshot.
    """
    server_type = getattr(server, "server_type", "wireguard") or "wireguard"
    is_proxy = (
        getattr(server, "server_category", "vpn") == "proxy"
        or server_type in ("hysteria2", "tuic")
    )
    if is_proxy:
        return {}

    try:
        is_remote = bool(server.ssh_host) or (
            (getattr(server, "agent_mode", None) or "") == "mikrotik"
        )
        if is_remote:
            from src.core.remote_adapter import RemoteServerAdapter
            adapter = RemoteServerAdapter(
                server=server,
                interface=server.interface,
                config_path=server.config_path,
            )
            try:
                peers = adapter.get_all_peers()
            finally:
                adapter.close()
        elif server_type == "amneziawg":
            from src.core.amneziawg import AmneziaWGManager
            mgr = AmneziaWGManager(
                interface=server.interface, config_path=server.config_path,
            )
            peers = mgr.get_all_peers()
        else:
            from src.core.wireguard import WireGuardManager
            mgr = WireGuardManager(
                interface=server.interface, config_path=server.config_path,
            )
            peers = mgr.get_all_peers()
    except Exception as e:
        logger.debug("peer_cache: fetch failed for server %s: %s", getattr(server, "name", "?"), e)
        return {}

    out: Dict[str, PeerSnapshot] = {}
    for peer in peers:
        pubkey = getattr(peer, "public_key", None)
        if not pubkey:
            continue
        hs_raw = getattr(peer, "latest_handshake", None)
        hs: Optional[datetime] = None
        if hs_raw and isinstance(hs_raw, (int, float)) and hs_raw > 0:
            hs = datetime.fromtimestamp(hs_raw, tz=timezone.utc)
        elif isinstance(hs_raw, datetime):
            hs = hs_raw if hs_raw.tzinfo else hs_raw.replace(tzinfo=timezone.utc)
        out[pubkey] = PeerSnapshot(
            public_key=pubkey,
            handshake=hs,
            endpoint=getattr(peer, "endpoint", None),
            transfer_rx=int(getattr(peer, "transfer_rx", 0) or 0),
            transfer_tx=int(getattr(peer, "transfer_tx", 0) or 0),
        )
    return out


async def _refresh_one_server(server) -> None:
    """Fetch one server with a hard timeout. Never raises — failures
    are logged and the previous snapshot stays in cache."""
    cache = get_cache()
    loop = asyncio.get_running_loop()
    executor = _get_executor()
    try:
        peers = await asyncio.wait_for(
            loop.run_in_executor(executor, fetch_server_peers_sync, server),
            timeout=PER_SERVER_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.debug("peer_cache: server %s refresh timed out after %ss",
                     server.id, PER_SERVER_TIMEOUT_SECONDS)
        return
    except Exception as e:
        logger.debug("peer_cache: server %s refresh raised %s", server.id, e)
        return

    # Only replace if we actually got data; an empty dict from a
    # transient failure shouldn't wipe a previously good cache.
    if peers:
        cache.replace_server(server.id, peers)
    else:
        # Mark refresh time anyway so lazy-refetch doesn't immediately
        # fire again — but only if there was already data, so a fresh
        # cold-start server still triggers the lazy path on first read.
        if cache.has_fresh_data_for(server.id):
            cache.replace_server(server.id, {})


async def _refresh_all_servers_once() -> None:
    """Pull a fresh snapshot from every active server in parallel."""
    # Late imports so the module stays import-cheap.
    from src.database.connection import SessionLocal
    from src.database.models import Server

    db = SessionLocal()
    try:
        servers = db.query(Server).filter(Server.is_active == True).all()  # noqa: E712
    finally:
        db.close()

    if not servers:
        return

    await asyncio.gather(*(_refresh_one_server(s) for s in servers))


async def _refresher_loop() -> None:
    """The background task. Runs forever, refreshing every interval."""
    logger.info("peer_cache: background refresher started (interval=%ss, per-server-timeout=%ss)",
                REFRESH_INTERVAL_SECONDS, PER_SERVER_TIMEOUT_SECONDS)
    # First refresh fires immediately so the cache is hot for the first
    # request after startup.
    try:
        await _refresh_all_servers_once()
    except Exception as e:
        logger.warning("peer_cache: first refresh raised: %s", e)
    while True:
        try:
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
            await _refresh_all_servers_once()
        except asyncio.CancelledError:
            logger.info("peer_cache: background refresher cancelled")
            raise
        except Exception as e:
            logger.warning("peer_cache: refresh tick raised: %s", e)
            # Don't let one bad tick kill the loop forever.


def ensure_refresher_started() -> None:
    """Idempotent: start the background task once, on first call.

    Safe to call from any request handler; cheap on subsequent calls.
    Bound to the running asyncio loop, which is the FastAPI one.
    """
    global _refresher_task, _refresher_started
    with _refresher_lock:
        if _refresher_started:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Called from a worker thread that doesn't have an event
            # loop — defer to the first async handler that touches us.
            return
        _refresher_task = loop.create_task(_refresher_loop())
        _refresher_started = True
        logger.info("peer_cache: background refresher scheduled on event loop")
