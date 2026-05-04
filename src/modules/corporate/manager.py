"""
Corporate VPN business logic:
  - Subnet / IP allocation (10.200.0.0/16 pool)
  - Subnet conflict validation
  - WireGuard key-pair generation
  - Per-site config file generation (split-tunnel full-mesh)
  - Plan-limit enforcement via Plan.features JSON
  - CRUD operations (create / add site / update / delete)
  - Basic endpoint diagnostics
"""

import ipaddress
import json
import logging
import socket
import subprocess
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.modules.corporate.models import (
    CorporateNetwork,
    CorporateNetworkSite,
    CorporateNetworkEvent,
)
from src.modules.corporate import diagnostics as _diag
from src.modules.subscription.subscription_models import (
    ClientPortalSubscription,
    SubscriptionStatus,
    SubscriptionPlan,
)

logger = logging.getLogger(__name__)

# ── Address-space constants ────────────────────────────────────────────────────
# Each corporate network gets its own /24 from 10.200.1.0 … 10.200.254.0
_CORP_SUBNET_FMT = "10.200.{}.0/24"
_MAX_NETWORKS = 254  # 10.200.1.0/24 through 10.200.254.0/24

_LEGACY_CORP_PLAN_LIMITS = {
    "standard": (1, 5),
    "pro": (3, 20),
    "premium": (3, 20),
    "business": (3, 20),
    "enterprise": (10, 100),
    "corporation": (5, 30),
    "corporate": (5, 30),
}


class CorporateManager:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _site_network(self, site: CorporateNetworkSite) -> CorporateNetwork:
        network = site.network
        if network is None:
            network = self.get_network(site.network_id)
        if network is None:
            raise ValueError(f"Corporate network #{site.network_id} not found for site #{site.id}")
        return network

    @staticmethod
    def _normalize_tier(tier: object) -> str:
        if hasattr(tier, "value"):
            tier = tier.value
        return str(tier or "").strip().lower()

    @staticmethod
    def _aware_expiry(sub: ClientPortalSubscription) -> Optional[datetime]:
        expiry = getattr(sub, "expiry_date", None)
        if not expiry:
            return None
        if expiry.tzinfo is None:
            return expiry.replace(tzinfo=timezone.utc)
        return expiry

    def _pick_effective_subscription(self, user_id: int) -> Optional[ClientPortalSubscription]:
        """
        Return the best subscription record for entitlement checks.

        The schema is intended to keep one subscription row per user, but old
        data or manual repairs may leave inconsistent duplicates behind. We
        prefer the currently active record, then the latest-expiring/updated one.
        """
        subs = (
            self.db.query(ClientPortalSubscription)
            .filter(ClientPortalSubscription.user_id == user_id)
            .all()
        )
        if not subs:
            return None

        now = datetime.now(timezone.utc)

        def sort_key(sub: ClientPortalSubscription):
            status_val = sub.status.value if hasattr(sub.status, "value") else str(sub.status)
            expiry = self._aware_expiry(sub)
            is_effectively_active = (
                status_val == SubscriptionStatus.ACTIVE.value
                and (expiry is None or expiry > now)
            )
            updated = getattr(sub, "updated_at", None) or getattr(sub, "created_at", None) or datetime.min
            if isinstance(updated, datetime) and updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            expiry_sort = expiry or datetime.max.replace(tzinfo=timezone.utc)
            return (
                1 if is_effectively_active else 0,
                expiry_sort,
                updated,
                getattr(sub, "id", 0),
            )

        return max(subs, key=sort_key)

    def _get_legacy_plan_limits(self, tier: str) -> Tuple[int, int]:
        return _LEGACY_CORP_PLAN_LIMITS.get(tier, (0, 0))

    @staticmethod
    def _normalize_endpoint(endpoint: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
        """
        Validate and normalize a WireGuard endpoint.

        Expected format: host:port or [ipv6-literal]:port.
        Returns (normalized_endpoint, parsed_port). When *endpoint* is empty,
        returns (None, None).
        """
        if endpoint is None:
            return None, None

        raw = endpoint.strip()
        if not raw:
            return None, None

        host: Optional[str] = None
        port_raw: Optional[str] = None

        if raw.startswith("["):
            if "]" not in raw:
                raise ValueError(
                    "Public endpoint must be in the format host:port or [ipv6]:port."
                )
            host_part, _, tail = raw.partition("]")
            host = host_part[1:].strip()
            if not tail.startswith(":"):
                raise ValueError(
                    "Public endpoint must include an explicit UDP port, e.g. 203.0.113.5:51820."
                )
            port_raw = tail[1:].strip()
        else:
            host, sep, port_raw = raw.rpartition(":")
            if not sep:
                raise ValueError(
                    "Public endpoint must include an explicit UDP port, e.g. 203.0.113.5:51820."
                )
            host = host.strip()
            port_raw = port_raw.strip()

        if not host or not port_raw:
            raise ValueError(
                "Public endpoint must be in the format host:port or [ipv6]:port."
            )
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ValueError("Endpoint port must be a valid integer between 1 and 65535.") from exc
        if port < 1 or port > 65535:
            raise ValueError("Endpoint port must be a valid integer between 1 and 65535.")

        normalized = f"[{host}]:{port}" if ":" in host and not raw.startswith("[") else f"{host if not raw.startswith('[') else f'[{host}]'}:{port}"
        return normalized, port

    def _validate_routing_requirements(
        self,
        network: CorporateNetwork,
        routing_mode: str,
        *,
        site_id: Optional[int] = None,
        is_relay: bool = False,
    ) -> None:
        if is_relay:
            return
        if routing_mode == "via_relay":
            relay = next(
                (
                    s for s in network.sites
                    if s.status == "active" and s.is_relay and (site_id is None or s.id != site_id)
                ),
                None,
            )
            if relay is None:
                raise ValueError(
                    "routing_mode='via_relay' requires an active relay site in this network."
                )

    # ── Subnet & IP allocation ─────────────────────────────────────────────────

    def _allocate_subnet(self) -> str:
        """Return the next free /24 from the corporate pool.
        Uses SELECT FOR UPDATE to prevent concurrent allocations of the same subnet.
        """
        used = {
            n.vpn_subnet
            for n in self.db.query(CorporateNetwork).with_for_update().all()
        }
        for i in range(1, _MAX_NETWORKS + 1):
            candidate = _CORP_SUBNET_FMT.format(i)
            if candidate not in used:
                return candidate
        raise ValueError("No available corporate VPN subnets (pool exhausted)")

    def _allocate_vpn_ip(self, network: CorporateNetwork) -> str:
        """Return the next free host IP inside network.vpn_subnet.
        Uses SELECT FOR UPDATE to prevent concurrent duplicate IP allocations.
        """
        # Lock all sites in this network to prevent concurrent allocation
        locked_sites = (
            self.db.query(CorporateNetworkSite)
            .filter(CorporateNetworkSite.network_id == network.id)
            .with_for_update()
            .all()
        )
        net = ipaddress.ip_network(network.vpn_subnet, strict=False)
        used = {s.vpn_ip for s in locked_sites}
        for host in net.hosts():
            candidate = str(host)
            if candidate not in used:
                return candidate
        raise ValueError(f"No available VPN IPs in subnet {network.vpn_subnet}")

    # ── Subnet conflict validation ─────────────────────────────────────────────

    def _validate_subnets(
        self,
        new_subnets: List[str],
        network: CorporateNetwork,
        exclude_site_id: Optional[int] = None,
    ) -> None:
        """
        Check that *new_subnets* don't overlap with:
          - the VPN tunnel subnet of this network
          - local subnets already claimed by other sites in the network
          - each other
        Raises ValueError with a descriptive message on conflict.
        """
        # Parse and validate each subnet
        parsed: List[ipaddress.IPv4Network] = []
        for raw in new_subnets:
            raw = raw.strip()
            try:
                parsed.append(ipaddress.ip_network(raw, strict=False))
            except ValueError:
                raise ValueError(f"'{raw}' is not a valid CIDR subnet")

        # Must not overlap with the VPN tunnel subnet itself
        vpn_net = ipaddress.ip_network(network.vpn_subnet, strict=False)
        for pn in parsed:
            if pn.overlaps(vpn_net):
                raise ValueError(
                    f"Subnet {pn} overlaps with the VPN tunnel subnet {network.vpn_subnet}"
                )

        # Gather subnets already in use by other sites
        existing: List[ipaddress.IPv4Network] = []
        for site in network.sites:
            if exclude_site_id and site.id == exclude_site_id:
                continue
            for raw in site.get_local_subnets():
                try:
                    existing.append(ipaddress.ip_network(raw, strict=False))
                except ValueError:
                    pass

        for pn in parsed:
            for ex in existing:
                if pn.overlaps(ex):
                    raise ValueError(
                        f"Subnet {pn} conflicts with an existing site subnet {ex}"
                    )

        # Self-overlap check within the new list
        for i, a in enumerate(parsed):
            for b in parsed[i + 1 :]:
                if a.overlaps(b):
                    raise ValueError(f"Subnets {a} and {b} overlap each other")

    # ── WireGuard key-pair generation ─────────────────────────────────────────

    @staticmethod
    def _generate_keypair() -> Tuple[str, str]:
        """Return (private_key, public_key) generated by the system wg binary."""
        priv = subprocess.run(
            ["wg", "genkey"], capture_output=True, text=True, check=True
        ).stdout.strip()
        pub = subprocess.run(
            ["wg", "pubkey"], input=priv, capture_output=True, text=True, check=True
        ).stdout.strip()
        return priv, pub

    # ── WireGuard config generation ───────────────────────────────────────────

    @staticmethod
    def _get_relay_site(network: CorporateNetwork) -> Optional[CorporateNetworkSite]:
        """Return the active relay site for *network*, or None."""
        return next(
            (s for s in network.sites if s.is_relay and s.status == "active"),
            None,
        )

    @staticmethod
    def _needs_relay_for_pair(
        site_a: CorporateNetworkSite,
        site_b: CorporateNetworkSite,
    ) -> bool:
        """
        Return True when direct WireGuard connectivity between *site_a* and
        *site_b* is impossible without a relay.

        Rules:
        - If either side has routing_mode=="via_relay": always use relay.
        - If routing_mode=="direct" on both: never use relay.
        - "auto" (default): relay only when BOTH peers lack a public endpoint
          (neither can initiate a connection to the other).
        """
        a_mode = site_a.routing_mode or "auto"
        b_mode = site_b.routing_mode or "auto"

        if a_mode == "direct" and b_mode == "direct":
            return False
        if a_mode == "via_relay" or b_mode == "via_relay":
            return True
        # auto: relay needed only when neither side has a public endpoint
        return not site_a.endpoint and not site_b.endpoint

    def generate_site_config(self, site: CorporateNetworkSite) -> str:
        """
        Build the WireGuard .conf for *site*.

        Topology:
          • Full-mesh by default (every site is a direct Peer).
          • If a relay node exists in the network, NAT'd pairs (both without
            public endpoints) route through the relay instead of connecting
            directly.  The relay site's config includes ALL peers plus
            a PostUp note about IP forwarding.
          • Split-tunnel: internet traffic stays on the local gateway
            (no 0.0.0.0/0 AllowedIPs anywhere).
        """
        network = self._site_network(site)
        net = ipaddress.ip_network(network.vpn_subnet, strict=False)
        prefix = net.prefixlen
        relay = self._get_relay_site(network)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        iface_name = f"wg-corp-{site.id:02d}"
        lines = [
            "# Corporate VPN — WireGuard site-to-site (split-tunnel)",
            f"# Network  : {network.name}",
            f"# Site     : {site.name}",
            f"# Subnet   : {network.vpn_subnet}",
            f"# Generated: {ts}",
            "#",
            f"# SETUP: save as /etc/wireguard/{iface_name}.conf",
            f"# START: wg-quick up {iface_name}",
            f"# STOP : wg-quick down {iface_name}",
            f"# AUTO : systemctl enable --now wg-quick@{iface_name}",
        ]
        if site.is_relay:
            lines += [
                "#",
                "# *** RELAY / HUB NODE ***",
                "# This site forwards traffic between peers that cannot connect directly.",
                "# You MUST enable IP forwarding on this host:",
                "#   PostUp   = sysctl -w net.ipv4.ip_forward=1",
                "#   PostDown = sysctl -w net.ipv4.ip_forward=0",
                "# Or set it permanently: echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf",
            ]
        lines += [
            "#",
            "# NOTE: Deploy this config on your router/firewall, not on a client device.",
            "# Internet traffic is NOT routed through the VPN — only inter-site traffic.",
            "",
            "[Interface]",
            f"PrivateKey = {site.private_key}",
            f"Address    = {site.vpn_ip}/{prefix}",
        ]
        local_advertised = site.get_local_subnets()
        if local_advertised:
            lines.extend(
                [
                    "#",
                    "# This site advertises these local networks to other sites:",
                    f"#   {', '.join(local_advertised)}",
                ]
            )
        else:
            lines.extend(
                [
                    "#",
                    "# This site does not advertise any local LAN subnets yet.",
                    "# Add local subnets in the portal if this router should expose a branch LAN.",
                ]
            )
        lines.append(f"ListenPort = {site.listen_port}")
        lines.append("")

        other_active = [
            s for s in network.sites if s.id != site.id and s.status == "active"
        ]

        if not other_active:
            lines.append("# No other active sites yet — re-download after adding sites.")
            return "\n".join(lines)

        # ── Relay site: add ALL peers directly ────────────────────────────────
        if site.is_relay:
            for peer in other_active:
                peer_subnets = peer.get_local_subnets()
                allowed = [f"{peer.vpn_ip}/32"] + peer_subnets
                lines.append(f"[Peer]  # {peer.name}")
                lines.append(f"PublicKey  = {peer.public_key}")
                lines.append(f"AllowedIPs = {', '.join(allowed)}")
                if peer.endpoint:
                    lines.append(f"Endpoint   = {peer.endpoint}")
                lines.append("PersistentKeepalive = 25")
                lines.append("")
            return "\n".join(lines)

        # ── Regular site: direct peers + relay peers ──────────────────────────
        direct_peers: List[CorporateNetworkSite] = []
        relay_peers:  List[CorporateNetworkSite] = []  # route through relay

        for peer in other_active:
            if peer.is_relay:
                continue  # relay handled separately below
            if relay and self._needs_relay_for_pair(site, peer):
                relay_peers.append(peer)
            else:
                direct_peers.append(peer)

        # Direct peer entries
        for peer in direct_peers:
            peer_subnets = peer.get_local_subnets()
            allowed = [f"{peer.vpn_ip}/32"] + peer_subnets
            if peer_subnets:
                lines.append(f"# Reach via direct peer '{peer.name}': {', '.join(peer_subnets)}")
            else:
                lines.append(f"# Direct peer '{peer.name}' carries only its tunnel IP.")
            lines.append(f"[Peer]  # {peer.name} (direct)")
            lines.append(f"PublicKey  = {peer.public_key}")
            lines.append(f"AllowedIPs = {', '.join(allowed)}")
            if peer.endpoint:
                lines.append(f"Endpoint   = {peer.endpoint}")
            lines.append("PersistentKeepalive = 25")
            lines.append("")

        # Relay peer entry (aggregates relay node's own IP + all relay'd peers)
        if relay and (relay_peers or site.routing_mode == "via_relay"):
            relay_allowed: List[str] = [f"{relay.vpn_ip}/32"]
            relayed_names: List[str] = []
            for rp in relay_peers:
                relay_allowed.append(f"{rp.vpn_ip}/32")
                relay_allowed.extend(rp.get_local_subnets())
                relayed_names.append(rp.name)
            via_comment = f" + via-relay: {', '.join(relayed_names)}" if relayed_names else ""
            if relayed_names:
                lines.append(
                    f"# Reach via relay '{relay.name}': {', '.join(relayed_names)}"
                )
            lines.append(f"[Peer]  # {relay.name} (RELAY{via_comment})")
            lines.append(f"PublicKey  = {relay.public_key}")
            lines.append(f"AllowedIPs = {', '.join(relay_allowed)}")
            if relay.endpoint:
                lines.append(f"Endpoint   = {relay.endpoint}")
            elif not relay.endpoint:
                lines.append("# WARNING: relay has no public endpoint — cannot connect to relay")
            lines.append("PersistentKeepalive = 25")
            lines.append("")

        elif relay and not direct_peers and not relay_peers:
            # relay exists but this site has no need for it (all direct)
            relay_allowed = [f"{relay.vpn_ip}/32"]
            lines.append(f"[Peer]  # {relay.name} (relay — standby)")
            lines.append(f"PublicKey  = {relay.public_key}")
            lines.append(f"AllowedIPs = {', '.join(relay_allowed)}")
            if relay.endpoint:
                lines.append(f"Endpoint   = {relay.endpoint}")
            lines.append("PersistentKeepalive = 25")
            lines.append("")

        return "\n".join(lines)

    # ── Plan-limit enforcement ─────────────────────────────────────────────────

    def _get_corp_limits(self, user_id: int) -> Tuple[int, int]:
        """
        Return (max_networks, max_sites_per_network) from the user's active
        subscription plan.  Returns (0, 0) when the plan does not include
        corporate VPN or there is no active subscription.
        """
        sub = self._pick_effective_subscription(user_id)
        if not sub:
            return 0, 0

        # Accept enum or string value for status
        status_val = sub.status.value if hasattr(sub.status, "value") else sub.status
        if status_val != SubscriptionStatus.ACTIVE.value:
            return 0, 0

        expiry = self._aware_expiry(sub)
        if expiry and expiry <= datetime.now(timezone.utc):
            return 0, 0

        tier = self._normalize_tier(sub.tier)
        legacy_networks, legacy_sites = self._get_legacy_plan_limits(tier)

        # Primary: look up SubscriptionPlan (admin-managed tariffs with features JSON)
        # Use case-insensitive match to handle mixed-case tier names (e.g. "Corporation" vs "corporation")
        from sqlalchemy import func as _func
        sp = self.db.query(SubscriptionPlan).filter(
            _func.lower(SubscriptionPlan.tier) == tier.lower()
        ).first()
        if sp and sp.features:
            f = sp.features
            max_networks = int(f.get("corp_networks", legacy_networks or 0))
            if max_networks <= 0:
                return 0, 0
            max_sites = int(f.get("corp_sites", legacy_sites or 5))
            return max_networks, max_sites

        return legacy_networks, legacy_sites

    # ── CRUD — networks ────────────────────────────────────────────────────────

    def get_user_networks(self, user_id: int) -> List[CorporateNetwork]:
        return (
            self.db.query(CorporateNetwork)
            .filter(CorporateNetwork.user_id == user_id)
            .order_by(CorporateNetwork.created_at.desc())
            .all()
        )

    def get_network(
        self, network_id: int, user_id: Optional[int] = None
    ) -> Optional[CorporateNetwork]:
        q = self.db.query(CorporateNetwork).filter(CorporateNetwork.id == network_id)
        if user_id is not None:
            q = q.filter(CorporateNetwork.user_id == user_id)
        return q.first()

    def create_network(self, user_id: int, name: str) -> CorporateNetwork:
        max_nets, _ = self._get_corp_limits(user_id)
        if max_nets == 0:
            raise PermissionError(
                "Your subscription plan does not include corporate VPN networks. "
                "Upgrade your plan to access this feature."
            )

        existing_count = (
            self.db.query(CorporateNetwork)
            .filter(
                CorporateNetwork.user_id == user_id,
                CorporateNetwork.status != "expired",
            )
            .count()
        )
        if existing_count >= max_nets:
            raise PermissionError(
                f"Network limit reached: your plan allows {max_nets} network(s)."
            )

        subnet = self._allocate_subnet()
        now = datetime.now(timezone.utc)

        # Inherit expiry from subscription
        sub = self._pick_effective_subscription(user_id)
        tier = None
        expires_at = None
        if sub:
            expires_at = sub.expiry_date
            tier = sub.tier.value if hasattr(sub.tier, "value") else sub.tier

        network = CorporateNetwork(
            user_id=user_id,
            name=name.strip(),
            vpn_subnet=subnet,
            status="active",
            subscription_tier=tier,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        self.db.add(network)
        self.db.flush()  # populate network.id before adding sites
        self._log_event(
            network_id=network.id,
            event_type="network_created",
            description=f"Network '{name}' created (subnet {subnet})",
        )
        logger.info(f"Created corporate network #{network.id} '{name}' for user {user_id} — subnet {subnet}")
        return network

    # ── CRUD — sites ───────────────────────────────────────────────────────────

    def _auto_name(self, network: CorporateNetwork) -> str:
        """Generate unique site name: 'Site 1', 'Site 2', …"""
        existing = {s.name for s in network.sites}
        i = 1
        while True:
            candidate = f"Site {i}"
            if candidate not in existing:
                return candidate
            i += 1

    def _auto_port(self, user_id: int) -> int:
        """Pick the first free listen port (51820–52820) across all user's sites."""
        used_ports = set()
        user_networks = self.db.query(CorporateNetwork).filter_by(user_id=user_id).all()
        for net in user_networks:
            for s in net.sites:
                used_ports.add(s.listen_port)
        for port in range(51820, 52821):
            if port not in used_ports:
                return port
        return 51820  # fallback

    def add_site(
        self,
        network: CorporateNetwork,
        name: Optional[str] = None,
        local_subnets: Optional[List[str]] = None,
        endpoint: Optional[str] = None,
        listen_port: Optional[int] = None,
        is_relay: bool = False,
        routing_mode: str = "auto",
    ) -> CorporateNetworkSite:
        _, max_sites = self._get_corp_limits(network.user_id)
        active_count = sum(1 for s in network.sites if s.status == "active")
        if active_count >= max_sites:
            raise PermissionError(
                f"Site limit reached: your plan allows {max_sites} sites per network."
            )

        # Auto-fill name and port if not provided
        if not name or not name.strip():
            name = self._auto_name(network)
        else:
            name = name.strip()
        endpoint, endpoint_port = self._normalize_endpoint(endpoint)
        if listen_port is None:
            listen_port = endpoint_port or self._auto_port(network.user_id)
        elif endpoint_port is not None and listen_port != endpoint_port:
            raise ValueError(
                "Listen port must match the port embedded in the public endpoint."
            )

        if local_subnets:
            self._validate_subnets(local_subnets, network)

        # Relay validation
        routing_mode = routing_mode or "auto"
        if routing_mode not in ("auto", "direct", "via_relay"):
            routing_mode = "auto"
        self._validate_routing_requirements(network, routing_mode, is_relay=is_relay)
        if is_relay:
            self._validate_relay_promotion(network, candidate_endpoint=endpoint, exclude_site_id=None)

        vpn_ip = self._allocate_vpn_ip(network)
        private_key, public_key = self._generate_keypair()
        now = datetime.now(timezone.utc)

        site = CorporateNetworkSite(
            network=network,
            network_id=network.id,
            name=name,
            private_key=private_key,
            public_key=public_key,
            vpn_ip=vpn_ip,
            local_subnets=json.dumps(local_subnets) if local_subnets else None,
            endpoint=endpoint,
            listen_port=listen_port,
            status="active",
            is_relay=is_relay,
            routing_mode=routing_mode,
            created_at=now,
            updated_at=now,
        )
        self.db.add(site)
        self._log_event(
            network_id=network.id,
            event_type="site_created",
            description=f"Site '{name}' added (VPN IP: {vpn_ip})",
            site_name=name,
        )
        logger.info(f"Added site '{name}' (vpn_ip={vpn_ip}) to network #{network.id}")
        return site

    def update_site(
        self,
        site: CorporateNetworkSite,
        name: Optional[str] = None,
        local_subnets: Optional[List[str]] = None,
        endpoint: Optional[str] = None,
        listen_port: Optional[int] = None,
        is_relay: Optional[bool] = None,
        routing_mode: Optional[str] = None,
    ) -> CorporateNetworkSite:
        site_network = self._site_network(site)
        next_name = site.name
        if name is not None:
            next_name = name.strip()

        effective_is_relay = site.is_relay if is_relay is None else is_relay
        effective_routing_mode = site.routing_mode if routing_mode is None else routing_mode
        next_endpoint = site.endpoint
        if name is not None:
            site.name = next_name
        if endpoint is not None:
            next_endpoint, endpoint_port = self._normalize_endpoint(endpoint)
            if not next_endpoint and effective_is_relay:
                raise ValueError(
                    "Cannot remove the endpoint from a relay node — relay requires a public "
                    "endpoint so that NAT'd peers can connect to it. "
                    "Demote the relay role first (is_relay=false), then clear the endpoint."
                )
            next_listen_port = listen_port if listen_port is not None else site.listen_port
            if endpoint_port is not None and next_listen_port != endpoint_port:
                raise ValueError(
                    "Listen port must match the port embedded in the public endpoint."
                )
            site.endpoint = next_endpoint
        if listen_port is not None:
            if next_endpoint:
                _, endpoint_port = self._normalize_endpoint(next_endpoint)
                if endpoint_port is not None and listen_port != endpoint_port:
                    raise ValueError(
                        "Listen port must match the port embedded in the public endpoint."
                    )
            site.listen_port = listen_port
        if local_subnets is not None:
            self._validate_subnets(local_subnets, site_network, exclude_site_id=site.id)
            site.local_subnets = json.dumps(local_subnets)
        if effective_routing_mode not in ("auto", "direct", "via_relay"):
            raise ValueError(
                f"Invalid routing_mode '{effective_routing_mode}'. Use: auto, direct, via_relay"
            )
        self._validate_routing_requirements(
            site_network,
            effective_routing_mode,
            site_id=site.id,
            is_relay=effective_is_relay,
        )
        if routing_mode is not None:
            site.routing_mode = effective_routing_mode
        if is_relay is not None and is_relay != site.is_relay:
            self.set_site_relay_status(site, is_relay)
        site.updated_at = datetime.now(timezone.utc)
        return site

    def set_site_relay_status(self, site: CorporateNetworkSite, is_relay: bool) -> None:
        """Promote or demote a site to/from relay role."""
        network = self._site_network(site)
        if is_relay:
            self._validate_relay_promotion(
                network, candidate_endpoint=site.endpoint, exclude_site_id=site.id
            )
        else:
            # Demotion: check that no other active sites depend on this relay
            dependent = [
                s for s in network.sites
                if s.id != site.id
                and s.status == "active"
                and (s.routing_mode == "via_relay")
            ]
            if dependent:
                names = ", ".join(f"'{s.name}'" for s in dependent)
                raise ValueError(
                    f"Cannot demote relay: site(s) {names} are configured to route via relay "
                    "(routing_mode='via_relay'). Change their routing_mode to 'auto' or 'direct' first."
                )
        site.is_relay = is_relay
        site.updated_at = datetime.now(timezone.utc)
        action = "promoted to RELAY" if is_relay else "demoted from RELAY"
        self._log_event(
            network_id=site.network_id,
            event_type="relay_changed",
            description=f"Site '{site.name}' {action} — re-download configs for all sites",
            site_id=site.id,
            site_name=site.name,
            severity="warning",
        )
        logger.info(f"Site #{site.id} '{site.name}' {action} in network #{site.network_id}")

    def _validate_relay_promotion(
        self,
        network: CorporateNetwork,
        candidate_endpoint: Optional[str],
        exclude_site_id: Optional[int],
    ) -> None:
        """Validate that a site can become a relay node."""
        if not candidate_endpoint:
            raise ValueError(
                "A relay node must have a public endpoint (IP:port) so that "
                "NAT'd peers can connect to it."
            )
        # Enforce one relay per network (simplest topology)
        existing_relay = next(
            (
                s for s in network.sites
                if s.is_relay and s.status == "active"
                and (exclude_site_id is None or s.id != exclude_site_id)
            ),
            None,
        )
        if existing_relay:
            raise ValueError(
                f"Network already has a relay node: '{existing_relay.name}'. "
                "Remove the existing relay before setting a new one."
            )

    def get_relay_topology(self, network: CorporateNetwork) -> dict:
        """
        Return a relay topology summary: which site is relay, which pairs
        use relay, and which are direct.
        """
        relay = self._get_relay_site(network)
        active = [s for s in network.sites if s.status == "active"]
        direct_pairs = []
        relay_pairs = []
        for i, a in enumerate(active):
            for b in active[i + 1:]:
                if a.is_relay or b.is_relay:
                    continue
                if relay and self._needs_relay_for_pair(a, b):
                    relay_pairs.append({"site_a": a.name, "site_b": b.name,
                                        "site_a_id": a.id, "site_b_id": b.id})
                else:
                    direct_pairs.append({"site_a": a.name, "site_b": b.name,
                                         "site_a_id": a.id, "site_b_id": b.id})
        return {
            "relay_site": {
                "id": relay.id,
                "name": relay.name,
                "vpn_ip": relay.vpn_ip,
                "endpoint": relay.endpoint,
                "status": relay.status,
            } if relay else None,
            "has_relay": relay is not None,
            "direct_pairs": direct_pairs,
            "relay_pairs": relay_pairs,
            "nat_sites": [
                {"id": s.id, "name": s.name, "vpn_ip": s.vpn_ip}
                for s in active
                if not s.endpoint and not s.is_relay
            ],
        }

    def regenerate_site_keys(self, site: CorporateNetworkSite) -> CorporateNetworkSite:
        """Replace the key pair for *site*.  All peer configs must be re-downloaded."""
        priv, pub = self._generate_keypair()
        site.private_key = priv
        site.public_key = pub
        site.updated_at = datetime.now(timezone.utc)
        self._log_event(
            network_id=site.network_id,
            event_type="keys_regenerated",
            description=f"WireGuard keys regenerated for site '{site.name}' — all configs must be re-downloaded",
            site_id=site.id,
            site_name=site.name,
            severity="warning",
        )
        logger.info(f"Regenerated keys for site #{site.id} '{site.name}'")
        return site

    def mark_config_downloaded(self, site: CorporateNetworkSite) -> None:
        site.config_downloaded_at = datetime.now(timezone.utc)
        self._log_event(
            network_id=site.network_id,
            event_type="config_downloaded",
            description=f"WireGuard config downloaded for site '{site.name}'",
            site_id=site.id,
            site_name=site.name,
        )

    def delete_site(self, site: CorporateNetworkSite) -> None:
        logger.info(f"Deleting site #{site.id} '{site.name}' from network #{site.network_id}")
        self._log_event(
            network_id=site.network_id,
            event_type="site_deleted",
            description=f"Site '{site.name}' (VPN IP: {site.vpn_ip}) deleted",
            site_name=site.name,
            severity="warning",
        )
        self.db.delete(site)

    def delete_network(self, network: CorporateNetwork) -> None:
        logger.info(f"Deleting corporate network #{network.id} '{network.name}' (user {network.user_id})")
        self.db.delete(network)

    # ── Diagnostics ────────────────────────────────────────────────────────────

    def get_quick_health(self, network: CorporateNetwork) -> dict:
        """Fast health check — no DNS, no I/O. Safe for list views."""
        return _diag.quick_network_health(network)

    def run_full_diagnostics(self, network: CorporateNetwork) -> dict:
        """
        Full diagnostics with DNS resolution.
        Logs a 'diagnostics_run' event and returns the result as a plain dict.
        """
        result = _diag.run_network_diagnostics(network)
        severity = "info" if result.health == "healthy" else result.health
        self._log_event(
            network_id=network.id,
            event_type="diagnostics_run",
            description=(
                f"Diagnostics: {result.health.upper()} — "
                f"{len(result.errors)} error(s), {len(result.warnings)} warning(s)"
            ),
            severity=severity if severity in ("info", "warning", "error") else "info",
        )
        return result.to_dict()

    # Kept for backwards compatibility (old route still calls this)
    def diagnose_network(self, network: CorporateNetwork) -> List[dict]:
        result = _diag.run_network_diagnostics(network)
        return [s.to_dict() for s in result.sites]

    # ── Event log ──────────────────────────────────────────────────────────────

    def _log_event(
        self,
        network_id: int,
        event_type: str,
        description: str,
        site_id: Optional[int] = None,
        site_name: Optional[str] = None,
        severity: str = "info",
    ) -> None:
        try:
            ev = CorporateNetworkEvent(
                network_id=network_id,
                site_id=site_id,
                site_name=site_name,
                event_type=event_type,
                description=description,
                severity=severity,
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(ev)
            # Don't flush/commit here — caller controls the transaction
        except Exception as exc:
            logger.warning(f"Could not write corp event log: {exc}")

    def get_event_log(
        self,
        network_id: int,
        limit: int = 50,
    ) -> List[CorporateNetworkEvent]:
        return (
            self.db.query(CorporateNetworkEvent)
            .filter(CorporateNetworkEvent.network_id == network_id)
            .order_by(CorporateNetworkEvent.created_at.desc())
            .limit(limit)
            .all()
        )

    # ── Admin helpers ──────────────────────────────────────────────────────────

    def get_all_networks(
        self,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> List[CorporateNetwork]:
        q = self.db.query(CorporateNetwork)
        if status:
            q = q.filter(CorporateNetwork.status == status)
        if user_id:
            q = q.filter(CorporateNetwork.user_id == user_id)
        return q.order_by(CorporateNetwork.created_at.desc()).offset(skip).limit(limit).all()

    def set_network_status(self, network: CorporateNetwork, status: str) -> None:
        network.status = status
        network.updated_at = datetime.now(timezone.utc)
        self._log_event(
            network_id=network.id,
            event_type="status_changed",
            description=f"Network status changed to '{status}' by administrator",
            severity="warning" if status != "active" else "info",
        )
        logger.info(f"Admin: set network #{network.id} status → {status}")

    def set_site_status(self, site: CorporateNetworkSite, status: str) -> None:
        site.status = status
        site.updated_at = datetime.now(timezone.utc)
        self._log_event(
            network_id=site.network_id,
            event_type="status_changed",
            description=f"Site '{site.name}' status changed to '{status}' by administrator",
            site_id=site.id,
            site_name=site.name,
            severity="warning" if status != "active" else "info",
        )
        logger.info(f"Admin: set site #{site.id} status → {status}")
