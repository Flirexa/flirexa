"""
VPN Management Studio AmneziaWG Manager
Obfuscated WireGuard using amneziawg kernel module + awg/awg-quick tools.

All commands use `awg` / `awg-quick` instead of `wg` / `wg-quick`.
Obfuscation parameters (Jc, Jmin, Jmax, S1, S2, H1-H4) are stored on
the Server model and embedded into both server and client configs.
"""

import os
import subprocess
from typing import Optional, Tuple, Dict, List

from loguru import logger

from .wireguard import WireGuardManager, PeerInfo


AWG_DEFAULT_MTU = 1280  # Safe MTU for AmneziaWG (avoids fragmentation on most networks)


class AmneziaWGManager(WireGuardManager):
    """
    Manages AmneziaWG interface operations.

    Inherits WireGuardManager's SSH transport (_run_cmd, _get_ssh, etc.)
    and overrides every command that uses `wg` / `wg-quick` to use the
    amneziawg equivalents instead.

    Obfuscation params are passed at construction so generate_client_config
    can embed them without extra arguments at each call site.
    """

    def __init__(
        self,
        interface: str = "awg0",
        config_path: str = "/etc/amneziawg/awg0.conf",
        ssh_host: Optional[str] = None,
        ssh_port: int = 22,
        ssh_user: str = "root",
        ssh_password: Optional[str] = None,
        ssh_private_key: Optional[str] = None,
        # Obfuscation parameters (from Server model)
        jc: int = 4,
        jmin: int = 50,
        jmax: int = 100,
        s1: int = 80,
        s2: int = 40,
        h1: int = 0,
        h2: int = 0,
        h3: int = 0,
        h4: int = 0,
    ):
        super().__init__(
            interface=interface,
            config_path=config_path,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            ssh_password=ssh_password,
            ssh_private_key=ssh_private_key,
        )
        self.jc = jc
        self.jmin = jmin
        self.jmax = jmax
        self.s1 = s1
        self.s2 = s2
        self.h1 = h1
        self.h2 = h2
        self.h3 = h3
        self.h4 = h4

    # ── Key generation ────────────────────────────────────────────────────────

    _AWG_MISSING_HINT = (
        "amneziawg-tools is not installed on this server. AmneziaWG is a "
        "FREE-tier protocol but requires the userspace tools. Install with: "
        "sudo add-apt-repository ppa:amnezia/ppa && "
        "sudo apt install amneziawg amneziawg-tools amneziawg-dkms"
    )

    @staticmethod
    def generate_private_key() -> str:
        try:
            result = subprocess.run(
                ["awg", "genkey"], capture_output=True, text=True, check=True
            )
        except FileNotFoundError:
            raise RuntimeError(AmneziaWGManager._AWG_MISSING_HINT) from None
        return result.stdout.strip()

    @staticmethod
    def generate_public_key(private_key: str) -> str:
        try:
            result = subprocess.run(
                ["awg", "pubkey"], input=private_key,
                capture_output=True, text=True, check=True
            )
        except FileNotFoundError:
            raise RuntimeError(AmneziaWGManager._AWG_MISSING_HINT) from None
        return result.stdout.strip()

    @staticmethod
    def generate_keypair() -> Tuple[str, str]:
        priv = AmneziaWGManager.generate_private_key()
        pub = AmneziaWGManager.generate_public_key(priv)
        return priv, pub

    @staticmethod
    def generate_preshared_key() -> str:
        try:
            result = subprocess.run(
                ["awg", "genpsk"], capture_output=True, text=True, check=True
            )
        except FileNotFoundError:
            raise RuntimeError(AmneziaWGManager._AWG_MISSING_HINT) from None
        return result.stdout.strip()

    @staticmethod
    def generate_obfuscation_params() -> dict:
        """Generate secure random H1-H4 obfuscation headers (unique uint32 each)."""
        values: List[int] = []
        seen: set = set()
        while len(values) < 4:
            v = int.from_bytes(os.urandom(4), "big")
            v = max(1, v)  # never zero
            if v not in seen:
                values.append(v)
                seen.add(v)
        return {
            "jc": 4,
            "jmin": 50,
            "jmax": 100,
            "s1": 80,
            "s2": 40,
            "h1": values[0],
            "h2": values[1],
            "h3": values[2],
            "h4": values[3],
        }

    # ── Interface operations ──────────────────────────────────────────────────

    def is_interface_up(self) -> bool:
        try:
            result = self._run_cmd(["awg", "show", self.interface], check=False)
            return result.returncode == 0
        except Exception:
            return False

    def start_interface(self) -> bool:
        if self.is_interface_up():
            logger.info(f"[AWG] Interface {self.interface} already up")
            return True
        try:
            self._run_cmd(["awg-quick", "up", self.interface])
            logger.info(f"[AWG] Started interface {self.interface}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"[AWG] Failed to start interface: {e.stderr}")
            return False

    def stop_interface(self) -> bool:
        try:
            self._run_cmd(["awg-quick", "down", self.interface])
            logger.info(f"[AWG] Stopped interface {self.interface}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"[AWG] Failed to stop interface: {e.stderr}")
            return False

    def restart_interface(self) -> bool:
        self.stop_interface()
        return self.start_interface()

    def save_config(self) -> bool:
        try:
            self._run_cmd(["awg-quick", "save", self.interface])
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"[AWG] Failed to save config: {e.stderr}")
            return False

    # ── Peer operations ───────────────────────────────────────────────────────

    def add_peer(
        self,
        public_key: str,
        allowed_ips: List[str],
        preshared_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        persistent_keepalive: Optional[int] = None,
    ) -> bool:
        try:
            cmd = [
                "awg", "set", self.interface,
                "peer", public_key,
                "allowed-ips", ",".join(allowed_ips),
            ]
            if endpoint:
                cmd.extend(["endpoint", endpoint])
            if persistent_keepalive:
                cmd.extend(["persistent-keepalive", str(persistent_keepalive)])
            if preshared_key:
                cmd.extend(["preshared-key", "/dev/stdin"])
                self._run_cmd(cmd, input=preshared_key)
            else:
                self._run_cmd(cmd)
            self.save_config()
            logger.info(f"[AWG] Added peer {public_key[:16]}... IPs={allowed_ips}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"[AWG] Failed to add peer: {e}")
            return False

    def remove_peer(self, public_key: str) -> bool:
        try:
            self._run_cmd(["awg", "set", self.interface, "peer", public_key, "remove"])
            self.save_config()
            logger.info(f"[AWG] Removed peer {public_key[:16]}...")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"[AWG] Failed to remove peer: {e}")
            return False

    def update_peer_allowed_ips(self, public_key: str, allowed_ips: List[str]) -> bool:
        try:
            self._run_cmd([
                "awg", "set", self.interface,
                "peer", public_key,
                "allowed-ips", ",".join(allowed_ips),
            ])
            self.save_config()
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"[AWG] Failed to update peer allowed IPs: {e}")
            return False

    # ── Status & monitoring ───────────────────────────────────────────────────

    def get_interface_info(self) -> Optional[Dict]:
        try:
            result = self._run_cmd(["awg", "show", self.interface])
            info = {
                "interface": self.interface,
                "type": "amneziawg",
                "public_key": None,
                "private_key": "(hidden)",
                "listening_port": None,
                "peers_count": 0,
            }
            for line in result.stdout.strip().split("\n"):
                if "public key:" in line:
                    info["public_key"] = line.split(":", 1)[1].strip()
                elif "listening port:" in line:
                    info["listening_port"] = int(line.split(":", 1)[1].strip())
                elif line.startswith("peer:"):
                    info["peers_count"] += 1
            return info
        except subprocess.CalledProcessError:
            return None

    def get_all_peers(self) -> List[PeerInfo]:
        peers = []
        try:
            result = self._run_cmd(["awg", "show", self.interface, "dump"])
            from datetime import datetime, timezone
            for line in result.stdout.strip().split("\n")[1:]:
                parts = line.split("\t")
                if len(parts) >= 8:
                    ts = int(parts[4]) if parts[4] != "0" else 0
                    peer = PeerInfo(
                        public_key=parts[0],
                        preshared_key=parts[1] != "(none)",
                        endpoint=parts[2] if parts[2] != "(none)" else None,
                        allowed_ips=parts[3].split(",") if parts[3] else [],
                        latest_handshake=datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None,
                        transfer_rx=int(parts[5]),
                        transfer_tx=int(parts[6]),
                        persistent_keepalive=int(parts[7]) if parts[7] != "off" else None,
                    )
                    peers.append(peer)
        except subprocess.CalledProcessError as e:
            logger.error(f"[AWG] Failed to get peers: {e}")
        return peers

    def get_peer_transfer(self, public_key: str) -> Tuple[int, int]:
        try:
            result = self._run_cmd(["awg", "show", self.interface, "transfer"])
            for line in result.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 3 and parts[0] == public_key:
                    return int(parts[1]), int(parts[2])
        except subprocess.CalledProcessError:
            pass
        return 0, 0

    def get_peer_latest_handshake(self, public_key: str):
        try:
            result = self._run_cmd(["awg", "show", self.interface, "latest-handshakes"])
            for line in result.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 2 and parts[0] == public_key:
                    ts = int(parts[1])
                    if ts > 0:
                        from datetime import datetime, timezone
                        return datetime.fromtimestamp(ts, tz=timezone.utc)
                    return None
        except subprocess.CalledProcessError:
            pass
        return None

    def get_peer_endpoints(self) -> Dict[str, str]:
        endpoints = {}
        try:
            result = self._run_cmd(["awg", "show", self.interface, "endpoints"])
            for line in result.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 2:
                    endpoints[parts[0]] = parts[1] if parts[1] != "(none)" else None
        except subprocess.CalledProcessError:
            pass
        return endpoints

    # ── Config generation ─────────────────────────────────────────────────────

    def generate_client_config(
        self,
        client_private_key: str,
        client_ipv4: str,
        client_ipv6: Optional[str],
        server_public_key: str,
        server_endpoint: str,
        preshared_key: Optional[str] = None,
        dns: str = "1.1.1.1,1.0.0.1",
        mtu: int = AWG_DEFAULT_MTU,
        allowed_ips: str = "0.0.0.0/0",
        persistent_keepalive: int = 25,
        # obfuscation overrides (fall back to instance params)
        jc: Optional[int] = None,
        jmin: Optional[int] = None,
        jmax: Optional[int] = None,
        s1: Optional[int] = None,
        s2: Optional[int] = None,
        h1: Optional[int] = None,
        h2: Optional[int] = None,
        h3: Optional[int] = None,
        h4: Optional[int] = None,
    ) -> str:
        """Generate AmneziaWG client config (.conf for AmneziaVPN app)."""
        address = client_ipv4
        if client_ipv6:
            address = f"{client_ipv4},{client_ipv6}"

        _jc   = jc   if jc   is not None else self.jc
        _jmin = jmin if jmin is not None else self.jmin
        _jmax = jmax if jmax is not None else self.jmax
        _s1   = s1   if s1   is not None else self.s1
        _s2   = s2   if s2   is not None else self.s2
        _h1   = h1   if h1   is not None else self.h1
        _h2   = h2   if h2   is not None else self.h2
        _h3   = h3   if h3   is not None else self.h3
        _h4   = h4   if h4   is not None else self.h4

        config = (
            f"[Interface]\n"
            f"PrivateKey = {client_private_key}\n"
            f"Address = {address}\n"
            f"DNS = {dns}\n"
            f"MTU = {mtu}\n"
            f"Jc = {_jc}\n"
            f"Jmin = {_jmin}\n"
            f"Jmax = {_jmax}\n"
            f"S1 = {_s1}\n"
            f"S2 = {_s2}\n"
            f"H1 = {_h1}\n"
            f"H2 = {_h2}\n"
            f"H3 = {_h3}\n"
            f"H4 = {_h4}\n"
            f"\n"
            f"[Peer]\n"
            f"PublicKey = {server_public_key}\n"
        )
        if preshared_key:
            config += f"PresharedKey = {preshared_key}\n"
        config += (
            f"Endpoint = {server_endpoint}\n"
            f"AllowedIPs = {allowed_ips}\n"
            f"PersistentKeepalive = {persistent_keepalive}\n"
        )
        return config

    def generate_server_config(
        self,
        private_key: str,
        address: str,           # e.g. "10.8.0.1/24"
        listen_port: int,
        eth_interface: Optional[str] = None,  # None = auto-detect egress NIC at PostUp time
        peers: Optional[List[dict]] = None,
        mtu: Optional[int] = None,
        jc: Optional[int] = None,
        jmin: Optional[int] = None,
        jmax: Optional[int] = None,
        s1: Optional[int] = None,
        s2: Optional[int] = None,
        h1: Optional[int] = None,
        h2: Optional[int] = None,
        h3: Optional[int] = None,
        h4: Optional[int] = None,
    ) -> str:
        """Generate awg0.conf-style server configuration."""
        _jc   = jc   if jc   is not None else self.jc
        _jmin = jmin if jmin is not None else self.jmin
        _jmax = jmax if jmax is not None else self.jmax
        _s1   = s1   if s1   is not None else self.s1
        _s2   = s2   if s2   is not None else self.s2
        _h1   = h1   if h1   is not None else self.h1
        _h2   = h2   if h2   is not None else self.h2
        _h3   = h3   if h3   is not None else self.h3
        _h4   = h4   if h4   is not None else self.h4

        # Derive subnet from address (e.g. "10.8.0.1/24" → "10.8.0.0/24")
        base_ip = address.split("/")[0]
        prefix = address.split("/")[1] if "/" in address else "24"
        octets = base_ip.rsplit(".", 1)
        subnet = f"{octets[0]}.0/{prefix}"

        # Egress interface: use explicit value or auto-detect at runtime via shell substitution.
        # Shell command runs inside PostUp/PostDown (bash -c), not at config generation time.
        eth_out = eth_interface if eth_interface else "$(ip route | awk '/^default/{print $5; exit}')"

        iface = self.interface
        config = (
            f"[Interface]\n"
            f"Address = {address}\n"
            f"ListenPort = {listen_port}\n"
            f"PrivateKey = {private_key}\n"
        )
        if mtu is not None:
            config += f"MTU = {mtu}\n"
        config += (
            f"Jc = {_jc}\n"
            f"Jmin = {_jmin}\n"
            f"Jmax = {_jmax}\n"
            f"S1 = {_s1}\n"
            f"S2 = {_s2}\n"
            f"H1 = {_h1}\n"
            f"H2 = {_h2}\n"
            f"H3 = {_h3}\n"
            f"H4 = {_h4}\n"
            f"PostUp   = iptables -t nat -A POSTROUTING -s {subnet} -o {eth_out} -j MASQUERADE; "
            f"iptables -A FORWARD -i {iface} -j ACCEPT; "
            f"iptables -A FORWARD -o {iface} -j ACCEPT; "
            f"ip route add {subnet} dev {iface} 2>/dev/null || true\n"
            f"PostDown = iptables -t nat -D POSTROUTING -s {subnet} -o {eth_out} -j MASQUERADE; "
            f"iptables -D FORWARD -i {iface} -j ACCEPT; "
            f"iptables -D FORWARD -o {iface} -j ACCEPT; "
            f"ip route del {subnet} dev {iface} 2>/dev/null || true\n"
        )

        for peer in (peers or []):
            config += f"\n[Peer]\n"
            if peer.get("name"):
                config += f"# {peer['name']}\n"
            config += f"PublicKey = {peer['public_key']}\n"
            if peer.get("preshared_key"):
                config += f"PresharedKey = {peer['preshared_key']}\n"
            allowed = peer.get("allowed_ips") or (peer.get("ipv4", "") + "/32")
            config += f"AllowedIPs = {allowed}\n"

        return config

    # ── Remote discovery ──────────────────────────────────────────────────────

    def discover_remote(self) -> Optional[Dict]:
        """Discover AmneziaWG configuration on remote server (SSH)."""
        if not self.is_remote:
            return None
        try:
            result = self._run_cmd(["awg", "show", self.interface, "dump"], check=False)
            if result.returncode != 0:
                return None

            lines = result.stdout.strip().split("\n")
            if not lines:
                return None

            iface_parts = lines[0].split("\t")
            server_private_key = iface_parts[0] if len(iface_parts) > 0 else None
            server_public_key  = iface_parts[1] if len(iface_parts) > 1 else None
            listen_port        = int(iface_parts[2]) if len(iface_parts) > 2 else 443

            config_content = self.read_config_file()
            address_pool_ipv4 = None
            awg_params: Dict[str, int] = {}
            if config_content:
                _awg_int_keys = {
                    "jc": "jc", "jmin": "jmin", "jmax": "jmax",
                    "s1": "s1", "s2": "s2",
                    "h1": "h1", "h2": "h2", "h3": "h3", "h4": "h4",
                }
                for line in config_content.split("\n"):
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith("["):
                        continue
                    if "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip().lower()
                    val = val.strip()
                    if key == "address":
                        for addr in val.split(","):
                            addr = addr.strip()
                            if ":" not in addr:
                                address_pool_ipv4 = addr
                    elif key in _awg_int_keys:
                        try:
                            awg_params[_awg_int_keys[key]] = int(val)
                        except ValueError:
                            pass

            clients = []
            for line in lines[1:]:
                parts = line.split("\t")
                if len(parts) >= 4:
                    clients.append({
                        "public_key": parts[0],
                        "preshared_key": parts[1] if parts[1] != "(none)" else None,
                        "allowed_ips": parts[3].split(",") if parts[3] else [],
                        "transfer_rx": int(parts[5]) if len(parts) > 5 else 0,
                        "transfer_tx": int(parts[6]) if len(parts) > 6 else 0,
                    })
                    if clients[-1]["allowed_ips"]:
                        ip = clients[-1]["allowed_ips"][0].split("/")[0]
                        clients[-1]["name"] = f"peer_{ip.replace('.', '_')}"
                    else:
                        clients[-1]["name"] = f"peer_{parts[0][:8]}"

            return {
                "interface": self.interface,
                "server_type": "amneziawg",
                "public_key": server_public_key,
                "private_key": server_private_key,
                "listen_port": listen_port,
                "address_pool_ipv4": address_pool_ipv4,
                "address_pool_ipv6": None,
                "clients": clients,
                "awg_params": awg_params if awg_params else None,
            }
        except Exception as e:
            logger.error(f"[AWG] discover_remote failed: {e}")
            return None
