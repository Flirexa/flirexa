"""
VPN Management Studio — Proxy Protocol Base Manager

Provides SSH transport and common operations shared by
Hysteria2Manager and TUICManager.

Proxy protocols (Hysteria2, TUIC) are NOT VPN — they do not maintain
per-peer IP routing tables. Clients access the proxy via
password/UUID auth and the server forwards traffic to the internet.
"""

import io
import time
import socket
import subprocess
from typing import Optional, Tuple
from urllib.parse import quote
from loguru import logger


def build_proxy_uri(
    scheme: str,
    user: str,
    password: str,
    host: str,
    port: int,
    params: str = "",
    label: str = "",
) -> str:
    """
    Build a proxy client URI with correct RFC-3986 encoding.

    - user / password are percent-encoded (handles spaces, @, :, # etc.)
    - host is assumed to be a clean IP or domain (not encoded)
    - params is appended as-is (caller must pre-encode query values if needed)
    - label (profile name) is percent-encoded and appended as URI fragment

    Examples:
        hysteria2://user:pass@1.2.3.4:8443?sni=1.2.3.4&insecure=1#My%20Profile
        tuic://uuid:pass@1.2.3.4:8444?congestion_control=bbr&alpn=h3#Alice
    """
    enc_user = quote(user, safe="")
    enc_pass = quote(password, safe="")
    uri = f"{scheme}://{enc_user}:{enc_pass}@{host}:{port}"
    if params:
        uri += f"?{params}"
    if label:
        uri += f"#{quote(label, safe='')}"
    return uri


class ProxyBaseManager:
    """
    Base class for proxy protocol managers (Hysteria2, TUIC).

    Provides:
    - SSH transport via Paramiko (same pattern as WireGuardManager)
    - Common systemd service operations
    - Config file read/write over SSH
    - Port listening check
    """

    def __init__(
        self,
        config_path: str,
        service_name: str,
        ssh_host: Optional[str] = None,
        ssh_port: int = 22,
        ssh_user: str = "root",
        ssh_password: Optional[str] = None,
        ssh_private_key: Optional[str] = None,
    ):
        self.config_path = config_path
        self.service_name = service_name
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.ssh_private_key = ssh_private_key
        self._ssh = None

    # ── SSH transport ─────────────────────────────────────────────────────────

    def _get_ssh(self):
        """Return open Paramiko SSH client, reconnecting if needed."""
        import paramiko
        if self._ssh and self._ssh.get_transport() and self._ssh.get_transport().is_active():
            return self._ssh
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs = {
            "hostname": self.ssh_host,
            "port": self.ssh_port,
            "username": self.ssh_user,
            "timeout": 15,
            "banner_timeout": 15,
            "auth_timeout": 15,
        }
        if self.ssh_private_key:
            key_file = io.StringIO(self.ssh_private_key)
            try:
                pkey = paramiko.RSAKey.from_private_key(key_file)
            except paramiko.ssh_exception.SSHException:
                key_file.seek(0)
                pkey = paramiko.Ed25519Key.from_private_key(key_file)
            connect_kwargs["pkey"] = pkey
        elif self.ssh_password:
            connect_kwargs["password"] = self.ssh_password
        client.connect(**connect_kwargs)
        self._ssh = client
        return client

    def _run(self, cmd: str, timeout: int = 30, check: bool = False) -> Tuple[int, str, str]:
        """
        Run command over SSH (or locally if no ssh_host).
        Returns (exit_code, stdout, stderr).
        """
        if not self.ssh_host:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()

        ssh = self._get_ssh()
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()

        if check and exit_code != 0:
            raise RuntimeError(f"Command failed [{exit_code}]: {cmd}\nSTDERR: {err}")
        return exit_code, out, err

    def _write_file(self, remote_path: str, content: str) -> None:
        """Write content to remote (or local) file atomically (write→rename)."""
        if not self.ssh_host:
            import os, tempfile
            dir_path = os.path.dirname(remote_path)
            os.makedirs(dir_path, exist_ok=True)
            # Atomic write: write to sibling temp file, then rename
            with tempfile.NamedTemporaryFile("w", dir=dir_path, delete=False, suffix=".tmp") as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            os.replace(tmp_path, remote_path)  # atomic on POSIX
            return
        # Remote: write to .tmp path, then rename via shell
        ssh = self._get_ssh()
        sftp = ssh.open_sftp()
        tmp_path = remote_path + ".tmp"
        try:
            dir_path = remote_path.rsplit("/", 1)[0]
            # Always ensure directory exists — sftp.stat may raise IOError (not
            # FileNotFoundError) on some paramiko/sshd combinations, so mkdir-p
            # unconditionally is simpler and safe (no-op if dir already exists).
            self._run(f"mkdir -p {dir_path}")
            with sftp.open(tmp_path, "w") as f:
                f.write(content)
        finally:
            sftp.close()
        # Atomic rename via SSH
        self._run(f"mv -f {tmp_path} {remote_path}")

    def _read_file(self, remote_path: str) -> Optional[str]:
        """Read content from remote (or local) file. Returns None if not found."""
        if not self.ssh_host:
            try:
                with open(remote_path) as f:
                    return f.read()
            except FileNotFoundError:
                return None
        code, out, _ = self._run(f"cat {remote_path} 2>/dev/null")
        return out if code == 0 and out else None

    def close(self):
        """Close SSH connection."""
        if self._ssh:
            try:
                self._ssh.close()
            except Exception:
                pass
            self._ssh = None

    # ── Systemd helpers ───────────────────────────────────────────────────────

    def is_service_active(self) -> bool:
        """Return True if systemd service is active (running)."""
        code, out, _ = self._run(f"systemctl is-active {self.service_name} 2>/dev/null")
        return out.strip() == "active"

    def start_service(self) -> bool:
        code, _, _ = self._run(f"systemctl start {self.service_name}")
        return code == 0

    def stop_service(self) -> bool:
        code, _, _ = self._run(f"systemctl stop {self.service_name}")
        return code == 0

    def purge_service(self) -> bool:
        """Stop, disable, and remove the per-interface systemd unit + config file."""
        self._run(f"systemctl stop {self.service_name} 2>/dev/null")
        self._run(f"systemctl disable {self.service_name} 2>/dev/null")
        self._run(f"rm -f /etc/systemd/system/{self.service_name}.service")
        self._run("systemctl daemon-reload 2>/dev/null")
        # Remove per-interface config if it's a per-interface path
        if self.config_path and self.config_path != "/etc/hysteria/config.yaml":
            self._run(f"rm -f {self.config_path}")
        return True

    def restart_service(self) -> bool:
        code, _, _ = self._run(f"systemctl restart {self.service_name}")
        time.sleep(1)
        return code == 0

    def enable_service(self) -> bool:
        code, _, _ = self._run(f"systemctl enable {self.service_name}")
        return code == 0

    def get_service_status(self) -> dict:
        """Return dict with service status details."""
        _, active, _ = self._run(f"systemctl is-active {self.service_name} 2>/dev/null")
        _, enabled, _ = self._run(f"systemctl is-enabled {self.service_name} 2>/dev/null")
        _, status_out, _ = self._run(
            f"systemctl status {self.service_name} --no-pager -l 2>/dev/null | head -20"
        )
        return {
            "active": active.strip() == "active",
            "enabled": enabled.strip() in ("enabled", "enabled-runtime"),
            "status_output": status_out,
        }

    def is_port_listening(self, port: int, proto: str = "udp") -> bool:
        """Check if a UDP/TCP port is bound on the remote server."""
        if proto == "udp":
            code, out, _ = self._run(f"ss -uln sport = :{port} 2>/dev/null | grep :{port}")
        else:
            code, out, _ = self._run(f"ss -tln sport = :{port} 2>/dev/null | grep :{port}")
        return bool(out.strip())

    def get_system_metrics(self) -> dict:
        """Return basic CPU/mem/disk metrics from remote server."""
        _, cpu, _ = self._run(
            "grep 'cpu ' /proc/stat | awk '{u=$2+$4; t=$2+$3+$4+$5; if (NR==1){u1=u;t1=t} else {printf \"%.1f\", (u-u1)*100/(t-t1)}}' <(grep 'cpu ' /proc/stat) <(sleep 0.1; grep 'cpu ' /proc/stat)"
        )
        _, mem, _ = self._run(
            "free | awk '/Mem:/{printf \"%.1f\", $3/$2*100}'"
        )
        _, disk, _ = self._run(
            "df / | awk 'NR==2{gsub(\"%\",\"\",$5); print $5}'"
        )
        try:
            return {
                "cpu_percent": float(cpu) if cpu else None,
                "memory_percent": float(mem) if mem else None,
                "disk_percent": float(disk) if disk else None,
            }
        except (ValueError, TypeError):
            return {}

    # ── TLS certificate helpers ───────────────────────────────────────────────

    def generate_self_signed_cert(self, cert_path: str, key_path: str,
                                   domain: Optional[str] = None) -> bool:
        """
        Generate a self-signed TLS certificate on the remote server.
        Includes SAN (Subject Alternative Names) for both IP and DNS so
        that modern TLS clients accept the certificate without errors.
        """
        import re as _re
        cn = domain or self.ssh_host or "proxy.local"
        # Determine SAN type: IP address or DNS name
        is_ip = bool(_re.match(r'^\d{1,3}(\.\d{1,3}){3}$', cn))
        san = f"IP:{cn}" if is_ip else f"DNS:{cn}"
        cert_dir = cert_path.rsplit("/", 1)[0]
        self._run(f"mkdir -p {cert_dir}")
        cmd = (
            f"openssl req -x509 -newkey rsa:2048 -keyout {key_path} "
            f"-out {cert_path} -days 3650 -nodes "
            f'-subj "/CN={cn}" '
            f'-addext "subjectAltName={san}" 2>/dev/null'
        )
        code, _, err = self._run(cmd, timeout=30)
        if code != 0:
            # Fallback for older openssl that doesn't support -addext
            cmd_fallback = (
                f"openssl req -x509 -newkey rsa:2048 -keyout {key_path} "
                f"-out {cert_path} -days 3650 -nodes "
                f'-subj "/CN={cn}" 2>/dev/null'
            )
            code, _, err = self._run(cmd_fallback, timeout=30)
            if code != 0:
                logger.error(f"Self-signed cert generation failed: {err}")
                return False
            logger.warning("Generated cert without SAN (old openssl); clients may need insecure=1")
        self._run(f"chmod 600 {key_path} {cert_path}")
        return True

    def cert_exists(self, cert_path: str, key_path: str) -> bool:
        """Check if certificate and key files exist on remote."""
        code1, _, _ = self._run(f"test -f {cert_path}")
        code2, _, _ = self._run(f"test -f {key_path}")
        return code1 == 0 and code2 == 0
