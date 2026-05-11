"""
Remote Server Adapter
Routes commands to SSH (legacy), Agent (HTTP), or Mikrotik RouterOS REST.
Mode selection is read from `server.agent_mode`.
"""

from typing import Optional
from urllib.parse import urlparse
from loguru import logger

from .wireguard import WireGuardManager
from .amneziawg import AmneziaWGManager
from .agent_client import AgentClient
from .mikrotik import MikrotikWireGuardManager


class RemoteServerAdapter:
    """
    Adapter that routes commands to SSH or Agent HTTP API

    Maintains same interface as WireGuardManager for compatibility
    NO changes needed in ClientManager, TrafficManager, etc.
    """

    def __init__(
        self,
        server,
        interface: str = "wg0",
        config_path: Optional[str] = None
    ):
        """
        Args:
            server: Server model instance
            interface: WireGuard interface name
            config_path: Path to WireGuard config
        """
        self.server = server
        self.interface = interface
        self.config_path = config_path or f"/etc/wireguard/{interface}.conf"

        # Determine mode: "agent" or "ssh" (default)
        self.mode = getattr(server, "agent_mode", "ssh") or "ssh"

        # Determine server type
        is_awg = getattr(server, 'server_type', 'wireguard') == 'amneziawg'

        # Initialize backend
        if self.mode == "mikrotik" and server.agent_url:
            # Mikrotik RouterOS REST API. `agent_url` carries the scheme+host
            # (e.g. "http://142.171.45.138" or "https://router.example.com:443"),
            # `agent_api_key` is "user:password" — picked because the existing
            # Server model already has those two columns and they're encrypted
            # at rest. Avoids a schema migration just for one new mode.
            parsed = urlparse(server.agent_url)
            host = parsed.hostname or server.agent_url
            scheme = parsed.scheme or "http"
            port = parsed.port or (443 if scheme == "https" else 80)
            creds = (server.agent_api_key or "").split(":", 1)
            username = creds[0] if creds[0] else "admin"
            password = creds[1] if len(creds) > 1 else ""
            self.backend = MikrotikWireGuardManager(
                interface=interface,
                host=host,
                port=port,
                scheme=scheme,
                username=username,
                password=password,
            )
            logger.debug(f"RemoteAdapter: using MIKROTIK mode for {server.name}")
        elif self.mode == "agent" and server.agent_url and server.agent_api_key:
            # Use Agent API
            self.backend = AgentClient(server.agent_url, server.agent_api_key)
            logger.debug(f"RemoteAdapter: using AGENT mode for {server.name}")
        elif is_awg:
            # AmneziaWG over SSH
            self.backend = AmneziaWGManager(
                interface=interface,
                config_path=config_path,
                ssh_host=server.ssh_host,
                ssh_port=server.ssh_port or 22,
                ssh_user=server.ssh_user or "root",
                ssh_password=server.ssh_password,
                ssh_private_key=server.ssh_private_key,
                jc=server.awg_jc,
                jmin=server.awg_jmin,
                jmax=server.awg_jmax,
                s1=server.awg_s1,
                s2=server.awg_s2,
                h1=server.awg_h1,
                h2=server.awg_h2,
                h3=server.awg_h3,
                h4=server.awg_h4,
            )
            logger.debug(f"RemoteAdapter: using AWG/SSH mode for {server.name}")
        else:
            # Fallback to SSH (existing code, no changes)
            self.backend = WireGuardManager(
                interface=interface,
                config_path=config_path,
                ssh_host=server.ssh_host,
                ssh_port=server.ssh_port or 22,
                ssh_user=server.ssh_user or "root",
                ssh_password=server.ssh_password,
                ssh_private_key=server.ssh_private_key,
            )
            logger.debug(f"RemoteAdapter: using SSH mode for {server.name}")

    # ========================================================================
    # PEER MANAGEMENT (compatible with WireGuardManager interface)
    # ========================================================================

    def add_peer(
        self,
        public_key: str,
        allowed_ips,
        preshared_key: Optional[str] = None
    ) -> bool:
        """Add peer (routes to SSH or Agent)"""
        if self.mode == "agent":
            # Agent API expects comma-separated string, but callers may pass a list
            if isinstance(allowed_ips, (list, tuple)):
                allowed_ips = ",".join(allowed_ips)
            return self.backend.create_peer(public_key, allowed_ips, preshared_key)
        else:
            return self.backend.add_peer(public_key, allowed_ips, preshared_key)

    def remove_peer(self, public_key: str) -> bool:
        """Remove peer (routes to SSH or Agent)"""
        if self.mode == "agent":
            return self.backend.delete_peer(public_key)
        else:
            return self.backend.remove_peer(public_key)

    # ========================================================================
    # STATS (compatible with WireGuardManager interface)
    # ========================================================================

    def get_interface_info(self) -> Optional[dict]:
        """Get interface info"""
        if self.mode == "agent":
            stats = self.backend.get_stats()
            if stats:
                return {
                    "interface": stats.get("interface"),
                    "is_up": stats.get("is_up"),
                    "peers_count": stats.get("peers_count")
                }
            return None
        else:
            return self.backend.get_interface_info()

    def get_all_peers(self) -> list:
        """Get all peers"""
        if self.mode == "agent":
            stats = self.backend.get_stats()
            if stats and "peers" in stats:
                # Convert agent format to WireGuardManager format
                from dataclasses import dataclass

                @dataclass
                class Peer:
                    public_key: str
                    preshared_key: Optional[str]
                    endpoint: Optional[str]
                    allowed_ips: str
                    latest_handshake: Optional[int]
                    transfer_rx: int
                    transfer_tx: int

                peers = []
                for p in stats["peers"]:
                    peers.append(Peer(
                        public_key=p["public_key"],
                        preshared_key=p.get("preshared_key"),
                        endpoint=p.get("endpoint"),
                        allowed_ips=p["allowed_ips"],
                        latest_handshake=p.get("latest_handshake"),
                        transfer_rx=p["transfer_rx"],
                        transfer_tx=p["transfer_tx"]
                    ))
                return peers
            return []
        else:
            return self.backend.get_all_peers()

    def get_peer_latest_handshake(self, public_key: str):
        """Get latest handshake time for a peer"""
        if self.mode == "agent":
            stats = self.backend.get_stats()
            if stats and "peers" in stats:
                for peer in stats["peers"]:
                    if peer["public_key"] == public_key:
                        ts = peer.get("latest_handshake")
                        if ts:
                            from datetime import datetime, timezone
                            return datetime.fromtimestamp(ts, tz=timezone.utc)
            return None
        else:
            return self.backend.get_peer_latest_handshake(public_key)

    def get_peer_transfer(self, public_key: str) -> tuple[int, int]:
        """Get peer transfer stats"""
        if self.mode == "agent":
            stats = self.backend.get_stats()
            if stats and "peers" in stats:
                for peer in stats["peers"]:
                    if peer["public_key"] == public_key:
                        return peer["transfer_rx"], peer["transfer_tx"]
            return 0, 0
        else:
            return self.backend.get_peer_transfer(public_key)

    def is_interface_up(self) -> bool:
        """Check if interface is up"""
        if self.mode == "agent":
            return self.backend.health_check()
        else:
            return self.backend.is_interface_up()

    # ========================================================================
    # INTERFACE CONTROL (compatible with WireGuardManager interface)
    # ========================================================================

    def start_interface(self) -> bool:
        """Start WireGuard interface"""
        if self.mode == "agent":
            # Try the agent's /interface/up endpoint first (agent ≥ 1.4.0).
            # Falls back to a bare health check for older agents — they
            # already auto-start the interface via systemd, so being healthy
            # is the same as being up.
            if self.backend.start_interface():
                return True
            return self.backend.health_check()
        else:
            return self.backend.start_interface()

    def stop_interface(self) -> bool:
        """Stop WireGuard interface"""
        if self.mode == "agent":
            # agent ≥ 1.4.0 supports /interface/down; older agents 404 on it
            # and we surface that as False so the panel shows a clearer
            # message ("re-bootstrap from panel to enable Stop in agent mode").
            return self.backend.stop_interface()
        else:
            return self.backend.stop_interface()

    # ========================================================================
    # BANDWIDTH LIMITS (new in agent)
    # ========================================================================

    def set_bandwidth_limit(self, ip: str, limit_mbps: int, ip_index: int = 0) -> bool:
        """Set bandwidth limit"""
        if self.mode == "agent":
            return self.backend.set_bandwidth(ip, limit_mbps, ip_index)
        else:
            logger.warning("set_bandwidth_limit not implemented for SSH mode")
            return False

    def remove_bandwidth_limit(self, ip: str, ip_index: int) -> bool:
        """Remove bandwidth limit"""
        if self.mode == "agent":
            return self.backend.set_bandwidth(ip, 0, ip_index, remove=True)
        else:
            logger.warning("remove_bandwidth_limit not implemented for SSH mode")
            return False

    # ========================================================================
    # CONFIG (passthrough to SSH backend)
    # ========================================================================

    def write_config_file(self, content: str) -> bool:
        """Write config file (SSH or Agent mode)"""
        if self.mode == "ssh":
            return self.backend.write_config_file(content)
        else:
            return self.backend.write_config(content)

    def read_config_file(self) -> Optional[str]:
        """Read config file (SSH or Agent mode)"""
        if self.mode == "ssh":
            return self.backend.read_config_file()
        else:
            return self.backend.read_config()

    # ========================================================================
    # KEY GENERATION (passthrough - always local)
    # ========================================================================

    def generate_keypair(self) -> tuple[str, str]:
        """Generate keypair (uses awg for AWG servers, wg otherwise)"""
        is_awg = getattr(self.server, 'server_type', 'wireguard') == 'amneziawg'
        if is_awg:
            return AmneziaWGManager.generate_keypair()
        return WireGuardManager.generate_keypair()

    def generate_preshared_key(self) -> str:
        """Generate preshared key (uses awg for AWG servers, wg otherwise)"""
        is_awg = getattr(self.server, 'server_type', 'wireguard') == 'amneziawg'
        if is_awg:
            return AmneziaWGManager.generate_preshared_key()
        return WireGuardManager.generate_preshared_key()

    # ========================================================================
    # CLOSE
    # ========================================================================

    def close(self):
        """Close connection"""
        self.backend.close()
