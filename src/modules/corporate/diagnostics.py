"""
Comprehensive diagnostics for corporate WireGuard VPN networks.

Because the management server is NOT in the WireGuard data path, all checks
are limited to what we can observe from the outside:
  - Config validation  (fields present, keys non-empty)
  - Endpoint DNS resolution + private-IP detection
  - Subnet conflict analysis (across all sites)
  - Peer cross-validation (AllowedIPs logic, split-tunnel compliance)
  - Health status aggregation  (healthy / warning / error / inactive)

Two entry points:
  quick_network_health(network)   – instant, no I/O, safe for list views
  run_network_diagnostics(network) – full check with DNS, slower, on-demand
"""

import ipaddress
import logging
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Status constants ──────────────────────────────────────────────────────────

HEALTH_HEALTHY  = "healthy"
HEALTH_WARNING  = "warning"
HEALTH_ERROR    = "error"
HEALTH_INACTIVE = "inactive"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class PeerDiagnostic:
    """Diagnostic result for a single directed peer link (site → peer)."""
    peer_id:   int
    peer_name: str
    peer_is_relay: bool
    # Endpoint
    peer_has_endpoint:        bool
    peer_endpoint_dns_ok:     bool
    peer_endpoint_resolved_ip: Optional[str]
    # Connectivity posture
    can_initiate_to_peer:    bool   # this site has endpoint OR peer has endpoint
    bidirectional_endpoints: bool   # both sides have endpoints
    # Relay
    uses_relay:    bool             # traffic routed through relay node
    relay_name:    Optional[str]    # name of the relay site, if used
    nat_detected:  bool             # one or both sides behind NAT
    # Route checks
    peer_has_local_subnets:      bool
    allowed_ips_no_default_route: bool  # always True (we generate split-tunnel)
    # Summary
    status: str
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "peer_id":   self.peer_id,
            "peer_name": self.peer_name,
            "peer_is_relay": self.peer_is_relay,
            "peer_has_endpoint":         self.peer_has_endpoint,
            "peer_endpoint_dns_ok":      self.peer_endpoint_dns_ok,
            "peer_endpoint_resolved_ip": self.peer_endpoint_resolved_ip,
            "can_initiate_to_peer":      self.can_initiate_to_peer,
            "bidirectional_endpoints":   self.bidirectional_endpoints,
            "uses_relay":   self.uses_relay,
            "relay_name":   self.relay_name,
            "nat_detected": self.nat_detected,
            "peer_has_local_subnets":    self.peer_has_local_subnets,
            "allowed_ips_no_default_route": self.allowed_ips_no_default_route,
            "status": self.status,
            "issues": self.issues,
        }


@dataclass
class SiteDiagnostic:
    """Diagnostic result for a single site."""
    site_id:   int
    site_name: str
    is_relay:  bool
    status:    str
    vpn_ip:    str
    endpoint:  Optional[str]
    routing_mode: str
    # Endpoint checks
    endpoint_dns_ok:      bool
    endpoint_resolved_ip: Optional[str]
    endpoint_is_private:  bool
    # Config
    has_local_subnets:  bool
    local_subnets:      List[str]
    config_downloaded:  bool
    config_downloaded_at: Optional[str]
    keys_present:       bool
    # Conflicts
    subnet_conflicts: List[str]
    # Relay
    behind_nat: bool   # no public endpoint → likely behind NAT
    # Peers
    peers: List[PeerDiagnostic]
    # Summary
    errors:   List[str]
    warnings: List[str]

    def to_dict(self) -> dict:
        return {
            "site_id":   self.site_id,
            "site_name": self.site_name,
            "is_relay":  self.is_relay,
            "status":    self.status,
            "vpn_ip":    self.vpn_ip,
            "endpoint":  self.endpoint,
            "routing_mode": self.routing_mode,
            "endpoint_dns_ok":      self.endpoint_dns_ok,
            "endpoint_resolved_ip": self.endpoint_resolved_ip,
            "endpoint_is_private":  self.endpoint_is_private,
            "has_local_subnets": self.has_local_subnets,
            "local_subnets":     self.local_subnets,
            "config_downloaded":    self.config_downloaded,
            "config_downloaded_at": self.config_downloaded_at,
            "keys_present":     self.keys_present,
            "subnet_conflicts": self.subnet_conflicts,
            "behind_nat": self.behind_nat,
            "peers":    [p.to_dict() for p in self.peers],
            "errors":   self.errors,
            "warnings": self.warnings,
        }


@dataclass
class NetworkDiagnostic:
    """Aggregated diagnostic result for the full network."""
    network_id:     int
    network_name:   str
    network_status: str
    health:         str
    site_count:        int
    active_site_count: int
    # Relay
    has_relay:       bool
    relay_site_id:   Optional[int]
    relay_site_name: Optional[str]
    # Sites
    sites:    List[SiteDiagnostic]
    errors:   List[str]
    warnings: List[str]
    ran_at:   str

    def to_dict(self) -> dict:
        return {
            "network_id":     self.network_id,
            "network_name":   self.network_name,
            "network_status": self.network_status,
            "health":         self.health,
            "site_count":        self.site_count,
            "active_site_count": self.active_site_count,
            "has_relay":       self.has_relay,
            "relay_site_id":   self.relay_site_id,
            "relay_site_name": self.relay_site_name,
            "sites":    [s.to_dict() for s in self.sites],
            "errors":   self.errors,
            "warnings": self.warnings,
            "ran_at":   self.ran_at,
        }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _resolve_endpoint(endpoint: str) -> Tuple[bool, Optional[str], bool]:
    """
    Try to resolve the host portion of *endpoint* (format: host:port or [v6]:port).
    Returns (dns_ok, resolved_ip_str, is_private_ip).
    """
    try:
        parts = endpoint.rsplit(":", 1)
        host = parts[0].strip("[]")
        port = int(parts[1]) if len(parts) > 1 else 51820
        results = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_DGRAM, 0, socket.AI_CANONNAME)
        if not results:
            return False, None, False
        ip_str = results[0][4][0]
        try:
            is_private = ipaddress.ip_address(ip_str).is_private
        except Exception:
            is_private = False
        return True, ip_str, is_private
    except socket.gaierror:
        return False, None, False
    except Exception as exc:
        logger.debug(f"Endpoint resolution error for {endpoint!r}: {exc}")
        return False, None, False


def _find_subnet_conflicts(
    site_id: int,
    my_subnets: List[ipaddress.IPv4Network],
    all_sites,            # List[CorporateNetworkSite]
) -> List[str]:
    conflicts = []
    for other in all_sites:
        if other.id == site_id or other.status != "active":
            continue
        for raw in other.get_local_subnets():
            try:
                other_net = ipaddress.ip_network(raw, strict=False)
                for my_net in my_subnets:
                    if my_net.overlaps(other_net):
                        conflicts.append(
                            f"Subnet {my_net} conflicts with '{other.name}' subnet {other_net}"
                        )
            except Exception:
                pass
    return conflicts


def _needs_relay_for_pair(site_a, site_b) -> bool:
    """Mirror of CorporateManager._needs_relay_for_pair — local copy for diagnostics."""
    a_mode = (site_a.routing_mode or "auto") if hasattr(site_a, "routing_mode") else "auto"
    b_mode = (site_b.routing_mode or "auto") if hasattr(site_b, "routing_mode") else "auto"
    if a_mode == "direct" and b_mode == "direct":
        return False
    if a_mode == "via_relay" or b_mode == "via_relay":
        return True
    return not site_a.endpoint and not site_b.endpoint


def _diagnose_peer(
    site,                       # CorporateNetworkSite
    peer,                       # CorporateNetworkSite
    with_dns: bool,
    relay_site=None,            # Optional[CorporateNetworkSite]
) -> PeerDiagnostic:
    issues: List[str] = []
    status = HEALTH_HEALTHY

    # ── Relay / NAT analysis ─────────────────────────────────────────────────
    peer_is_relay = relay_site is not None and peer.id == relay_site.id
    nat_detected  = not bool(site.endpoint) or not bool(peer.endpoint)

    uses_relay = False
    relay_name: Optional[str] = None

    if relay_site is not None and relay_site.id != site.id and relay_site.id != peer.id:
        # We have a relay node in this network; check if this pair needs it
        if _needs_relay_for_pair(site, peer):
            uses_relay = True
            relay_name = relay_site.name

    peer_has_endpoint = bool(peer.endpoint)
    peer_dns_ok = False
    peer_resolved_ip: Optional[str] = None
    peer_is_private = False

    if peer_has_endpoint and with_dns:
        peer_dns_ok, peer_resolved_ip, peer_is_private = _resolve_endpoint(peer.endpoint)
        if not peer_dns_ok:
            issues.append(
                f"Peer endpoint '{peer.endpoint}' does not resolve — "
                "check hostname or IP"
            )
            status = HEALTH_ERROR
        elif peer_is_private:
            issues.append(
                f"Peer endpoint resolves to private IP {peer_resolved_ip} — "
                "may not be reachable from remote sites (possible NAT issue)"
            )
            if status == HEALTH_HEALTHY:
                status = HEALTH_WARNING
    elif peer_has_endpoint:
        # quick mode: mark dns_ok as unknown but treat as ok for quick check
        peer_dns_ok = True

    # Both no endpoint → relay required or no connection at all
    can_initiate = bool(site.endpoint) or peer_has_endpoint
    bidirectional = bool(site.endpoint) and peer_has_endpoint

    if not can_initiate:
        if uses_relay and relay_site:
            # Relay saves us — downgrade to warning
            issues.append(
                f"Neither site has a public endpoint — traffic will be routed "
                f"through relay '{relay_name}'"
            )
            if status == HEALTH_HEALTHY:
                status = HEALTH_WARNING
        else:
            issues.append(
                "Neither this site nor the peer has an endpoint and no relay is "
                "available — WireGuard tunnel cannot be established"
            )
            status = HEALTH_ERROR
    elif not peer_has_endpoint and not uses_relay:
        issues.append(
            f"Peer '{peer.name}' has no public endpoint — "
            "this site cannot initiate connection to it"
        )
        if status == HEALTH_HEALTHY:
            status = HEALTH_WARNING
    elif not peer_has_endpoint and uses_relay:
        issues.append(
            f"Peer '{peer.name}' has no public endpoint — "
            f"traffic routed through relay '{relay_name}'"
        )
        if status == HEALTH_HEALTHY:
            status = HEALTH_WARNING

    peer_subnets = peer.get_local_subnets()
    if not peer_subnets:
        issues.append(
            f"Peer '{peer.name}' has no local subnets — "
            "only VPN IP will be routed, no LAN access through the tunnel"
        )
        if status == HEALTH_HEALTHY:
            status = HEALTH_WARNING

    return PeerDiagnostic(
        peer_id=peer.id,
        peer_name=peer.name,
        peer_is_relay=peer_is_relay,
        peer_has_endpoint=peer_has_endpoint,
        peer_endpoint_dns_ok=peer_dns_ok,
        peer_endpoint_resolved_ip=peer_resolved_ip,
        can_initiate_to_peer=can_initiate,
        bidirectional_endpoints=bidirectional,
        uses_relay=uses_relay,
        relay_name=relay_name,
        nat_detected=nat_detected,
        peer_has_local_subnets=bool(peer_subnets),
        allowed_ips_no_default_route=True,  # always split-tunnel in our generator
        status=status,
        issues=issues,
    )


def _diagnose_site(
    site,               # CorporateNetworkSite
    all_sites,          # List[CorporateNetworkSite]
    with_dns: bool,
    relay_site=None,    # Optional[CorporateNetworkSite]
) -> SiteDiagnostic:
    errors:   List[str] = []
    warnings: List[str] = []

    is_relay     = relay_site is not None and site.id == relay_site.id
    routing_mode = (site.routing_mode or "auto") if hasattr(site, "routing_mode") else "auto"
    behind_nat   = not bool(site.endpoint)

    # Inactive / disabled
    if site.status != "active":
        return SiteDiagnostic(
            site_id=site.id,
            site_name=site.name,
            is_relay=is_relay,
            status=HEALTH_INACTIVE,
            vpn_ip=site.vpn_ip,
            endpoint=site.endpoint,
            routing_mode=routing_mode,
            endpoint_dns_ok=False,
            endpoint_resolved_ip=None,
            endpoint_is_private=False,
            has_local_subnets=bool(site.get_local_subnets()),
            local_subnets=site.get_local_subnets(),
            config_downloaded=site.config_downloaded_at is not None,
            config_downloaded_at=(
                site.config_downloaded_at.isoformat() if site.config_downloaded_at else None
            ),
            keys_present=bool(site.private_key and site.public_key),
            subnet_conflicts=[],
            behind_nat=behind_nat,
            peers=[],
            errors=[f"Site is '{site.status}' — disabled by administrator"],
            warnings=[],
        )

    # Keys
    keys_present = bool(site.private_key and site.public_key)
    if not keys_present:
        errors.append("Missing WireGuard keys — regenerate keys for this site")

    # Config download
    if not site.config_downloaded_at:
        warnings.append("Config has not been downloaded yet — site is not deployed")

    # Local subnets
    local_subnets = site.get_local_subnets()
    if not local_subnets:
        warnings.append(
            "No local subnets configured — this site won't advertise any routes to peers"
        )

    # Parse subnets
    my_nets: List[ipaddress.IPv4Network] = []
    for raw in local_subnets:
        try:
            my_nets.append(ipaddress.ip_network(raw, strict=False))
        except Exception:
            errors.append(f"Invalid CIDR notation: '{raw}'")

    # Subnet conflicts
    subnet_conflicts = _find_subnet_conflicts(site.id, my_nets, all_sites)
    errors.extend(subnet_conflicts)

    # Endpoint
    endpoint_dns_ok   = False
    endpoint_resolved_ip: Optional[str] = None
    endpoint_is_private = False

    # Relay-specific checks
    if is_relay and not site.endpoint:
        errors.append(
            "Relay node must have a public endpoint — "
            "without it, NAT'd sites cannot reach the relay"
        )
    elif not site.endpoint:
        if relay_site is not None and not is_relay:
            warnings.append(
                "No public endpoint — outbound only; "
                f"traffic to/from other NAT'd sites will route through relay '{relay_site.name}'"
            )
        else:
            warnings.append(
                "No public endpoint configured — "
                "peer sites cannot initiate connections here (outbound only)"
            )
    if site.endpoint:
        if with_dns:
            endpoint_dns_ok, endpoint_resolved_ip, endpoint_is_private = _resolve_endpoint(
                site.endpoint
            )
            if not endpoint_dns_ok:
                errors.append(
                    f"Endpoint '{site.endpoint}' does not resolve — "
                    "check hostname / IP address"
                )
            elif endpoint_is_private:
                warnings.append(
                    f"Endpoint resolves to private IP {endpoint_resolved_ip} — "
                    "may not be reachable from remote sites (NAT issue?)"
                )
        else:
            # quick mode: no DNS call
            endpoint_dns_ok = True  # optimistic

    # Peer diagnostics
    peers = [
        _diagnose_peer(site, p, with_dns, relay_site=relay_site)
        for p in all_sites
        if p.id != site.id and p.status == "active"
    ]

    peer_error_count   = sum(1 for p in peers if p.status == HEALTH_ERROR)
    peer_warning_count = sum(1 for p in peers if p.status == HEALTH_WARNING)

    if peer_error_count:
        errors.append(
            f"{peer_error_count} peer connection(s) have configuration errors"
        )
    if peer_warning_count:
        warnings.append(
            f"{peer_warning_count} peer connection(s) have warnings"
        )

    if errors:
        status = HEALTH_ERROR
    elif warnings:
        status = HEALTH_WARNING
    else:
        status = HEALTH_HEALTHY

    return SiteDiagnostic(
        site_id=site.id,
        site_name=site.name,
        is_relay=is_relay,
        status=status,
        vpn_ip=site.vpn_ip,
        endpoint=site.endpoint,
        routing_mode=routing_mode,
        endpoint_dns_ok=endpoint_dns_ok,
        endpoint_resolved_ip=endpoint_resolved_ip,
        endpoint_is_private=endpoint_is_private,
        has_local_subnets=bool(local_subnets),
        local_subnets=local_subnets,
        config_downloaded=site.config_downloaded_at is not None,
        config_downloaded_at=(
            site.config_downloaded_at.isoformat() if site.config_downloaded_at else None
        ),
        keys_present=keys_present,
        subnet_conflicts=subnet_conflicts,
        behind_nat=behind_nat,
        peers=peers,
        errors=errors,
        warnings=warnings,
    )


def _aggregate_health(errors: List[str], warnings: List[str]) -> str:
    if errors:
        return HEALTH_ERROR
    if warnings:
        return HEALTH_WARNING
    return HEALTH_HEALTHY


# ── Public API ────────────────────────────────────────────────────────────────

def quick_network_health(network) -> Dict:
    """
    Fast health check — no DNS, no I/O.
    Safe to call for every network in a list view.

    Returns a dict with keys: health, errors, warnings.
    """
    now = datetime.now(timezone.utc)
    errors:   List[str] = []
    warnings: List[str] = []

    if network.status != "active":
        return {
            "health":   HEALTH_INACTIVE,
            "errors":   [f"Network is '{network.status}'"],
            "warnings": [],
        }

    if network.expires_at:
        expires = network.expires_at
        if hasattr(expires, "tzinfo") and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now:
            errors.append(f"Subscription expired on {expires.strftime('%Y-%m-%d')}")

    active_sites = [s for s in network.sites if s.status == "active"]

    if len(network.sites) == 0:
        warnings.append("No sites added yet")
    elif len(active_sites) < 2:
        warnings.append("Needs at least 2 active sites for VPN connectivity")

    if active_sites and not any(s.endpoint for s in active_sites):
        warnings.append("No sites have a public endpoint — add an endpoint to at least one site to enable connections")

    not_downloaded = [s for s in active_sites if not s.config_downloaded_at]
    if not_downloaded:
        warnings.append(
            f"{len(not_downloaded)} site(s) have not downloaded their config"
        )

    # Quick subnet conflict scan
    seen: List[Tuple[str, ipaddress.IPv4Network]] = []
    for site in active_sites:
        for raw in site.get_local_subnets():
            try:
                net = ipaddress.ip_network(raw, strict=False)
                for other_name, other_net in seen:
                    if net.overlaps(other_net):
                        errors.append(f"Subnet conflict: {raw} overlaps with {other_name}")
                seen.append((raw, net))
            except Exception:
                errors.append(f"Invalid subnet in site '{site.name}': {raw}")

    return {
        "health":   _aggregate_health(errors, warnings),
        "errors":   errors,
        "warnings": warnings,
    }


def run_network_diagnostics(network) -> NetworkDiagnostic:
    """
    Full diagnostic run with DNS resolution.
    May take several seconds per site (one DNS call per endpoint).
    """
    now = datetime.now(timezone.utc)
    errors:   List[str] = []
    warnings: List[str] = []

    if network.status != "active":
        return NetworkDiagnostic(
            network_id=network.id,
            network_name=network.name,
            network_status=network.status,
            health=HEALTH_INACTIVE,
            site_count=len(network.sites),
            active_site_count=0,
            sites=[],
            errors=[f"Network is '{network.status}'"],
            warnings=[],
            ran_at=now.isoformat(),
        )

    if network.expires_at:
        expires = network.expires_at
        if hasattr(expires, "tzinfo") and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now:
            errors.append(f"Subscription expired on {expires.strftime('%Y-%m-%d')}")

    active_sites = [s for s in network.sites if s.status == "active"]

    # Find relay site (at most one per network)
    relay_site = next((s for s in active_sites if getattr(s, "is_relay", False)), None)

    if len(network.sites) == 0:
        warnings.append("Network has no sites — add at least 2 to establish connectivity")
    elif len(active_sites) < 2:
        warnings.append("Network needs at least 2 active sites for VPN connectivity")

    nat_sites = [s for s in active_sites if not s.endpoint]
    if active_sites and not any(s.endpoint for s in active_sites):
        warnings.append(
            "No sites have a public endpoint — add an endpoint to at least one site "
            "or designate a relay node so peers can initiate connections"
        )
    elif nat_sites and relay_site is None and len(nat_sites) > 1:
        warnings.append(
            f"{len(nat_sites)} site(s) have no endpoint and no relay is configured — "
            "direct tunnels between these sites will not work"
        )

    site_diagnostics = [
        _diagnose_site(site, network.sites, with_dns=True, relay_site=relay_site)
        for site in network.sites
    ]

    for sd in site_diagnostics:
        if sd.status == HEALTH_ERROR:
            errors.append(f"Site '{sd.site_name}' has errors")
        elif sd.status == HEALTH_WARNING:
            warnings.append(f"Site '{sd.site_name}' has warnings")

    not_downloaded = [s for s in active_sites if not s.config_downloaded_at]
    if not_downloaded:
        names = ", ".join(s.name for s in not_downloaded)
        warnings.append(f"{len(not_downloaded)} site(s) config not downloaded: {names}")

    return NetworkDiagnostic(
        network_id=network.id,
        network_name=network.name,
        network_status=network.status,
        health=_aggregate_health(errors, warnings),
        site_count=len(network.sites),
        active_site_count=len(active_sites),
        has_relay=relay_site is not None,
        relay_site_id=relay_site.id if relay_site else None,
        relay_site_name=relay_site.name if relay_site else None,
        sites=site_diagnostics,
        errors=errors,
        warnings=warnings,
        ran_at=now.isoformat(),
    )
