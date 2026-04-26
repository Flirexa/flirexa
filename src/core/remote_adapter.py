"""
Remote Server Adapter
Routes commands to SSH (legacy) or Agent (new) based on server.agent_mode
"""

from typing import Optional
from loguru import logger

from .wireguard import WireGuardManager
from .amneziawg import AmneziaWGManager
from .agent_client import AgentClient


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
        if self.mode == "agent" and server.agent_url and server.agent_api_key:
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
            # Agent manages interface via systemd — verify it's actually up
            is_up = self.backend.health_check()
            if is_up:
                return True
            logger.warning("Agent mode: interface not up, cannot start remotely (use systemd on agent server)")
            return False
        else:
            return self.backend.start_interface()

    def stop_interface(self) -> bool:
        """Stop WireGuard interface"""
        if self.mode == "agent":
            logger.warning("Interface stop not supported in agent mode (use systemd on agent server)")
            return False
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
