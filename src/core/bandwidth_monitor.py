"""
VPN Management Studio Bandwidth Monitor
Computes real-time bandwidth rates from cumulative WireGuard transfer counters.
"""

from typing import Optional, Dict, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from loguru import logger

from ..database.models import Server, Client

# Module-level storage for previous snapshots
# {server_id: {"time": datetime, "peers": {public_key: (rx_bytes, tx_bytes)}}}
_PREV_SNAPSHOT: Dict[int, dict] = {}


class BandwidthMonitor:
    def __init__(self, db: Session):
        self.db = db

    def _get_wg(self, server):
        """Create WireGuard manager or RemoteServerAdapter for a server."""
        if server.ssh_host or (server.agent_mode and server.agent_mode == "agent"):
            from .remote_adapter import RemoteServerAdapter
            return RemoteServerAdapter(
                server=server,
                interface=server.interface,
                config_path=server.config_path,
            )
        # Local server — use AWG manager for amneziawg interfaces
        if getattr(server, 'server_type', 'wireguard') == 'amneziawg':
            from .amneziawg import AmneziaWGManager
            return AmneziaWGManager(
                interface=server.interface,
                config_path=server.config_path,
            )
        from .wireguard import WireGuardManager
        return WireGuardManager(
            interface=server.interface,
            config_path=server.config_path,
        )

    def get_server_bandwidth(self, server_id: int) -> Optional[dict]:
        """
        Get current bandwidth rates for a server.
        First call stores baseline (returns zero rates).
        Subsequent calls compute delta from previous snapshot.
        """
        server = self.db.query(Server).filter(Server.id == server_id).first()
        if not server:
            return None

        # Proxy servers (Hysteria2/TUIC) do not have WireGuard peers — skip.
        if getattr(server, 'server_category', None) == 'proxy' or \
                getattr(server, 'server_type', '') in ('hysteria2', 'tuic'):
            return None

        now = datetime.now(timezone.utc)

        # Fetch current peer data
        wg = self._get_wg(server)
        try:
            peers = wg.get_all_peers()
        except Exception as e:
            logger.error(f"Bandwidth monitor: failed to get peers for server {server_id}: {e}")
            return None
        finally:
            if hasattr(wg, 'close'):
                try:
                    wg.close()
                except Exception:
                    pass

        # Build current snapshot: {public_key: (rx, tx)}
        current = {}
        for p in peers:
            current[p.public_key] = (p.transfer_rx, p.transfer_tx)

        # Client lookup: public_key -> (name, id, ipv4, owner_server_id)
        # Look up across ALL servers, not just this one — when dual-active
        # migration ("Keep clients on source server") adds a peer to the
        # destination server's WireGuard, the matching DB record stays on
        # the SOURCE server. Filtering by server_id alone produces an empty
        # cmap on dst, and live peers fall back to public-key fragments in
        # the panel's Top Consumers list.
        clients = self.db.query(Client).all()
        cmap = {}
        for c in clients:
            cmap[c.public_key] = (c.name, c.id, c.ipv4 or "?", c.server_id)

        # Compute rates from delta
        peer_rates = []
        total_rx = 0.0
        total_tx = 0.0

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
                    src_srv = next((s for s in [server] if s.id == owner_sid), None)
                    if src_srv is None:
                        from ..database.models import Server as _S
                        src_srv = self.db.query(_S).filter(_S.id == owner_sid).first()
                    shadow_from = src_srv.name if src_srv else f"server #{owner_sid}"
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

        return {
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
