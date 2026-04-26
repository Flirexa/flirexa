"""
VPN Management Studio Traffic Manager
Handles traffic monitoring, limits, and bandwidth control
"""

from typing import Optional, List, Tuple, Dict
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from loguru import logger
import subprocess
import threading
import re

from ..database.models import Client, Server, ClientStatus, TrafficDaily, TrafficRule
from .wireguard import WireGuardManager
from datetime import date as date_type

# Module-level cache for remote server traffic stats (reduces HTTP requests)
_TRAFFIC_STATS_CACHE: Dict[int, Dict] = {}           # server_id -> {public_key: (rx, tx)}
_TRAFFIC_STATS_CACHE_TIME: Dict[int, datetime] = {}
_TRAFFIC_STATS_CACHE_TTL = 30  # seconds
_TRAFFIC_CACHE_LOCK = threading.Lock()


@dataclass
class TrafficStats:
    """Traffic statistics for a client"""
    client_name: str
    rx_bytes: int  # Received (download from client perspective)
    tx_bytes: int  # Transmitted (upload from client perspective)
    total_bytes: int
    limit_bytes: Optional[int]
    percent_used: float
    is_exceeded: bool


class TrafficManager:
    """
    Manages traffic monitoring and limits
    Implements the BASELINE system for accurate traffic tracking
    """

    def __init__(
        self,
        db: Session,
        wg_manager: Optional[WireGuardManager] = None
    ):
        self.db = db
        self.wg_manager = wg_manager or WireGuardManager()

    def _get_wg(self, server: Server):
        """
        Create WireGuard manager for server (local or remote).

        Returns RemoteServerAdapter for remote servers (routes to SSH or Agent).
        Returns AmneziaWGManager/WireGuardManager for local servers (direct execution).
        """
        # Local server - use direct manager (AWG or standard WG)
        if not server.ssh_host:
            if getattr(server, 'server_type', 'wireguard') == 'amneziawg':
                from .amneziawg import AmneziaWGManager
                return AmneziaWGManager(
                    interface=server.interface,
                    config_path=server.config_path
                )
            return WireGuardManager(
                interface=server.interface,
                config_path=server.config_path
            )

        # Remote server - use RemoteServerAdapter (SSH or Agent mode)
        from .remote_adapter import RemoteServerAdapter
        return RemoteServerAdapter(
            server=server,
            interface=server.interface,
            config_path=server.config_path
        )

    # ========================================================================
    # TRAFFIC MONITORING
    # ========================================================================

    def _get_cached_peer_transfer(self, server: Server, public_key: str) -> tuple:
        """Get peer transfer stats with caching for remote servers.
        Fetches all peers in one request and caches for _TRAFFIC_STATS_CACHE_TTL seconds."""
        now = datetime.now(timezone.utc)
        server_id = server.id

        # Fix M-5: use module-level lock so concurrent threads don't each trigger
        # a separate WG fetch for the same server within the same cache window.
        with _TRAFFIC_CACHE_LOCK:
            # Check cache validity
            if server_id in _TRAFFIC_STATS_CACHE and server_id in _TRAFFIC_STATS_CACHE_TIME:
                cache_age = (now - _TRAFFIC_STATS_CACHE_TIME[server_id]).total_seconds()
                if cache_age < _TRAFFIC_STATS_CACHE_TTL:
                    return _TRAFFIC_STATS_CACHE[server_id].get(public_key, (0, 0))

        # Cache miss — fetch all peers in one request (outside lock to avoid blocking)
        wg = self._get_wg(server)
        try:
            peers = wg.get_all_peers()
        finally:
            wg.close()

        # Build cache: public_key -> (rx, tx)
        peer_map = {}
        for p in peers:
            peer_map[p.public_key] = (p.transfer_rx, p.transfer_tx)

        with _TRAFFIC_CACHE_LOCK:
            _TRAFFIC_STATS_CACHE[server_id] = peer_map
            _TRAFFIC_STATS_CACHE_TIME[server_id] = now

        return peer_map.get(public_key, (0, 0))

    @staticmethod
    def clear_traffic_cache(server_id: Optional[int] = None):
        """Clear traffic stats cache"""
        if server_id is None:
            _TRAFFIC_STATS_CACHE.clear()
            _TRAFFIC_STATS_CACHE_TIME.clear()
        else:
            _TRAFFIC_STATS_CACHE.pop(server_id, None)
            _TRAFFIC_STATS_CACHE_TIME.pop(server_id, None)

    def get_client_traffic(self, client: Client) -> TrafficStats:
        """
        Get current traffic statistics for a client
        Uses BASELINE system for accurate tracking after resets
        """
        # Get current traffic from WireGuard
        server = client.server
        if server:
            # Use cached batch fetch (1 request per server per 30s); _get_cached_peer_transfer
            # uses _get_wg(server) which selects the correct interface for local servers too.
            current_rx, current_tx = self._get_cached_peer_transfer(server, client.public_key)
        else:
            # No server — fall back to default wg_manager (edge case)
            current_rx, current_tx = self.wg_manager.get_peer_transfer(client.public_key)

        # Calculate actual traffic using baseline system
        # Baseline represents the WireGuard counter value at the time of last reset
        actual_rx = max(0, current_rx - client.traffic_baseline_rx) + client.traffic_used_rx
        actual_tx = max(0, current_tx - client.traffic_baseline_tx) + client.traffic_used_tx
        total = actual_rx + actual_tx

        # Calculate limit info
        limit_bytes = None
        percent_used = 0
        is_exceeded = False

        if client.traffic_limit_mb and client.traffic_limit_mb > 0:
            limit_bytes = client.traffic_limit_mb * 1024 * 1024
            percent_used = (total / limit_bytes * 100) if limit_bytes > 0 else 0
            is_exceeded = total >= limit_bytes

        return TrafficStats(
            client_name=client.name,
            rx_bytes=actual_rx,
            tx_bytes=actual_tx,
            total_bytes=total,
            limit_bytes=limit_bytes,
            percent_used=percent_used,
            is_exceeded=is_exceeded
        )

    def get_all_traffic_stats(
        self,
        server_id: Optional[int] = None
    ) -> List[TrafficStats]:
        """Get traffic statistics for all clients"""
        query = self.db.query(Client)
        if server_id:
            query = query.filter(Client.server_id == server_id)

        clients = query.all()
        return [self.get_client_traffic(c) for c in clients]

    # ========================================================================
    # TRAFFIC LIMITS
    # ========================================================================

    def set_traffic_limit(
        self,
        client_id: int,
        limit_mb: int,
        duration_days: int = 0,
        sync_with_expiry: bool = False,
        auto_reset: bool = True
    ) -> bool:
        """
        Set traffic limit for a client

        Args:
            client_id: ID of the client
            limit_mb: Traffic limit in megabytes (0 = remove limit)
            duration_days: Days until limit expires (0 = permanent)
            sync_with_expiry: Sync limit expiry with client expiry_date
            auto_reset: Automatically reset counter if current exceeds new limit

        Returns:
            True if successful
        """
        client = self.db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return False

        # Proxy clients have no WG-based traffic tracking — not supported
        if client.is_proxy_client:
            logger.warning(
                f"set_traffic_limit called on proxy client '{client.name}' — not supported, ignoring"
            )
            return False

        if limit_mb <= 0:
            # Remove limit
            client.traffic_limit_mb = None
            client.traffic_limit_expiry = None
            self.db.commit()
            logger.info(f"Removed traffic limit for {client.name}")
            return True

        # Check if we need to reset counter
        if auto_reset:
            current_stats = self.get_client_traffic(client)
            limit_bytes = limit_mb * 1024 * 1024

            # Reset if this is first limit or current exceeds new limit
            if client.traffic_limit_mb is None or current_stats.total_bytes >= limit_bytes:
                self.reset_traffic_counter(client_id)

        # Calculate expiry
        expiry = None
        if sync_with_expiry and client.expiry_date:
            expiry = client.expiry_date
        elif duration_days > 0:
            expiry = datetime.now(timezone.utc) + timedelta(days=duration_days)

        # Update client
        client.traffic_limit_mb = limit_mb
        client.traffic_limit_expiry = expiry
        self.db.commit()

        logger.info(f"Set traffic limit for {client.name}: {limit_mb} MB, expiry: {expiry}")
        return True

    def reset_traffic_counter(self, client_id: int) -> bool:
        """
        Reset traffic counter for a client
        Sets current WireGuard counters as the new baseline
        """
        client = self.db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return False

        now = datetime.now(timezone.utc)

        # Proxy clients have no WireGuard peers — zero out DB counters directly
        if client.is_proxy_client:
            client.traffic_used_rx = 0
            client.traffic_used_tx = 0
            client.traffic_reset_date = now
            self.db.commit()
            logger.info(f"Reset traffic counter for proxy client {client.name}")
            return True

        # WireGuard clients: get current counters as new baseline
        server = client.server
        if server:
            current_rx, current_tx = self._get_cached_peer_transfer(server, client.public_key)
        else:
            current_rx, current_tx = self.wg_manager.get_peer_transfer(client.public_key)

        # Set these as the new baseline
        # Now traffic = (current - baseline) + saved
        # After reset: traffic = (current - current) + 0 = 0
        client.traffic_baseline_rx = current_rx
        client.traffic_baseline_tx = current_tx
        client.traffic_used_rx = 0
        client.traffic_used_tx = 0
        client.traffic_reset_date = now

        self.db.commit()

        logger.info(f"Reset traffic counter for {client.name}")
        return True

    def sync_traffic_to_db(self) -> int:
        """
        Sync live WireGuard traffic counters to database for all enabled clients.
        After sync, traffic_used_rx/tx in DB contain real accumulated values.
        Called by monitoring loop before limit checks.

        Returns:
            Number of clients synced
        """
        clients = self.db.query(Client).filter(Client.enabled == True).all()
        count = 0

        for client in clients:
            try:
                # Proxy clients have no WireGuard peers — no traffic to sync via wg
                if client.is_proxy_client:
                    continue

                server = client.server
                if server:
                    current_rx, current_tx = self._get_cached_peer_transfer(server, client.public_key)
                else:
                    current_rx, current_tx = self.wg_manager.get_peer_transfer(client.public_key)

                # Compute actual traffic using baseline system
                old_rx = client.traffic_used_rx
                old_tx = client.traffic_used_tx
                actual_rx = max(0, current_rx - client.traffic_baseline_rx) + old_rx
                actual_tx = max(0, current_tx - client.traffic_baseline_tx) + old_tx

                # Calculate delta for daily tracking
                delta_rx = max(0, actual_rx - old_rx)
                delta_tx = max(0, actual_tx - old_tx)

                # Save: current WG counters become new baseline, actual values stored
                client.traffic_baseline_rx = current_rx
                client.traffic_baseline_tx = current_tx
                client.traffic_used_rx = actual_rx
                client.traffic_used_tx = actual_tx
                count += 1

                # Update daily traffic record
                if delta_rx > 0 or delta_tx > 0:
                    today = date_type.today()
                    daily = self.db.query(TrafficDaily).filter_by(
                        client_id=client.id, date=today
                    ).first()
                    if daily:
                        daily.bytes_rx += delta_rx
                        daily.bytes_tx += delta_tx
                    else:
                        self.db.add(TrafficDaily(
                            client_id=client.id, date=today,
                            bytes_rx=delta_rx, bytes_tx=delta_tx
                        ))
            except Exception as e:
                logger.error(f"Failed to sync traffic for {client.name}: {e}")

        if count > 0:
            self.db.commit()
            logger.debug(f"Synced traffic for {count} clients")

        return count

    def check_traffic_limits(self) -> List[Client]:
        """
        Check all clients for traffic limit violations
        Disables clients that have exceeded their limits

        Returns:
            List of clients that were disabled
        """
        disabled_clients = []
        now = datetime.now(timezone.utc)

        # Get all enabled clients with traffic limits
        clients = self.db.query(Client).filter(
            and_(
                Client.enabled == True,
                Client.traffic_limit_mb != None,
                Client.traffic_limit_mb > 0
            )
        ).all()

        for client in clients:
            # Proxy clients don't have WG-tracked traffic — skip enforcement
            if client.is_proxy_client:
                continue

            # Check if limit has expired (needs renewal)
            limit_expiry = client.traffic_limit_expiry
            if limit_expiry and limit_expiry.tzinfo is None:
                limit_expiry = limit_expiry.replace(tzinfo=timezone.utc)
            if limit_expiry and now >= limit_expiry:
                # Limit period expired - reset counter and extend
                self._handle_limit_expiry(client)
                continue

            # Check if traffic exceeded
            stats = self.get_client_traffic(client)
            if stats.is_exceeded:
                # Disable client
                self._disable_for_traffic(client)
                disabled_clients.append(client)

        return disabled_clients

    def _handle_limit_expiry(self, client: Client) -> None:
        """Handle traffic limit period expiry"""
        # Calculate the period duration
        if client.traffic_reset_date:
            limit_exp = client.traffic_limit_expiry
            reset_dt = client.traffic_reset_date
            if limit_exp.tzinfo is None:
                limit_exp = limit_exp.replace(tzinfo=timezone.utc)
            if reset_dt.tzinfo is None:
                reset_dt = reset_dt.replace(tzinfo=timezone.utc)
            period_duration = (limit_exp - reset_dt).days
        else:
            period_duration = 30  # Default to monthly

        # Reset counter
        self.reset_traffic_counter(client.id)

        # Extend limit expiry
        if period_duration > 0:
            client.traffic_limit_expiry = datetime.now(timezone.utc) + timedelta(days=period_duration)
            self.db.commit()
            logger.info(f"Renewed traffic limit for {client.name} ({period_duration} days)")

    def _disable_for_traffic(self, client: Client) -> None:
        """Disable client due to traffic limit exceeded"""
        try:
            server = client.server

            # Proxy clients: just update DB + regenerate proxy config
            if client.is_proxy_client:
                client.enabled = False
                client.status = ClientStatus.TRAFFIC_EXCEEDED
                self.db.commit()
                if server:
                    from .client_manager import ClientManager
                    cm = ClientManager(self.db)
                    cm._apply_proxy_config(server)
                logger.warning(f"Client {client.name} disabled: traffic exceeded (proxy)")
                return

            # WireGuard clients: remove peer first
            wg = self._get_wg(server) if server else self.wg_manager
            wg.remove_peer(client.public_key)
            if wg is not self.wg_manager:
                wg.close()

            # Update status
            client.enabled = False
            client.status = ClientStatus.TRAFFIC_EXCEEDED
            self.db.commit()

            stats = self.get_client_traffic(client)
            logger.warning(
                f"Client {client.name} disabled: traffic exceeded "
                f"({self.format_bytes(stats.total_bytes)} / "
                f"{client.traffic_limit_mb} MB)"
            )
        except Exception as e:
            logger.error(f"Failed to disable {client.name} for traffic: {e}")

    # ========================================================================
    # AUTO-RULES ENGINE
    # ========================================================================

    def get_top_consumers(self, period: str = "day", limit: int = 10) -> List[Dict]:
        """
        Get top traffic consumers for a period.

        Args:
            period: 'day', 'week', or 'month'
            limit: max number of results

        Returns:
            List of dicts with client info and traffic totals
        """
        from sqlalchemy import func as sa_func

        today = date_type.today()
        if period == "day":
            start_date = today
        elif period == "week":
            start_date = today - timedelta(days=7)
        else:  # month
            start_date = today - timedelta(days=30)

        results = (
            self.db.query(
                TrafficDaily.client_id,
                sa_func.sum(TrafficDaily.bytes_rx).label("total_rx"),
                sa_func.sum(TrafficDaily.bytes_tx).label("total_tx"),
                sa_func.sum(TrafficDaily.bytes_rx + TrafficDaily.bytes_tx).label("total"),
            )
            .filter(TrafficDaily.date >= start_date)
            .group_by(TrafficDaily.client_id)
            .order_by(sa_func.sum(TrafficDaily.bytes_rx + TrafficDaily.bytes_tx).desc())
            .limit(limit)
            .all()
        )

        top = []
        for r in results:
            client = self.db.query(Client).filter(Client.id == r.client_id).first()
            if not client:
                continue
            server = client.server
            top.append({
                "client_id": client.id,
                "client_name": client.name,
                "server_id": client.server_id,
                "server_name": server.name if server else "Unknown",
                "bytes_rx": r.total_rx or 0,
                "bytes_tx": r.total_tx or 0,
                "bytes_total": r.total or 0,
                "bandwidth_limit": client.bandwidth_limit,
                "auto_bandwidth_limit": client.auto_bandwidth_limit,
                "auto_bandwidth_rule_id": client.auto_bandwidth_rule_id,
            })

        return top

    def check_traffic_rules(self) -> int:
        """
        Evaluate all enabled traffic rules and apply/remove auto bandwidth limits.

        Returns:
            Number of clients affected
        """
        from sqlalchemy import func as sa_func

        rules = (
            self.db.query(TrafficRule)
            .filter(TrafficRule.enabled == True)
            .order_by(TrafficRule.threshold_mb.asc())
            .all()
        )

        if not rules:
            return 0

        today = date_type.today()
        affected = 0

        # Calculate period usage for all clients at once
        # We need usage for each period type that rules use
        periods_needed = set(r.period for r in rules)
        period_usage = {}  # {client_id: {period: bytes_total}}

        for period in periods_needed:
            if period == "day":
                start_date = today
            elif period == "week":
                start_date = today - timedelta(days=7)
            else:
                start_date = today - timedelta(days=30)

            results = (
                self.db.query(
                    TrafficDaily.client_id,
                    sa_func.sum(TrafficDaily.bytes_rx + TrafficDaily.bytes_tx).label("total"),
                )
                .filter(TrafficDaily.date >= start_date)
                .group_by(TrafficDaily.client_id)
                .all()
            )

            for r in results:
                if r.client_id not in period_usage:
                    period_usage[r.client_id] = {}
                period_usage[r.client_id][period] = r.total or 0

        # For each client, find the strictest matching rule
        clients = self.db.query(Client).filter(Client.enabled == True).all()

        for client in clients:
            usage = period_usage.get(client.id, {})
            matching_rule = None

            # Rules are sorted by threshold_mb ASC — first match = lowest threshold = strictest
            for rule in rules:
                # Skip rules targeted at a different client
                if rule.client_id is not None and rule.client_id != client.id:
                    continue

                threshold_bytes = rule.threshold_mb * 1024 * 1024
                client_usage = usage.get(rule.period, 0)

                if client_usage >= threshold_bytes:
                    # This rule matches — use the one with lowest bandwidth limit
                    if matching_rule is None or rule.bandwidth_limit_mbps < matching_rule.bandwidth_limit_mbps:
                        matching_rule = rule

            if matching_rule:
                # Client exceeds a rule — apply auto-limit if not already set
                if client.auto_bandwidth_limit != matching_rule.bandwidth_limit_mbps or \
                   client.auto_bandwidth_rule_id != matching_rule.id:
                    client.auto_bandwidth_limit = matching_rule.bandwidth_limit_mbps
                    client.auto_bandwidth_rule_id = matching_rule.id

                    # Apply effective limit via tc
                    effective = matching_rule.bandwidth_limit_mbps
                    if client.bandwidth_limit:
                        effective = min(effective, client.bandwidth_limit)
                    self._apply_bandwidth_for_client(client, effective)

                    affected += 1
                    logger.info(
                        f"Auto-limit: {client.name} → {matching_rule.bandwidth_limit_mbps} Mbps "
                        f"(rule: {matching_rule.name})"
                    )
            else:
                # Client below all thresholds — remove auto-limit if set
                if client.auto_bandwidth_limit is not None:
                    client.auto_bandwidth_limit = None
                    client.auto_bandwidth_rule_id = None

                    # Restore manual limit or remove limit
                    if client.bandwidth_limit:
                        self._apply_bandwidth_for_client(client, client.bandwidth_limit)
                    else:
                        self._remove_bandwidth_for_client(client)

                    affected += 1
                    logger.info(f"Auto-limit removed: {client.name}")

        if affected > 0:
            self.db.commit()

        return affected

    def _apply_bandwidth_for_client(self, client: Client, limit_mbps: int):
        """Apply bandwidth limit for a client (routes to local tc or remote agent)."""
        try:
            self.set_bandwidth_limit(client.id, limit_mbps)
        except Exception as e:
            logger.error(f"Failed to apply bandwidth for {client.name}: {e}")

    def _remove_bandwidth_for_client(self, client: Client):
        """Remove bandwidth limit for a client (routes to local tc or remote agent)."""
        try:
            self.remove_bandwidth_limit(client.id)
        except Exception as e:
            logger.error(f"Failed to remove bandwidth for {client.name}: {e}")

    def cleanup_old_daily_records(self, days_to_keep: int = 90):
        """Delete TrafficDaily records older than N days."""
        cutoff = date_type.today() - timedelta(days=days_to_keep)
        deleted = self.db.query(TrafficDaily).filter(TrafficDaily.date < cutoff).delete()
        if deleted > 0:
            self.db.commit()
            logger.info(f"Cleaned up {deleted} old daily traffic records")

    # ========================================================================
    # BANDWIDTH LIMITING (TC - Traffic Control)
    # ========================================================================

    IFB_DEVICE = "ifb0"

    def setup_bandwidth_qdisc(self, interface: str = "wg0") -> bool:
        """Set up HTB qdisc on egress AND ingress (via IFB) for bandwidth limiting"""
        try:
            # Check if HTB qdisc already exists
            result = subprocess.run(
                ["tc", "qdisc", "show", "dev", interface],
                capture_output=True,
                text=True
            )

            if "htb" in result.stdout:
                self._ensure_ifb(interface)
                return True

            # Delete any existing qdisc
            subprocess.run(
                ["tc", "qdisc", "del", "dev", interface, "root"],
                stderr=subprocess.DEVNULL
            )

            # Create HTB qdisc (egress — limits download)
            subprocess.run(
                [
                    "tc", "qdisc", "add", "dev", interface,
                    "root", "handle", "1:", "htb", "default", "9999"
                ],
                check=True
            )

            # Create root class (1 Gbps default)
            subprocess.run(
                [
                    "tc", "class", "add", "dev", interface,
                    "parent", "1:", "classid", "1:1", "htb",
                    "rate", "1000mbit"
                ],
                check=True
            )

            # Set up IFB for ingress (upload) shaping
            self._ensure_ifb(interface)

            logger.info(f"Set up bandwidth qdisc on {interface} + {self.IFB_DEVICE}")
            return True

        except Exception as e:
            logger.error(f"Failed to setup qdisc: {e}")
            return False

    def _ensure_ifb(self, interface: str) -> bool:
        """Set up IFB device for ingress (upload) shaping."""
        try:
            result = subprocess.run(
                ["tc", "qdisc", "show", "dev", self.IFB_DEVICE],
                capture_output=True, text=True
            )
            if "htb" in result.stdout:
                return True

            subprocess.run(["modprobe", "ifb", "numifbs=1"], stderr=subprocess.DEVNULL)
            subprocess.run(["ip", "link", "set", "dev", self.IFB_DEVICE, "up"],
                            stderr=subprocess.DEVNULL)

            # Redirect ingress from wg interface to ifb0
            subprocess.run(
                ["tc", "qdisc", "add", "dev", interface, "handle", "ffff:", "ingress"],
                stderr=subprocess.DEVNULL
            )
            subprocess.run(
                ["tc", "filter", "add", "dev", interface, "parent", "ffff:",
                 "protocol", "ip", "u32", "match", "u32", "0", "0",
                 "action", "mirred", "egress", "redirect", "dev", self.IFB_DEVICE],
                stderr=subprocess.DEVNULL
            )

            subprocess.run(["tc", "qdisc", "del", "dev", self.IFB_DEVICE, "root"],
                            stderr=subprocess.DEVNULL)
            subprocess.run(
                ["tc", "qdisc", "add", "dev", self.IFB_DEVICE,
                 "root", "handle", "2:", "htb", "default", "9999"],
                capture_output=True
            )
            subprocess.run(
                ["tc", "class", "add", "dev", self.IFB_DEVICE,
                 "parent", "2:", "classid", "2:1", "htb",
                 "rate", "1000mbit"],
                capture_output=True
            )
            logger.info(f"Set up IFB ingress shaping on {self.IFB_DEVICE}")
            return True
        except Exception as e:
            logger.error(f"Failed to setup IFB: {e}")
            return False

    def set_bandwidth_limit(
        self,
        client_id: int,
        bandwidth_mbps: int,
        interface: str = "wg0"
    ) -> bool:
        """
        Set bandwidth limit for a client

        Args:
            client_id: ID of the client
            bandwidth_mbps: Speed limit in Mbps (0 = remove limit)
            interface: WireGuard interface name

        Returns:
            True if successful
        """
        client = self.db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return False

        # Proxy clients have no VPN IP — tc-based bandwidth limiting is not supported
        if client.is_proxy_client:
            logger.warning(
                f"set_bandwidth_limit called on proxy client '{client.name}' — not supported, ignoring"
            )
            return False

        server = client.server

        try:
            if server and server.ssh_host:
                # REMOTE server — delegate to Agent via RemoteServerAdapter
                wg = self._get_wg(server)
                try:
                    if bandwidth_mbps <= 0:
                        result = wg.remove_bandwidth_limit(client.ipv4, client.ip_index)
                    else:
                        result = wg.set_bandwidth_limit(client.ipv4, bandwidth_mbps, client.ip_index)
                finally:
                    wg.close()

                if result:
                    client.bandwidth_limit = bandwidth_mbps if bandwidth_mbps > 0 else None
                    self.db.commit()
                    logger.info(f"Set bandwidth limit for {client.name}: {bandwidth_mbps} Mbps (remote)")
                return result
            else:
                # LOCAL server — tc via subprocess
                self.setup_bandwidth_qdisc(interface)

                class_id = f"1:{client.ip_index}"

                if bandwidth_mbps <= 0:
                    self._remove_tc_class(interface, class_id)
                    # Also remove ingress class
                    ingress_class = f"2:{client.ip_index}"
                    self._remove_tc_class(self.IFB_DEVICE, ingress_class)
                    client.bandwidth_limit = None
                else:
                    rate = f"{bandwidth_mbps}mbit"

                    # === EGRESS (download) on wg interface ===
                    self._ensure_tc_class(interface, "1:1", class_id, rate)
                    if not self._filter_exists(interface, class_id):
                        subprocess.run(
                            [
                                "tc", "filter", "add", "dev", interface,
                                "protocol", "ip", "parent", "1:0", "prio", "1",
                                "u32", "match", "ip", "dst", f"{client.ipv4}/32",
                                "flowid", class_id
                            ],
                            capture_output=True
                        )

                    # === INGRESS (upload) on ifb0 ===
                    ingress_class = f"2:{client.ip_index}"
                    self._ensure_tc_class(self.IFB_DEVICE, "2:1", ingress_class, rate)
                    if not self._filter_exists(self.IFB_DEVICE, ingress_class):
                        subprocess.run(
                            [
                                "tc", "filter", "add", "dev", self.IFB_DEVICE,
                                "protocol", "ip", "parent", "2:0", "prio", "1",
                                "u32", "match", "ip", "src", f"{client.ipv4}/32",
                                "flowid", ingress_class
                            ],
                            capture_output=True
                        )

                    client.bandwidth_limit = bandwidth_mbps

                self.db.commit()
                logger.info(f"Set bandwidth limit for {client.name}: {bandwidth_mbps} Mbps (local)")
                return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to set bandwidth limit: {e}")
            return False

    @staticmethod
    def _ensure_tc_class(dev: str, parent: str, class_id: str, rate: str):
        """Create or update tc class on device."""
        change = subprocess.run(
            ["tc", "class", "change", "dev", dev,
             "parent", parent, "classid", class_id, "htb",
             "rate", rate, "ceil", rate],
            capture_output=True
        )
        if change.returncode != 0:
            subprocess.run(
                ["tc", "class", "add", "dev", dev,
                 "parent", parent, "classid", class_id, "htb",
                 "rate", rate, "ceil", rate],
                capture_output=True
            )

    @staticmethod
    def _filter_exists(interface: str, class_id: str) -> bool:
        """Check if a tc filter already routes traffic to the given class."""
        try:
            result = subprocess.run(
                ["tc", "filter", "show", "dev", interface],
                capture_output=True, text=True
            )
            return (f"flowid {class_id} " in result.stdout or
                    f"flowid {class_id}\n" in result.stdout or
                    result.stdout.rstrip().endswith(f"flowid {class_id}"))
        except Exception:
            return False

    def _remove_tc_class(self, interface: str, class_id: str) -> None:
        """Remove a TC class and its filters"""
        try:
            # Remove class (this will also remove associated filters)
            subprocess.run(
                ["tc", "class", "del", "dev", interface, "classid", class_id],
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

    # ── Bandwidth verification ────────────────────────────────────────────────

    def verify_bandwidth_applied(self, server_id: int) -> dict:
        """
        Verify that TC bandwidth limits stored in DB are actually applied on the server.

        Supports:
          - Local servers (no ssh_host): subprocess
          - SSH servers: paramiko SSH command
          - Agent servers: skipped (TC state not exposed via agent API)

        Returns dict with keys:
          applied_count, missing_count, mismatches (list),
          skipped (bool, optional), error (str, optional)
        """
        from ..database.models import Server as _Server
        server = self.db.query(_Server).filter(_Server.id == server_id).first()
        if not server:
            return {"error": "server_not_found", "applied_count": 0,
                    "missing_count": 0, "mismatches": []}

        if getattr(server, "server_category", None) == "proxy":
            return {"skipped": True, "reason": "proxy_server",
                    "applied_count": 0, "missing_count": 0, "mismatches": []}

        if getattr(server, "agent_mode", None) == "agent":
            return {"skipped": True, "reason": "agent_server_tc_unverifiable",
                    "applied_count": 0, "missing_count": 0, "mismatches": []}

        clients_with_limit = (
            self.db.query(Client)
            .filter(
                Client.server_id == server_id,
                Client.bandwidth_limit.isnot(None),
                Client.bandwidth_limit > 0,
                Client.public_key.isnot(None),
                Client.enabled == True,
            )
            .all()
        )
        if not clients_with_limit:
            return {"applied_count": 0, "missing_count": 0, "mismatches": []}

        interface = getattr(server, "interface", None) or "wg0"

        try:
            if server.ssh_host:
                tc_output = self._run_ssh_command(
                    server, f"tc class show dev {interface} 2>/dev/null"
                )
            else:
                result = subprocess.run(
                    ["tc", "class", "show", "dev", interface],
                    capture_output=True, text=True, timeout=5,
                )
                tc_output = result.stdout
        except Exception as exc:
            return {
                "error": str(exc),
                "applied_count": 0,
                "missing_count": len(clients_with_limit),
                "mismatches": [],
            }

        import re as _re
        mismatches = []
        applied = 0
        for client in clients_with_limit:
            class_id = f"1:{client.ip_index}"
            if class_id not in tc_output:
                mismatches.append({
                    "client_id": client.id,
                    "name": client.name,
                    "ipv4": client.ipv4,
                    "expected_mbps": client.bandwidth_limit,
                    "reason": "tc_class_missing",
                })
                continue

            # Verify rate: "classid 1:N ... rate XMbit"
            m = _re.search(
                rf"classid\s+{_re.escape(class_id)}\b.*?rate\s+(\d+)(\w+)",
                tc_output,
            )
            if m:
                actual_value = int(m.group(1))
                actual_unit = m.group(2).lower()
                # Normalize to Mbps for comparison
                actual_mbps = actual_value
                if actual_unit in ("kbit", "kbps"):
                    actual_mbps = actual_value / 1000
                elif actual_unit in ("gbit", "gbps"):
                    actual_mbps = actual_value * 1000
                if abs(actual_mbps - client.bandwidth_limit) > 0.5:
                    mismatches.append({
                        "client_id": client.id,
                        "name": client.name,
                        "ipv4": client.ipv4,
                        "expected_mbps": client.bandwidth_limit,
                        "actual_mbps": actual_mbps,
                        "reason": "rate_mismatch",
                    })
                    continue
            applied += 1

        return {
            "applied_count": applied,
            "missing_count": len(mismatches),
            "mismatches": mismatches,
        }

    def _run_ssh_command(self, server, command: str, timeout: int = 10) -> str:
        """Run a command on a remote server via SSH. Returns stdout."""
        import paramiko
        import io as _io

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = None
        if server.ssh_private_key:
            for _cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
                try:
                    pkey = _cls.from_private_key(_io.StringIO(server.ssh_private_key))
                    break
                except Exception:
                    pass
        try:
            client.connect(
                server.ssh_host,
                port=server.ssh_port or 22,
                username=server.ssh_user or "root",
                password=server.ssh_password if not pkey else None,
                pkey=pkey,
                timeout=timeout,
                look_for_keys=False,
            )
            _, stdout, _ = client.exec_command(command, timeout=timeout)
            return stdout.read().decode("utf-8", errors="replace")
        finally:
            try:
                client.close()
            except Exception:
                pass

    def remove_bandwidth_limit(self, client_id: int) -> bool:
        """Remove bandwidth limit for a client"""
        return self.set_bandwidth_limit(client_id, 0)

    @staticmethod
    def _get_local_tc_class_indices(interface: str) -> set:
        """Return set of ip_index values for child HTB classes on a local interface."""
        try:
            result = subprocess.run(
                ["tc", "class", "show", "dev", interface],
                capture_output=True, text=True
            )
            indices = set()
            for line in result.stdout.splitlines():
                m = re.search(r'class htb \d+:(\d+) parent \d+:\d+', line)
                if m:
                    idx = int(m.group(1))
                    if idx != 1:
                        indices.add(idx)
            return indices
        except Exception:
            return set()

    def restore_all_bandwidth_limits(self) -> int:
        """
        Sync bandwidth limits to match DB state on all servers.

        For each server:
        - Applies limits from DB (re-creates TC rules lost on reboot)
        - Removes stale TC rules that exist on the server but not in DB
          (prevents orphaned rules from old systems throttling clients)

        Call on startup. Returns number of limits applied.
        """
        from ..database.models import Server as ServerModel

        servers = self.db.query(ServerModel).all()
        total = 0

        for server in servers:
            if getattr(server, "server_category", None) == "proxy" or getattr(server, "server_type", None) in ("hysteria2", "tuic"):
                logger.info(
                    f"Skipping bandwidth TC restore for proxy server "
                    f"{server.name} ({getattr(server, 'server_type', 'proxy')})"
                )
                continue
            try:
                total += self._sync_bandwidth_for_server(server)
            except Exception as e:
                logger.error(f"Failed to sync bandwidth for server {server.name}: {e}")

        if total > 0:
            logger.info(f"Synced bandwidth limits: {total} active limits across all servers")
        return total

    def _sync_bandwidth_for_server(self, server) -> int:
        """
        Sync bandwidth TC rules for one server to match DB state.
        Returns number of active limits applied.
        """
        if getattr(server, "server_category", None) == "proxy" or getattr(server, "server_type", None) in ("hysteria2", "tuic"):
            logger.info(
                f"Skipping bandwidth sync for proxy server "
                f"{server.name} ({getattr(server, 'server_type', 'proxy')})"
            )
            return 0

        # Build desired state: {ip_index → (ip, limit_mbps)}
        clients = self.db.query(Client).filter(
            Client.server_id == server.id,
            Client.enabled == True,
        ).all()

        desired: dict = {}
        for client in clients:
            effective = None
            if client.bandwidth_limit and client.bandwidth_limit > 0:
                effective = client.bandwidth_limit
            if client.auto_bandwidth_limit and client.auto_bandwidth_limit > 0:
                effective = min(effective, client.auto_bandwidth_limit) if effective else client.auto_bandwidth_limit
            if effective:
                desired[client.ip_index] = {"ip": client.ipv4, "limit_mbps": effective, "ip_index": client.ip_index}

        if server.ssh_host:
            # Remote server — delegate to agent (which handles sync atomically)
            try:
                wg = self._get_wg(server)
                if wg.mode == "agent":
                    limits = list(desired.values())
                    synced = wg.backend.sync_bandwidth(limits)
                    wg.close()
                    if synced:
                        logger.info(f"Bandwidth synced via agent for {server.name}: {len(limits)} limits")
                        return len(limits)
                    # Fallback: agent may not support /bandwidth/sync (old agent)
                    for item in desired.values():
                        wg2 = self._get_wg(server)
                        wg2.backend.set_bandwidth(item["ip"], item["limit_mbps"], item["ip_index"])
                        wg2.close()
                else:
                    wg.close()
            except Exception as e:
                logger.warning(f"Could not sync bandwidth for remote server {server.name}: {e}")
        else:
            # Local server — sync TC rules directly
            interface = server.interface or "wg0"
            try:
                self.setup_bandwidth_qdisc(interface)
                current_indices = self._get_local_tc_class_indices(interface)
                desired_indices = set(desired.keys())

                # Remove stale classes
                stale = current_indices - desired_indices
                for idx in stale:
                    class_id = f"1:{idx}"
                    self._remove_tc_class(interface, class_id)
                    logger.info(f"Removed stale TC class {class_id} on {interface} (not in DB)")

                # Apply desired limits
                for item in desired.values():
                    client_obj = self.db.query(Client).filter(
                        Client.server_id == server.id,
                        Client.ip_index == item["ip_index"]
                    ).first()
                    if client_obj is None:
                        logger.warning(f"Client with ip_index={item['ip_index']} not found on server {server.name}, skipping")
                        continue
                    self.set_bandwidth_limit(
                        client_obj.id,
                        item["limit_mbps"],
                        interface
                    )

                if stale:
                    logger.info(f"Removed {len(stale)} stale TC rules on {server.name} ({interface})")
            except Exception as e:
                logger.error(f"Failed to sync local bandwidth on {server.name}: {e}")

        return len(desired)

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    @staticmethod
    def format_bytes(bytes_count: int) -> str:
        """Format bytes to human-readable string"""
        if bytes_count == 0:
            return "0 B"

        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        size = float(bytes_count)

        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        if unit_index <= 1:
            return f"{int(size)} {units[unit_index]}"
        return f"{size:.2f} {units[unit_index]}"

    @staticmethod
    def parse_size_to_mb(size_str: str) -> int:
        """Parse size string like '5GB' to megabytes"""
        size_str = size_str.upper().strip()

        multipliers = {
            "MB": 1,
            "M": 1,
            "GB": 1024,
            "G": 1024,
            "TB": 1024 * 1024,
            "T": 1024 * 1024,
        }

        for suffix, mult in multipliers.items():
            if size_str.endswith(suffix):
                try:
                    value = float(size_str[:-len(suffix)])
                    return int(value * mult)
                except ValueError:
                    pass

        # Try parsing as plain number (assume MB)
        try:
            return int(size_str)
        except ValueError:
            return 0

    def get_traffic_summary(self, server_id: Optional[int] = None) -> Dict:
        """Get traffic summary for all clients"""
        stats = self.get_all_traffic_stats(server_id)

        total_rx = sum(s.rx_bytes for s in stats)
        total_tx = sum(s.tx_bytes for s in stats)
        total = sum(s.total_bytes for s in stats)

        exceeded_count = sum(1 for s in stats if s.is_exceeded)
        warning_count = sum(1 for s in stats if 80 <= s.percent_used < 100)

        return {
            "total_clients": len(stats),
            "total_rx": total_rx,
            "total_rx_formatted": self.format_bytes(total_rx),
            "total_tx": total_tx,
            "total_tx_formatted": self.format_bytes(total_tx),
            "total": total,
            "total_formatted": self.format_bytes(total),
            "exceeded_count": exceeded_count,
            "warning_count": warning_count,
        }
