"""
VPN Management Studio WireGuard Manager
Low-level WireGuard operations using wg and wg-quick commands
Supports both local and remote (SSH) execution
"""

import subprocess
import os
import re
from typing import Optional, Tuple, Dict, List
from dataclasses import dataclass
from datetime import datetime, timezone
from loguru import logger


@dataclass
class PeerInfo:
    """WireGuard peer information from wg show"""
    public_key: str
    preshared_key: bool = False
    endpoint: Optional[str] = None
    allowed_ips: List[str] = None
    latest_handshake: Optional[datetime] = None
    transfer_rx: int = 0
    transfer_tx: int = 0
    persistent_keepalive: Optional[int] = None


class WireGuardManager:
    """
    Manages WireGuard interface operations
    All low-level wg/wg-quick commands are here

    Supports local and remote (SSH) execution.
    If ssh_host is provided, commands are executed on the remote server via SSH.
    """

    def __init__(
        self,
        interface: str = "wg0",
        config_path: str = "/etc/wireguard/wg0.conf",
        ssh_host: Optional[str] = None,
        ssh_port: int = 22,
        ssh_user: str = "root",
        ssh_password: Optional[str] = None,
        ssh_private_key: Optional[str] = None,
    ):
        self.interface = interface
        self.config_path = config_path
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.ssh_private_key = ssh_private_key
        self._ssh_client = None

    @property
    def is_remote(self) -> bool:
        return self.ssh_host is not None

    def _get_ssh(self, _retry=True):
        """Get or create SSH connection (with single retry on stale connection)."""
        if self._ssh_client is None:
            import paramiko
            import io as _io
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            pkey = None
            if self.ssh_private_key:
                for _cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
                    try:
                        pkey = _cls.from_private_key(_io.StringIO(self.ssh_private_key))
                        break
                    except Exception:
                        pass
            self._ssh_client.connect(
                self.ssh_host,
                port=self.ssh_port,
                username=self.ssh_user,
                password=self.ssh_password if not pkey else None,
                pkey=pkey,
                timeout=10,
            )
        # Check if connection is still alive
        transport = self._ssh_client.get_transport()
        if transport is None or not transport.is_active():
            self._ssh_client.close()
            self._ssh_client = None
            if _retry:
                return self._get_ssh(_retry=False)
            raise ConnectionError(f"SSH connection to {self.ssh_host} failed after retry")
        return self._ssh_client

    def _run_cmd(self, cmd, input=None, check=True):
        """Execute command locally or via SSH.

        Returns subprocess.CompletedProcess (or compatible object).
        """
        if not self.ssh_host:
            # Local execution
            return subprocess.run(
                cmd, input=input, capture_output=True, text=True, check=check
            )

        # Remote execution via SSH
        ssh = self._get_ssh()
        if isinstance(cmd, (list, tuple)):
            import shlex
            cmd_str = " ".join(shlex.quote(str(c)) for c in cmd)
        else:
            cmd_str = cmd

        if input:
            # Use base64 to safely pass input over SSH (avoids shell injection via quotes)
            import base64
            b64 = base64.b64encode(input.encode()).decode()
            cmd_str = f"echo '{b64}' | base64 -d | {cmd_str}"

        stdin, stdout, stderr = ssh.exec_command(cmd_str, timeout=30)
        out = stdout.read().decode()
        err = stderr.read().decode()
        rc = stdout.channel.recv_exit_status()

        result = subprocess.CompletedProcess(cmd, rc, out, err)
        if check and rc != 0:
            raise subprocess.CalledProcessError(rc, cmd, out, err)
        return result

    def _read_remote_file(self, path: str) -> str:
        """Read file content via SSH."""
        result = self._run_cmd(["cat", path])
        return result.stdout

    def _write_remote_file(self, path: str, content: str):
        """Write file content via SSH using SFTP."""
        ssh = self._get_ssh()
        sftp = ssh.open_sftp()
        try:
            with sftp.file(path, "w") as f:
                f.write(content)
            sftp.chmod(path, 0o600)
        finally:
            sftp.close()

    def close(self):
        """Close SSH connection if open."""
        if self._ssh_client:
            self._ssh_client.close()
            self._ssh_client = None

    # ========================================================================
    # KEY GENERATION
    # ========================================================================

    @staticmethod
    def generate_private_key() -> str:
        """Generate a new WireGuard private key"""
        result = subprocess.run(
            ["wg", "genkey"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()

    @staticmethod
    def generate_public_key(private_key: str) -> str:
        """Derive public key from private key"""
        result = subprocess.run(
            ["wg", "pubkey"],
            input=private_key,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()

    @staticmethod
    def generate_keypair() -> Tuple[str, str]:
        """Generate a private/public key pair"""
        private_key = WireGuardManager.generate_private_key()
        public_key = WireGuardManager.generate_public_key(private_key)
        return private_key, public_key

    @staticmethod
    def generate_preshared_key() -> str:
        """Generate a preshared key"""
        result = subprocess.run(
            ["wg", "genpsk"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()

    # ========================================================================
    # INTERFACE OPERATIONS
    # ========================================================================

    def is_interface_up(self) -> bool:
        """Check if WireGuard interface is up"""
        try:
            result = self._run_cmd(
                ["wg", "show", self.interface],
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False

    def start_interface(self) -> bool:
        """Start WireGuard interface using wg-quick"""
        if self.is_interface_up():
            logger.info(f"Interface {self.interface} is already up")
            return True
        try:
            self._run_cmd(["wg-quick", "up", self.interface])
            logger.info(f"Started WireGuard interface {self.interface}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start interface: {e.stderr}")
            return False

    def stop_interface(self) -> bool:
        """Stop WireGuard interface"""
        try:
            self._run_cmd(["wg-quick", "down", self.interface])
            logger.info(f"Stopped WireGuard interface {self.interface}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to stop interface: {e.stderr}")
            return False

    def restart_interface(self) -> bool:
        """Restart WireGuard interface"""
        self.stop_interface()
        return self.start_interface()

    def save_config(self) -> bool:
        """Save current running config to file"""
        try:
            self._run_cmd(["wg-quick", "save", self.interface])
            logger.debug(f"Saved config for {self.interface}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to save config: {e.stderr}")
            return False

    # ========================================================================
    # PEER OPERATIONS
    # ========================================================================

    def add_peer(
        self,
        public_key: str,
        allowed_ips: List[str],
        preshared_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        persistent_keepalive: Optional[int] = None,
    ) -> bool:
        """Add a peer to the WireGuard interface"""
        try:
            cmd = [
                "wg", "set", self.interface,
                "peer", public_key,
                "allowed-ips", ",".join(allowed_ips)
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

            # Save configuration
            self.save_config()

            logger.info(f"Added peer {public_key[:16]}... with IPs {allowed_ips}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to add peer: {e}")
            return False

    def remove_peer(self, public_key: str) -> bool:
        """Remove a peer from the WireGuard interface"""
        try:
            self._run_cmd(
                ["wg", "set", self.interface, "peer", public_key, "remove"]
            )
            self.save_config()
            logger.info(f"Removed peer {public_key[:16]}...")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to remove peer: {e}")
            return False

    def update_peer_allowed_ips(self, public_key: str, allowed_ips: List[str]) -> bool:
        """Update allowed IPs for a peer"""
        try:
            self._run_cmd([
                "wg", "set", self.interface,
                "peer", public_key,
                "allowed-ips", ",".join(allowed_ips)
            ])
            self.save_config()
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to update peer allowed IPs: {e}")
            return False

    # ========================================================================
    # STATUS & MONITORING
    # ========================================================================

    def get_interface_info(self) -> Optional[Dict]:
        """Get interface information"""
        try:
            result = self._run_cmd(["wg", "show", self.interface])

            info = {
                "interface": self.interface,
                "public_key": None,
                "private_key": "(hidden)",
                "listening_port": None,
                "peers_count": 0
            }

            lines = result.stdout.strip().split("\n")
            for line in lines:
                if "public key:" in line:
                    info["public_key"] = line.split(":")[1].strip()
                elif "listening port:" in line:
                    info["listening_port"] = int(line.split(":")[1].strip())
                elif line.startswith("peer:"):
                    info["peers_count"] += 1

            return info

        except subprocess.CalledProcessError:
            return None

    def get_all_peers(self) -> List[PeerInfo]:
        """Get list of all peers with their info"""
        peers = []

        try:
            result = self._run_cmd(["wg", "show", self.interface, "dump"])

            lines = result.stdout.strip().split("\n")
            # Skip first line (interface info)
            for line in lines[1:]:
                parts = line.split("\t")
                if len(parts) >= 8:
                    peer = PeerInfo(
                        public_key=parts[0],
                        preshared_key=parts[1] != "(none)",
                        endpoint=parts[2] if parts[2] != "(none)" else None,
                        allowed_ips=parts[3].split(",") if parts[3] else [],
                        latest_handshake=datetime.fromtimestamp(int(parts[4]), tz=timezone.utc) if parts[4] != "0" else None,
                        transfer_rx=int(parts[5]),
                        transfer_tx=int(parts[6]),
                        persistent_keepalive=int(parts[7]) if parts[7] != "off" else None
                    )
                    peers.append(peer)

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get peers: {e}")

        return peers

    def get_peer_transfer(self, public_key: str) -> Tuple[int, int]:
        """Get transfer statistics for a specific peer (rx, tx in bytes)"""
        try:
            result = self._run_cmd(["wg", "show", self.interface, "transfer"])

            for line in result.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 3 and parts[0] == public_key:
                    return int(parts[1]), int(parts[2])

            return 0, 0

        except subprocess.CalledProcessError:
            return 0, 0

    def get_peer_latest_handshake(self, public_key: str) -> Optional[datetime]:
        """Get the latest handshake time for a peer"""
        try:
            result = self._run_cmd(["wg", "show", self.interface, "latest-handshakes"])

            for line in result.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 2 and parts[0] == public_key:
                    timestamp = int(parts[1])
                    if timestamp > 0:
                        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    return None

            return None

        except subprocess.CalledProcessError:
            return None

    def get_peer_endpoints(self) -> Dict[str, str]:
        """Get current endpoints for all peers"""
        endpoints = {}
        try:
            result = self._run_cmd(["wg", "show", self.interface, "endpoints"])

            for line in result.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 2:
                    endpoints[parts[0]] = parts[1] if parts[1] != "(none)" else None

        except subprocess.CalledProcessError:
            pass

        return endpoints

    # ========================================================================
    # CONFIG FILE OPERATIONS
    # ========================================================================

    def read_config_file(self) -> Optional[str]:
        """Read the WireGuard config file"""
        try:
            if self.is_remote:
                return self._read_remote_file(self.config_path)
            with open(self.config_path, "r") as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Config file not found: {self.config_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to read config: {e}")
            return None

    def write_config_file(self, content: str) -> bool:
        """Write to the WireGuard config file"""
        try:
            if self.is_remote:
                self._write_remote_file(self.config_path, content)
                return True
            with open(self.config_path, "w") as f:
                f.write(content)
            os.chmod(self.config_path, 0o600)
            return True
        except Exception as e:
            logger.error(f"Failed to write config: {e}")
            return False

    def backup_config(self, backup_path: Optional[str] = None) -> Optional[str]:
        """Create a backup of the config file"""
        if backup_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{self.config_path}.backup_{timestamp}"

        try:
            content = self.read_config_file()
            if content:
                if self.is_remote:
                    self._write_remote_file(backup_path, content)
                else:
                    with open(backup_path, "w") as f:
                        f.write(content)
                    os.chmod(backup_path, 0o600)
                return backup_path
        except Exception as e:
            logger.error(f"Failed to backup config: {e}")

        return None

    # ========================================================================
    # CLIENT CONFIG GENERATION
    # ========================================================================

    def generate_client_config(
        self,
        client_private_key: str,
        client_ipv4: str,
        client_ipv6: Optional[str],
        server_public_key: str,
        server_endpoint: str,
        preshared_key: Optional[str] = None,
        dns: str = "1.1.1.1,1.0.0.1",
        mtu: int = 1420,
        allowed_ips: str = "0.0.0.0/0,::/0",
        persistent_keepalive: int = 25,
    ) -> str:
        """Generate a client configuration file content"""
        address = client_ipv4
        if client_ipv6:
            address = f"{client_ipv4},{client_ipv6}"

        config = f"""[Interface]
PrivateKey = {client_private_key}
Address = {address}
DNS = {dns}
MTU = {mtu}

[Peer]
PublicKey = {server_public_key}
"""

        if preshared_key:
            config += f"PresharedKey = {preshared_key}\n"

        config += f"""Endpoint = {server_endpoint}
AllowedIPs = {allowed_ips}
PersistentKeepalive = {persistent_keepalive}
"""

        return config

    def save_client_config(
        self,
        config_content: str,
        client_name: str,
        config_dir: str = "/root"
    ) -> str:
        """Save client config to a file"""
        config_path = os.path.join(config_dir, f"wg0-client-{client_name}.conf")

        if self.is_remote:
            self._write_remote_file(config_path, config_content)
        else:
            with open(config_path, "w") as f:
                f.write(config_content)
            os.chmod(config_path, 0o600)

        return config_path

    # ========================================================================
    # REMOTE DISCOVERY
    # ========================================================================

    def discover_remote(self) -> Optional[Dict]:
        """Discover WireGuard configuration on a remote server via SSH.

        Strategy:
          1. Try 'wg show <iface> dump' — works when interface is running.
          2. If interface is down, fall back to parsing /etc/wireguard/<iface>.conf.
          3. In both cases also read the config file for Address/ListenPort.

        Returns dict with server info and list of clients, or None on failure.
        """
        if not self.is_remote:
            logger.error("discover_remote called on local manager")
            return None

        config_dir = "/etc/wireguard"

        try:
            server_private_key = None
            server_public_key  = None
            listen_port        = 51820
            address_pool_ipv4  = None
            address_pool_ipv6  = None
            clients            = []
            from_live          = False  # True if wg show dump succeeded

            # ------------------------------------------------------------------
            # 1. Try live interface dump
            # ------------------------------------------------------------------
            dump_result = self._run_cmd(
                ["wg", "show", self.interface, "dump"], check=False
            )
            if dump_result.returncode == 0 and dump_result.stdout.strip():
                lines = dump_result.stdout.strip().split("\n")
                iface_parts = lines[0].split("\t")
                server_private_key = iface_parts[0] if len(iface_parts) > 0 else None
                server_public_key  = iface_parts[1] if len(iface_parts) > 1 else None
                try:
                    listen_port = int(iface_parts[2]) if len(iface_parts) > 2 else 51820
                except ValueError:
                    pass

                for line in lines[1:]:
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        allowed_ips = parts[3].split(",") if parts[3] else []
                        clients.append({
                            "public_key":   parts[0],
                            "preshared_key": parts[1] if parts[1] != "(none)" else None,
                            "allowed_ips":  allowed_ips,
                            "transfer_rx":  int(parts[5]) if len(parts) > 5 else 0,
                            "transfer_tx":  int(parts[6]) if len(parts) > 6 else 0,
                        })
                from_live = True
                logger.info(f"[DISCOVER] Live dump OK for {self.interface} ({len(clients)} peers)")
            else:
                logger.warning(
                    f"[DISCOVER] 'wg show {self.interface} dump' failed "
                    f"(rc={dump_result.returncode}, err={dump_result.stderr.strip()!r}) — "
                    "falling back to config file"
                )

            # ------------------------------------------------------------------
            # 2. Read config file — always (for Address; fills keys if not live)
            # ------------------------------------------------------------------
            config_content = None
            cfg_path = f"{config_dir}/{self.interface}.conf"
            cat_result = self._run_cmd(["cat", cfg_path], check=False)
            if cat_result.returncode == 0 and cat_result.stdout.strip():
                config_content = cat_result.stdout
            else:
                logger.warning(f"[DISCOVER] Cannot read {cfg_path}: {cat_result.stderr.strip()!r}")

            if config_content:
                section = None
                current_peer: dict = {}
                for raw_line in config_content.split("\n"):
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.lower() == "[interface]":
                        section = "interface"
                        continue
                    if line.lower() == "[peer]":
                        if current_peer.get("public_key"):
                            clients.append(current_peer)
                        current_peer = {}
                        section = "peer"
                        continue

                    if "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip().lower()
                    val = val.strip()

                    if section == "interface":
                        if key == "privatekey" and not server_private_key:
                            server_private_key = val
                        elif key == "listenport" and listen_port == 51820:
                            try:
                                listen_port = int(val)
                            except ValueError:
                                pass
                        elif key == "address":
                            for addr in val.split(","):
                                addr = addr.strip()
                                if ":" in addr:
                                    address_pool_ipv6 = addr
                                else:
                                    address_pool_ipv4 = addr

                    elif section == "peer":
                        if key == "publickey":
                            current_peer["public_key"] = val
                        elif key == "presharedkey":
                            current_peer["preshared_key"] = val
                        elif key == "allowedips":
                            current_peer["allowed_ips"] = [
                                a.strip() for a in val.split(",")
                            ]

                if current_peer.get("public_key"):
                    clients.append(current_peer)

                # Derive server public key from private key if still unknown
                if server_private_key and not server_public_key:
                    pub_res = self._run_cmd(
                        ["wg", "pubkey"], input=server_private_key, check=False
                    )
                    if pub_res.returncode == 0:
                        server_public_key = pub_res.stdout.strip()

                # If we got peers from config but not from live dump, fill defaults
                if not from_live:
                    for p in clients:
                        p.setdefault("preshared_key", None)
                        p.setdefault("allowed_ips", [])
                        p.setdefault("transfer_rx", 0)
                        p.setdefault("transfer_tx", 0)

            # ------------------------------------------------------------------
            # 3. Validate — need at least public key
            # ------------------------------------------------------------------
            if not server_public_key:
                logger.error(
                    f"[DISCOVER] Could not determine public key for {self.interface} "
                    f"(interface {'up' if from_live else 'down'}, "
                    f"config {'found' if config_content else 'not found'})"
                )
                return None

            # Deduplicate peers by public key (config may list peers live dump also has)
            seen: set = set()
            unique_clients = []
            for c in clients:
                pk = c.get("public_key", "")
                if pk and pk not in seen:
                    seen.add(pk)
                    unique_clients.append(c)
            clients = unique_clients

            # ------------------------------------------------------------------
            # 4. Try to enrich peers with names from client config files
            # ------------------------------------------------------------------
            iface = self.interface  # e.g. "wg0", "wg1"
            client_configs: dict = {}
            for search_dir in [config_dir, "/root"]:
                ls_result = self._run_cmd(
                    f"ls {search_dir}/{iface}-client-*.conf 2>/dev/null || true",
                    check=False
                )
                for fpath in ls_result.stdout.strip().split("\n"):
                    fpath = fpath.strip()
                    if not fpath:
                        continue
                    fname = fpath.split("/")[-1]
                    client_name = fname.replace(f"{iface}-client-", "").replace(".conf", "")
                    try:
                        content = self._read_remote_file(fpath)
                        priv_key = None
                        for cl in content.split("\n"):
                            cl = cl.strip()
                            if cl.lower().startswith("privatekey"):
                                priv_key = cl.split("=", 1)[1].strip()
                                break
                        if priv_key:
                            pub_res = self._run_cmd(
                                ["wg", "pubkey"], input=priv_key, check=False
                            )
                            if pub_res.returncode == 0:
                                client_configs[pub_res.stdout.strip()] = client_name
                    except Exception:
                        pass

            for client in clients:
                pk = client.get("public_key", "")
                if pk in client_configs:
                    client["name"] = client_configs[pk]
                elif not client.get("name"):
                    ips = client.get("allowed_ips", [])
                    if ips:
                        ip = ips[0].split("/")[0]
                        client["name"] = f"peer_{ip.replace('.', '_')}"
                    else:
                        client["name"] = f"peer_{pk[:8]}"

            logger.info(
                f"[DISCOVER] ✅ {self.interface}: pubkey={server_public_key[:12]}… "
                f"port={listen_port} pool={address_pool_ipv4} peers={len(clients)} "
                f"source={'live' if from_live else 'config'}"
            )
            return {
                "interface":        self.interface,
                "public_key":       server_public_key,
                "private_key":      server_private_key,
                "listen_port":      listen_port,
                "address_pool_ipv4": address_pool_ipv4,
                "address_pool_ipv6": address_pool_ipv6,
                "clients":          clients,
            }

        except Exception as e:
            logger.error(f"Failed to discover remote server: {e}", exc_info=True)
            return None
