"""
VPN Management Studio AmneziaWG Manager
Obfuscated WireGuard using amneziawg kernel module + awg/awg-quick tools.

All commands use `awg` / `awg-quick` instead of `wg` / `wg-quick`.
Obfuscation parameters (Jc, Jmin, Jmax, S1, S2, H1-H4) are stored on
the Server model and embedded into both server and client configs.
"""

import base64
import json
import os
import struct
import subprocess
import zlib
from typing import Any, Optional, Tuple, Dict, List

from loguru import logger

from .wireguard import WireGuardManager, PeerInfo


AWG_DEFAULT_MTU = 1280  # Safe MTU for AmneziaWG (avoids fragmentation on most networks)


def _amnezia_vpn_share_url(payload: dict) -> str:
    """Encode a dict as a vpn://... URL the AmneziaVPN mobile app accepts.

    The AmneziaVPN client speaks its own share format: minified JSON →
    Qt's qCompress (zlib payload prepended with a 4-byte big-endian
    "original length" header) → base64-url without padding → vpn:// prefix.
    Plain wg-quick text is NOT accepted by the mobile app — it 'ErrorCode 900
    Configuration does not contain any containers'. This function builds
    the right wrapper.
    """
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    compressed = zlib.compress(raw, level=8)
    qcompress_blob = struct.pack(">I", len(raw)) + compressed
    b64 = base64.urlsafe_b64encode(qcompress_blob).rstrip(b"=").decode("ascii")
    return f"vpn://{b64}"


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
        config_path: str = "/etc/amnezia/amneziawg/awg0.conf",
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

    def _awgquick_target(self) -> str:
        """Argument for `awg-quick {up,down,save}`.

        When config_path is set to a non-default location (e.g. our installer
        puts AWG configs under /opt/amneziawg/config/), awg-quick won't find
        it via the bare interface name — its default lookup is
        /etc/amnezia/<iface>.conf. Pass the explicit path so it works
        regardless of where the config lives.
        """
        if self.config_path:
            return self.config_path
        return self.interface

    def start_interface(self) -> bool:
        if self.is_interface_up():
            logger.info(f"[AWG] Interface {self.interface} already up")
            return True
        try:
            self._run_cmd(["awg-quick", "up", self._awgquick_target()])
            logger.info(f"[AWG] Started interface {self.interface}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"[AWG] Failed to start interface: {e.stderr}")
            return False

    def stop_interface(self) -> bool:
        try:
            self._run_cmd(["awg-quick", "down", self._awgquick_target()])
            logger.info(f"[AWG] Stopped interface {self.interface}")
            return True
        except subprocess.CalledProcessError as e:
            # awg-quick can exit non-zero on a PostDown quirk (e.g. an
            # iptables rule already removed by another process, or a stale
            # `ip route del` line) AFTER the interface itself is gone.
            # If the kernel no longer shows the interface, the teardown
            # achieved its goal and we treat it as success — the alternative
            # is reporting "stop failed" while clients see the interface
            # vanish anyway, which is what burned us during 1.5.73 testing.
            if not self.is_interface_up():
                logger.info(f"[AWG] {self.interface} is down despite awg-quick exit ({e.returncode}) — treating as success")
                return True
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

    def generate_amneziavpn_share_url(
        self,
        client_private_key: str,
        client_public_key: str,
        client_ipv4: str,
        client_ipv6: Optional[str],
        server_public_key: str,
        server_endpoint: str,    # MUST include :port
        preshared_key: Optional[str] = None,
        dns: str = "1.1.1.1,1.0.0.1",
        mtu: int = AWG_DEFAULT_MTU,
        allowed_ips: str = "0.0.0.0/0",
        persistent_keepalive: int = 25,
        description: str = "Flirexa",
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
        """Build a vpn://... share URL for the AmneziaVPN mobile/desktop app.

        Wraps the same .conf content the wg-quick path uses, but inside the
        JSON shape the mobile app actually parses (containers / amnezia-awg
        / last_config). Plain text QR codes get rejected with 'ErrorCode 900'.
        """
        _jc   = jc   if jc   is not None else self.jc
        _jmin = jmin if jmin is not None else self.jmin
        _jmax = jmax if jmax is not None else self.jmax
        _s1   = s1   if s1   is not None else self.s1
        _s2   = s2   if s2   is not None else self.s2
        _h1   = h1   if h1   is not None else self.h1
        _h2   = h2   if h2   is not None else self.h2
        _h3   = h3   if h3   is not None else self.h3
        _h4   = h4   if h4   is not None else self.h4

        # The same .conf text the desktop client / awg-quick consumes — the
        # mobile app keeps a copy under last_config for quick re-export.
        wg_conf = self.generate_client_config(
            client_private_key=client_private_key,
            client_ipv4=client_ipv4,
            client_ipv6=client_ipv6,
            server_public_key=server_public_key,
            server_endpoint=server_endpoint,
            preshared_key=preshared_key,
            dns=dns,
            mtu=mtu,
            allowed_ips=allowed_ips,
            persistent_keepalive=persistent_keepalive,
            jc=_jc, jmin=_jmin, jmax=_jmax,
            s1=_s1, s2=_s2,
            h1=_h1, h2=_h2, h3=_h3, h4=_h4,
        )

        # Split host:port for the JSON fields. Endpoint always carries a port
        # at this layer (caller is responsible).
        host = server_endpoint
        port = ""
        if "]:" in server_endpoint:                # IPv6 literal "[::1]:51820"
            host, _, port = server_endpoint.rpartition(":")
        elif server_endpoint.count(":") == 1:      # plain "host:port"
            host, _, port = server_endpoint.rpartition(":")

        last_config_inner = {
            "H1": str(_h1), "H2": str(_h2), "H3": str(_h3), "H4": str(_h4),
            "Jc": str(_jc), "Jmax": str(_jmax), "Jmin": str(_jmin),
            "S1": str(_s1), "S2": str(_s2),
            "client_ip":          client_ipv4.split("/")[0],
            "client_priv_key":    client_private_key,
            "client_pub_key":     client_public_key,
            "config":             wg_conf,
            "hostName":           host,
            "mtu":                str(mtu),
            "persistent_keep_alive": str(persistent_keepalive),
            "port":               port or "0",
            "psk_key":            preshared_key or "",
            "server_pub_key":     server_public_key,
        }

        awg_block = {
            "H1": str(_h1), "H2": str(_h2), "H3": str(_h3), "H4": str(_h4),
            "Jc": str(_jc), "Jmax": str(_jmax), "Jmin": str(_jmin),
            "S1": str(_s1), "S2": str(_s2),
            "last_config":  json.dumps(last_config_inner, separators=(",", ":")),
            "port":         port or "0",
            "transport_proto": "udp",
        }

        share_payload = {
            "containers": [{
                "container":   "amnezia-awg",
                "amnezia-awg": awg_block,
            }],
            "defaultContainer": "amnezia-awg",
            "description":      description or "Flirexa",
            "dns1":             "1.1.1.1",
            "dns2":             "1.0.0.1",
            "hostName":         host,
        }
        return _amnezia_vpn_share_url(share_payload)

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

        # Derive IPv4 subnet from address. address may be a single CIDR
        # ("10.8.0.1/24") or a comma-joined dual-stack value
        # ("10.8.0.1/24,fd42:42:42::1/64") — pick the IPv4 half. NAT/route
        # rules are IPv4-only here; IPv6 forwarding sits on the kernel
        # default and doesn't need its own MASQUERADE.
        ipv4_part = address.split(",")[0].strip()
        base_ip = ipv4_part.split("/")[0]
        prefix = ipv4_part.split("/")[1] if "/" in ipv4_part else "24"
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

    # ── Remote bootstrap (SSH-only, no agent) ─────────────────────────────────

    def bootstrap_remote(
        self,
        address_pool_ipv4: str = "10.66.66.0/24",
        address_pool_ipv6: Optional[str] = None,
        listen_port: int = 51821,
        dns: str = "1.1.1.1",
        log_callback=None,
    ) -> Dict[str, Any]:
        """
        Provision AmneziaWG on an existing SSH-accessible server WITHOUT
        installing the agent. Suitable for adding AWG alongside an
        already-configured WG interface that's managed by the agent: the
        AWG side is then managed via SSH commands.

        Steps:
          1. Install amneziawg + amneziawg-tools (PPA / apt)
          2. Generate keypair + obfuscation params on remote
          3. Write awg config to /etc/amnezia/amneziawg/<iface>.conf
          4. Enable IP forwarding
          5. Bring up the interface (awg-quick @ iface)
          6. Open the listen port in UFW (best-effort)

        Returns:
          {
            "success": bool,
            "message": str,
            "public_key": str | None,
            "private_key": str | None,
            "listen_port": int,
            "awg_params": dict | None,
            "details": dict,
          }
        """
        def _log(msg: str):
            logger.info(msg)
            if log_callback:
                log_callback(msg)

        details: Dict[str, Any] = {}
        if not self.is_remote:
            return {"success": False, "message": "bootstrap_remote requires ssh_host", "details": details}

        # ── 1. Install amneziawg package ──────────────────────────────────────
        _log("📦 Checking AmneziaWG installation…")
        rc_check = self._run_cmd(["which", "awg"], check=False).returncode
        if rc_check != 0:
            _log("⬇ Installing AmneziaWG (apt + PPA, may take 1-2 min)…")
            # Two-tier strategy mirrored from agent_bootstrap._awg_install_cmd:
            #   1. Try the official ppa:amnezia/ppa.
            #   2. If launchpadcontent.net is unreachable, fall back to
            #      flirexa.biz/mirror/amnezia/<series>/.deb files.
            # See agent_bootstrap.py for the full rationale.
            install_cmd = r'''bash -c '
set -e
APT_FLAGS=(-o Acquire::ForceIPv4=true -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20)
MIRROR_BASE="https://flirexa.biz/mirror/amnezia"

retry_apt_update() {
    local attempt=1
    while [ "$attempt" -le 3 ]; do
        if apt-get "${APT_FLAGS[@]}" update 2>&1; then return 0; fi
        attempt=$((attempt + 1)); sleep 5
    done
    return 1
}

amnezia_index_ok() { apt-cache policy amneziawg-tools 2>/dev/null | grep -q "amnezia"; }

install_from_mirror() {
    local series="${VERSION_CODENAME:-noble}"
    case "$series" in noble|jammy|focal) ;; *) series=noble ;; esac
    local tmp; tmp=$(mktemp -d); cd "$tmp"
    for pkg in amneziawg-dkms amneziawg-tools amneziawg; do
        curl -4 -fsSL --max-time 60 -o "${pkg}.deb" "${MIRROR_BASE}/${series}/${pkg}.deb" || return 1
    done
    apt-get "${APT_FLAGS[@]}" install -y dkms "linux-headers-$(uname -r)" 2>&1 || \
        apt-get "${APT_FLAGS[@]}" install -y dkms linux-headers-generic 2>&1 || true
    dpkg -i amneziawg-dkms.deb amneziawg-tools.deb amneziawg.deb 2>&1 || \
        apt-get "${APT_FLAGS[@]}" install -y -f 2>&1
}

. /etc/os-release 2>/dev/null || true
case "${ID:-}" in
  ubuntu|debian)
    export DEBIAN_FRONTEND=noninteractive
    apt-get "${APT_FLAGS[@]}" install -y software-properties-common curl gnupg ca-certificates 2>&1
    if [ "${ID:-}" = "ubuntu" ]; then
        add-apt-repository -y ppa:amnezia/ppa 2>&1 || true
    else
        echo "deb http://ppa.launchpad.net/amnezia/ppa/ubuntu focal main" > /etc/apt/sources.list.d/amnezia-awg.list
        apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 57290828 2>&1 || \
            curl -4 -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x57290828" | apt-key add - 2>&1 || true
    fi
    retry_apt_update || true
    if amnezia_index_ok && apt-get "${APT_FLAGS[@]}" install -y amneziawg amneziawg-tools 2>&1; then
        echo "[ok] amneziawg installed via PPA"; exit 0
    fi
    echo "[ppa] unreachable, switching to mirror"
    install_from_mirror
    ;;
  *) echo "Unsupported distro" >&2; exit 1 ;;
esac
' '''
            r = self._run_cmd(["bash", "-c", install_cmd], check=False)
            if r.returncode != 0:
                err_tail = (r.stderr or r.stdout or "")[-400:].strip()
                return {
                    "success": False,
                    "message": (
                        "Failed to install AmneziaWG via PPA. The remote server may be "
                        "in a region that blocks launchpad.net (e.g. China/HK). "
                        f"Error tail: {err_tail}"
                    ),
                    "details": details,
                }
            details["installed"] = True
            _log("✓ AmneziaWG installed")
        else:
            details["installed"] = "already_present"
            _log("✓ AmneziaWG already installed")

        # ── 2. Generate keypair + obfuscation params on remote ────────────────
        _log("🔐 Generating server keypair…")
        priv_r = self._run_cmd(["awg", "genkey"], check=False)
        if priv_r.returncode != 0 or not priv_r.stdout.strip():
            return {"success": False, "message": "Failed to generate AWG private key on remote", "details": details}
        private_key = priv_r.stdout.strip()
        pub_r = self._run_cmd(["bash", "-c", f"echo '{private_key}' | awg pubkey"], check=False)
        if pub_r.returncode != 0 or not pub_r.stdout.strip():
            return {"success": False, "message": "Failed to derive AWG public key on remote", "details": details}
        public_key = pub_r.stdout.strip()
        details["public_key"] = public_key

        params = self.generate_obfuscation_params()
        # Sync into instance so generate_server_config picks them up
        self.jc, self.jmin, self.jmax = params["jc"], params["jmin"], params["jmax"]
        self.s1, self.s2 = params["s1"], params["s2"]
        self.h1, self.h2, self.h3, self.h4 = params["h1"], params["h2"], params["h3"], params["h4"]

        # ── 3. Build + write server config ────────────────────────────────────
        # Convert the network CIDR into the .1 host address for the interface.
        ipv4_net = address_pool_ipv4 or "10.66.66.0/24"
        net_part, _, prefix = ipv4_net.partition("/")
        prefix = prefix or "24"
        octets = net_part.split(".")
        if len(octets) != 4:
            return {"success": False, "message": f"Bad address_pool_ipv4 '{ipv4_net}'", "details": details}
        host_addr = ".".join(octets[:3] + ["1"]) + f"/{prefix}"
        if address_pool_ipv6:
            # Accept either "fd42:42:42::/64" (network) or "fd42:42:42::1/64"
            # (already a host). Naive concat doubles up the ::1 and yields
            # the invalid "fd42:42:42::1::1/64" — route through `ipaddress`
            # so the output is always a valid host.
            try:
                import ipaddress as _ip
                iface = _ip.IPv6Interface(address_pool_ipv6)
                net = iface.network
                host = iface.ip if iface.ip != net.network_address else (net.network_address + 1)
                host_addr = f"{host_addr},{host}/{net.prefixlen}"
            except Exception:
                v6_net, _, v6_prefix = address_pool_ipv6.partition("/")
                v6_prefix = v6_prefix or "64"
                base = v6_net.rstrip(":")
                host_addr = f"{host_addr},{base}::1/{v6_prefix}"

        config_content = self.generate_server_config(
            private_key=private_key,
            address=host_addr,
            listen_port=listen_port,
            peers=[],
        )

        config_dir = "/etc/amnezia/amneziawg"
        config_file = f"{config_dir}/{self.interface}.conf"
        _log(f"📝 Writing config: {config_file}")
        self._run_cmd(["mkdir", "-p", config_dir], check=False)
        self._run_cmd(["chmod", "700", config_dir], check=False)
        # Use base64-via-stdin pattern to avoid shell-quoting hazards
        import base64 as _b64
        b64 = _b64.b64encode(config_content.encode()).decode()
        self._run_cmd(
            ["bash", "-c", f"echo '{b64}' | base64 -d > {config_file} && chmod 600 {config_file}"],
            check=False,
        )
        details["config_path"] = config_file

        # ── 4. Enable IP forwarding ───────────────────────────────────────────
        self._run_cmd(["sysctl", "-w", "net.ipv4.ip_forward=1"], check=False)
        self._run_cmd(["sysctl", "-w", "net.ipv6.conf.all.forwarding=1"], check=False)
        self._run_cmd(
            ["bash", "-c",
             "grep -qxF 'net.ipv4.ip_forward=1' /etc/sysctl.conf || "
             "echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf"],
            check=False,
        )

        # ── 5. Bring up the interface ─────────────────────────────────────────
        _log(f"🚀 Bringing up {self.interface}…")
        # If a stale unit is up from a previous attempt, restart instead of up
        is_up = self._run_cmd(["awg", "show", self.interface], check=False).returncode == 0
        if is_up:
            self._run_cmd(["awg-quick", "down", self.interface], check=False)
        up_r = self._run_cmd(["awg-quick", "up", self.interface], check=False)
        if up_r.returncode != 0:
            err_tail = (up_r.stderr or up_r.stdout or "")[-400:].strip()
            return {
                "success": False,
                "message": f"awg-quick up {self.interface} failed: {err_tail}",
                "details": details,
            }
        # Persist via systemd (so it survives reboot)
        self._run_cmd(
            ["systemctl", "enable", f"awg-quick@{self.interface}"],
            check=False,
        )
        details["interface_up"] = True

        # ── 6. Open UFW (best-effort) ─────────────────────────────────────────
        try:
            ufw_rc = self._run_cmd(["which", "ufw"], check=False).returncode
            if ufw_rc == 0:
                status = self._run_cmd(["ufw", "status"], check=False)
                if "Status: active" in (status.stdout or ""):
                    rule = f"{listen_port}/udp"
                    if rule not in (status.stdout or ""):
                        _log(f"🛡  UFW active — opening {rule}")
                        self._run_cmd(
                            ["bash", "-c", f"ufw allow {rule} comment 'amneziawg ({self.interface})'"],
                            check=False,
                        )
                        details["firewall_opened"] = rule
        except Exception as e:
            logger.warning(f"UFW best-effort for AWG failed: {e}")

        _log(f"✅ AmneziaWG running on UDP:{listen_port} (interface {self.interface})")
        return {
            "success": True,
            "message": "AmneziaWG provisioned",
            "public_key": public_key,
            "private_key": private_key,
            "listen_port": listen_port,
            "awg_params": params,
            "details": details,
        }
