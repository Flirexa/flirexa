"""
Flirexa Bandwidth Monitor
Computes real-time bandwidth rates from cumulative WireGuard transfer counters.

Reads peer transfer counters from the shared peer cache
(``src.modules.cache.handshake_cache``). The background refresher polls
every active server in parallel every ~8s with a per-server hard
timeout, so this endpoint stays under 50ms even on a panel with 100
servers — no network I/O on the request path.
"""

from typing import Optional, Dict, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import threading
import time as _time
from loguru import logger

from ..database.models import Server, Client

# Module-level storage for previous snapshots — drives the delta math
# that converts cumulative WG counters into a per-peer Mbps rate.
# {server_id: {"time": datetime, "peers": {public_key: (rx_bytes, tx_bytes)}}}
_PREV_SNAPSHOT: Dict[int, dict] = {}

# Per-(server_id) response cache. The handshake refresher only refills
# the underlying snapshots every REFRESH_INTERVAL_SECONDS (~8s), so any
# requests within that window can safely return the same response.
# This cuts the polling load on hot panels (Servers tab, 6 servers,
# 5s refresh × multiple operator sessions = >10 calls/sec/server) to
# at most one DB session per (server, RESPONSE_CACHE_SECONDS) window.
RESPONSE_CACHE_SECONDS = 3.0
_response_cache: Dict[int, tuple[float, dict]] = {}
_response_cache_lock = threading.Lock()


def _response_cache_get(server_id: int) -> Optional[dict]:
    with _response_cache_lock:
        entry = _response_cache.get(server_id)
        if entry is None:
            return None
        expires_at, payload = entry
        if _time.monotonic() < expires_at:
            return payload
        # Stale; drop. Caller will compute fresh + store.
        _response_cache.pop(server_id, None)
        return None


def _response_cache_set(server_id: int, payload: dict) -> None:
    with _response_cache_lock:
        _response_cache[server_id] = (
            _time.monotonic() + RESPONSE_CACHE_SECONDS, payload,
        )


def invalidate_bandwidth_response_cache(server_id: Optional[int] = None) -> None:
    """Clear the per-server bandwidth response cache. Called by writer
    paths (peer enabled/disabled, slot switch) so a UI refresh after an
    admin action surfaces the change immediately rather than waiting
    for the cache window to elapse."""
    with _response_cache_lock:
        if server_id is None:
            _response_cache.clear()
        else:
            _response_cache.pop(server_id, None)


class BandwidthMonitor:
    def __init__(self, db: Session):
        self.db = db

    def get_server_bandwidth(self, server_id: int) -> Optional[dict]:
        """
        Get current bandwidth rates for a server.
        First call stores baseline (returns zero rates).
        Subsequent calls compute delta from previous snapshot.

        Response is memoized per (server_id) for RESPONSE_CACHE_SECONDS.
        Concurrent callers within that window return the same dict
        rather than each opening a DB session + decrypting Server + the
        Client batch lookup. Without this, the Servers tab polling 6
        servers every 5s × multiple operator sessions blew right
        through the connection pool on every refresh.
        """
        cached = _response_cache_get(server_id)
        if cached is not None:
            return cached

        # Project to the columns we actually read here — Server has
        # EncryptedText columns (ssh_password, ssh_private_key,
        # agent_api_key) that auto-decrypt on every full ORM fetch.
        # On a polled hot path that's measurable CPU we never use.
        srv_row = (
            self.db.query(
                Server.id, Server.name, Server.server_category,
                Server.server_type, Server.max_bandwidth_mbps,
            )
            .filter(Server.id == server_id)
            .first()
        )
        if not srv_row:
            return None

        # Proxy servers (Hysteria2/TUIC) do not have WireGuard peers — skip.
        if srv_row.server_category == 'proxy' or \
                srv_row.server_type in ('hysteria2', 'tuic'):
            return None
        server = srv_row

        now = datetime.now(timezone.utc)

        # Read from the shared peer cache. The cache is warmed by the
        # background refresher armed in api lifespan. If a server is
        # cold (just added, refresher hasn't ticked yet) we return zero
        # rates rather than fall back to a synchronous SSH/agent fetch —
        # that fallback used to bury the single api worker when the
        # Servers tab polled bandwidth for every server every 5s
        # (2026-06-11 incident), and indirectly broke customer config
        # fetches that share the same worker. Worst case the live Mbps
        # gauge reads 0 for one ~8s refresh tick after a panel reboot.
        from ..modules.cache.handshake_cache import get_cache
        cache = get_cache()

        if not cache.has_fresh_data_for(server_id):
            warming = {
                "server_id":           server_id,
                "server_name":         server.name,
                "total_rx_rate_mbps":  0.0,
                "total_tx_rate_mbps":  0.0,
                "total_rate_mbps":     0.0,
                "max_bandwidth_mbps":  server.max_bandwidth_mbps,
                "usage_percent":       None,
                "peer_rates":          [],
                "timestamp":           now.isoformat(),
                "cache_status":        "warming",
            }
            _response_cache_set(server_id, warming)
            return warming

        peer_snapshots = cache.get_server_peers(server_id)

        # Build current snapshot: {public_key: (rx, tx)}
        current = {pk: (snap.transfer_rx, snap.transfer_tx)
                   for pk, snap in peer_snapshots.items()}

        # Client lookup: public_key -> (name, id, ipv4, owner_server_id).
        # Scope to the keys we actually saw on this server's WG — the
        # previous Client.all() loaded the whole table on every refresh.
        #
        # Critically, pull ONLY the five columns we use — full Client
        # ORM objects auto-decrypt EncryptedText columns (private_key,
        # preshared_key, proxy_password) through Fernet on every fetch,
        # which on a server with hundreds of peers and panel polling
        # every 5s burns one full CPU core just on AES + HMAC. The
        # 2026-06-11 second incident was this exact path — py-spy
        # showed cryptography.fernet.decrypt at 100% CPU on every
        # bandwidth tick. with_entities skips the encrypted columns
        # entirely so the result rows are plain tuples.
        pks = list(peer_snapshots.keys())
        if pks:
            rows = (
                self.db.query(
                    Client.public_key,
                    Client.name,
                    Client.id,
                    Client.ipv4,
                    Client.server_id,
                )
                .filter(Client.public_key.in_(pks))
                .all()
            )
        else:
            rows = []
        cmap = {
            pk: (name, cid, ipv4 or "?", sid)
            for pk, name, cid, ipv4, sid in rows
        }

        # Compute rates from delta
        peer_rates = []
        total_rx = 0.0
        total_tx = 0.0

        # Pre-resolve names for any shadow-peer owner servers in one batched,
        # projected query. The previous per-shadow `db.query(Server)...first()`
        # inside the loop loaded the full ORM row including Fernet-encrypted
        # columns (ssh_password, ssh_private_key, agent_api_key) — and decrypted
        # all three per shadow peer. With dual-active migrations that meant
        # potentially dozens of redundant Fernet decrypts on every poll tick.
        shadow_owner_names: Dict[int, str] = {server_id: server.name}
        shadow_owner_sids = {
            owner_sid
            for _, _, _, owner_sid in cmap.values()
            if owner_sid is not None and owner_sid != server_id
        }
        if shadow_owner_sids:
            rows = (
                self.db.query(Server.id, Server.name)
                .filter(Server.id.in_(shadow_owner_sids))
                .all()
            )
            for r in rows:
                shadow_owner_names[r.id] = r.name

        prev = _PREV_SNAPSHOT.get(server_id)
        if prev:
            dt = max(1.0, (now - prev["time"]).total_seconds())
            for pub_key, (curr_rx, curr_tx) in current.items():
                prev_rx, prev_tx = prev["peers"].get(pub_key, (curr_rx, curr_tx))
                delta_rx = max(0, curr_rx - prev_rx)
                delta_tx = max(0, curr_tx - prev_tx)
                rx_mbps = round(delta_rx * 8 / dt / 1_000_000, 2)
                tx_mbps = round(delta_tx * 8 / dt / 1_000_000, 2)

                name, cid, ipv4, owner_sid = cmap.get(pub_key, (pub_key[:12], 0, "?", None))
                # Mark peers whose DB record lives on a different server (the
                # dual-active "shadow peer" case) so the UI can show e.g.
                # "test1 (from cloudConeWG)".
                shadow_from = None
                if owner_sid is not None and owner_sid != server_id:
                    shadow_from = shadow_owner_names.get(owner_sid, f"server #{owner_sid}")
                peer_rates.append({
                    "public_key": pub_key,
                    "client_name": name,
                    "client_id": cid,
                    "ipv4": ipv4,
                    "rx_rate_mbps": rx_mbps,
                    "tx_rate_mbps": tx_mbps,
                    "total_rate_mbps": round(rx_mbps + tx_mbps, 2),
                    "shadow_from": shadow_from,  # null for native, server name for dual-active mirrors
                })
                total_rx += rx_mbps
                total_tx += tx_mbps

        # Store snapshot for next call
        _PREV_SNAPSHOT[server_id] = {"time": now, "peers": current}

        # Sort by total_rate desc (top consumers first)
        peer_rates.sort(key=lambda x: x["total_rate_mbps"], reverse=True)

        # Usage percent
        max_bw = server.max_bandwidth_mbps
        usage_pct = None
        if max_bw and max_bw > 0:
            usage_pct = round((total_rx + total_tx) / max_bw * 100, 1)

        payload = {
            "server_id": server_id,
            "server_name": server.name,
            "total_rx_rate_mbps": round(total_rx, 2),
            "total_tx_rate_mbps": round(total_tx, 2),
            "total_rate_mbps": round(total_rx + total_tx, 2),
            "max_bandwidth_mbps": max_bw,
            "usage_percent": usage_pct,
            "peer_rates": peer_rates,
            "timestamp": now.isoformat(),
        }
        _response_cache_set(server_id, payload)
        return payload
