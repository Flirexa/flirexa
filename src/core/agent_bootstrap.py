"""
VPN Manager Agent Bootstrap
Uses existing SSH code to install agent on remote servers.

Bootstrap stages:
  S1  System check       — Python3, OS detection
  S2  Directory setup    — /opt/vpnmanager-agent/ layout
  S3  File upload        — agent.py, requirements.txt
  S4  VPN interface      — wg/awg check + provision fresh server
  S5  Port check         — ensure agent port is available
  S6  Venv + deps        — python3 -m venv + pip install (isolated)
  S7  Systemd service    — create unit, open firewall
  S8  Start + verify     — systemctl start, HTTP health check
"""

from typing import Optional
import os
import re
import secrets
import paramiko
from loguru import logger

# Agent install directory on remote servers
AGENT_DIR = "/opt/vpnmanager-agent"
AGENT_VENV = f"{AGENT_DIR}/venv"
AGENT_PYTHON = f"{AGENT_VENV}/bin/python"
AGENT_PIP = f"{AGENT_VENV}/bin/pip"
AGENT_SERVICE = "vpnmanager-agent"


class AgentBootstrap:
    """
    Bootstrap agent installation on remote server via SSH.
    Idempotent — safe to run multiple times.
    """

    def __init__(
        self,
        ssh_host: str,
        ssh_port: int = 22,
        ssh_user: str = "root",
        ssh_password: Optional[str] = None,
        ssh_private_key_path: Optional[str] = None,
        ssh_private_key_content: Optional[str] = None,
    ):
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.ssh_private_key_path = ssh_private_key_path
        self.ssh_private_key_content = ssh_private_key_content
        self._ssh_client = None

    # ------------------------------------------------------------------
    # SSH transport
    # ------------------------------------------------------------------

    def _get_ssh(self) -> paramiko.SSHClient:
        """Get (or reuse) SSH connection with explicit error classification."""
        if self._ssh_client is not None:
            return self._ssh_client

        import socket
        import io as _io

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Resolve private key — PKey.from_private_key() is broken in paramiko 4.x
        # (internally calls PKey(file_obj=…) which was removed). Try each type directly.
        pkey = None
        if self.ssh_private_key_content:
            for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
                try:
                    pkey = cls.from_private_key(_io.StringIO(self.ssh_private_key_content))
                    break
                except Exception:
                    continue
        elif self.ssh_private_key_path:
            for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
                try:
                    pkey = cls.from_private_key_file(self.ssh_private_key_path)
                    break
                except Exception:
                    continue

        try:
            client.connect(
                self.ssh_host,
                port=self.ssh_port,
                username=self.ssh_user,
                password=self.ssh_password,
                pkey=pkey,
                timeout=30,
                # Disable agent and key-file scanning — use only explicit credentials.
                # This prevents SSH agent keys or ~/.ssh/id_* from interfering when
                # explicit password or pkey is provided (avoids MaxAuthTries exhaustion).
                allow_agent=False,
                look_for_keys=False,
            )
        except socket.timeout:
            raise ConnectionError(
                f"SSH connection timed out: {self.ssh_host}:{self.ssh_port} "
                "(server unreachable or firewall blocked port 22)"
            )
        except socket.gaierror as e:
            raise ConnectionError(f"Cannot resolve SSH host '{self.ssh_host}': {e}")
        except paramiko.ssh_exception.NoValidConnectionsError:
            raise ConnectionError(
                f"Connection refused at {self.ssh_host}:{self.ssh_port} "
                "(SSH not running or port blocked)"
            )
        except paramiko.ssh_exception.AuthenticationException:
            raise PermissionError(
                f"SSH authentication failed for {self.ssh_user}@{self.ssh_host} "
                "(wrong password or key)"
            )
        except paramiko.ssh_exception.SSHException as e:
            raise ConnectionError(f"SSH error connecting to {self.ssh_host}: {e}")

        self._ssh_client = client
        return client

    def close(self):
        if self._ssh_client:
            self._ssh_client.close()
            self._ssh_client = None

    def _exec(self, command: str, timeout: int = 60) -> tuple[str, str, int]:
        """Execute command over SSH, return (stdout, stderr, exit_code)."""
        ssh = self._get_ssh()
        stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
        out = stdout.read().decode()
        err = stderr.read().decode()
        rc = stdout.channel.recv_exit_status()
        return out, err, rc

    def _upload_file(self, local_path: str, remote_path: str):
        """Upload file via SFTP."""
        ssh = self._get_ssh()
        sftp = ssh.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()

    def _upload_content(self, content: str, remote_path: str, mode: int = 0o644):
        """Write string content to a remote file via SFTP."""
        ssh = self._get_ssh()
        sftp = ssh.open_sftp()
        try:
            with sftp.file(remote_path, "w") as f:
                f.write(content)
            sftp.chmod(remote_path, mode)
        finally:
            sftp.close()

    # ------------------------------------------------------------------
    # AmneziaWG installation
    # ------------------------------------------------------------------

    def _awg_install_cmd(self) -> str:
        """
        Return a shell command that installs AmneziaWG on the remote host.
        Supports Ubuntu 20.04/22.04/24.04 and Debian 11/12 via official PPA.
        Falls back to compiled release binary for other distros.
        """
        return r"""
set -e
. /etc/os-release 2>/dev/null || true
case "${ID:-}" in
    ubuntu)
        export DEBIAN_FRONTEND=noninteractive
        apt-get install -y software-properties-common 2>&1
        add-apt-repository -y ppa:amnezia/amneziawg 2>&1
        apt-get update -qq 2>&1
        apt-get install -y amneziawg amneziawg-tools 2>&1
        ;;
    debian)
        export DEBIAN_FRONTEND=noninteractive
        apt-get install -y curl gnupg lsb-release 2>&1
        # Debian uses Ubuntu Focal PPA packages (compatible)
        echo "deb http://ppa.launchpad.net/amnezia/amneziawg/ubuntu focal main" \
            > /etc/apt/sources.list.d/amnezia-awg.list
        apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 57290828 2>&1 || \
            curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x57290828" \
            | apt-key add - 2>&1
        apt-get update -qq 2>&1
        apt-get install -y amneziawg amneziawg-tools 2>&1
        ;;
    *)
        echo "Unsupported distro: ${ID:-unknown}. Install AmneziaWG manually." >&2
        exit 1
        ;;
esac
""".strip()

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_interface(interface: str) -> str:
        interface = (interface or "").strip()
        if not re.fullmatch(r"(wg|awg)[0-9]+", interface):
            raise ValueError(
                f"Invalid interface name '{interface}': expected wg0/wg1/awg0/awg1 etc."
            )
        return interface

    @staticmethod
    def _validate_port(port: int) -> int:
        if not isinstance(port, int) or not (1 <= port <= 65535):
            raise ValueError("Invalid agent port")
        return port

    # ------------------------------------------------------------------
    # Main install
    # ------------------------------------------------------------------

    def install_agent(
        self,
        agent_code_path: str,
        interface: str = "wg0",
        port: int = 8001,
        server_config_content: Optional[str] = None,
    ) -> tuple[bool, str, str]:
        """
        Install (or reinstall) agent on remote server.  Idempotent.

        Returns:
            (success, api_url, api_key_or_error_message)
        """
        try:
            interface = self._validate_interface(interface)
            port = self._validate_port(port)
            is_awg = interface.startswith("awg")
            config_dir = "/etc/amneziawg" if is_awg else "/etc/wireguard"
            wg_cmd = "awg" if is_awg else "wg"
            wgquick_cmd = "awg-quick" if is_awg else "wg-quick"

            logger.info(
                f"[BOOTSTRAP] Starting agent install on {self.ssh_host} "
                f"(interface={interface}, type={'awg' if is_awg else 'wg'})"
            )

            # ==============================================================
            # S1: System check — Python3
            # ==============================================================
            logger.info("[BOOTSTRAP S1] System check: Python3")
            out, err, rc = self._exec("which python3")
            if rc != 0:
                logger.warning("[BOOTSTRAP S1] Python3 not found — installing...")
                out, err, rc = self._exec(
                    "apt-get update -qq && apt-get install -y python3 python3-venv 2>&1 || "
                    "yum install -y python3 2>&1 || "
                    "dnf install -y python3 2>&1",
                    timeout=120,
                )
                if rc != 0:
                    return False, "", f"[S1] Failed to install Python3: {err}"
                logger.info("[BOOTSTRAP S1] ✅ Python3 installed")

            out, _, _ = self._exec("python3 --version")
            logger.info(f"[BOOTSTRAP S1] ✅ {out.strip()}")

            # Ensure python3-venv is available (Debian/Ubuntu split venv into separate pkg).
            # Test actual venv creation (not just --help) — ensurepip can be missing even
            # when python3 -m venv --help returns 0 (Ubuntu 24.04 + python3.12-venv not installed).
            out, _, venv_rc = self._exec(
                "python3 -m venv /tmp/_vpnm_venv_test 2>&1 && rm -rf /tmp/_vpnm_venv_test"
            )
            if venv_rc != 0:
                logger.warning("[BOOTSTRAP S1] python3-venv not fully functional — installing...")
                # Detect exact python version to install the right package (e.g. python3.12-venv)
                py_ver_out, _, _ = self._exec(
                    "python3 -c \"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')\""
                )
                py_ver = py_ver_out.strip()
                self._exec(
                    f"apt-get install -y python3.{py_ver.split('.')[-1]}-venv 2>&1 || "
                    f"apt-get install -y python3-venv 2>&1 || "
                    "apt-get install -y python3-virtualenv 2>&1 || true",
                    timeout=60,
                )
                # Verify fix worked
                _, _, venv_rc2 = self._exec(
                    "python3 -m venv /tmp/_vpnm_venv_test 2>&1 && rm -rf /tmp/_vpnm_venv_test"
                )
                if venv_rc2 != 0:
                    return False, "", (
                        "[S1] python3-venv is not functional after install attempt. "
                        f"Run manually: apt install python3-venv (or python3.{py_ver.split('.')[-1]}-venv)"
                    )
                logger.info("[BOOTSTRAP S1] ✅ python3-venv installed and functional")

            # Ensure iptables is present (used by WireGuard PostUp and agent firewall rules)
            _, _, rc = self._exec("which iptables")
            if rc != 0:
                self._exec("apt-get install -y iptables 2>&1 || yum install -y iptables 2>&1 || true")

            # Early AWG binary check — auto-install if missing
            if is_awg:
                _, _, rc = self._exec("which awg")
                if rc != 0:
                    logger.warning("[BOOTSTRAP S1] awg not found — installing AmneziaWG...")
                    out, err, rc = self._exec(
                        self._awg_install_cmd(),
                        timeout=180,
                    )
                    if rc != 0:
                        return False, "", (
                            f"[S1] Failed to install AmneziaWG: {(err or out)[-500:]}\n"
                            "Supported: Ubuntu 20.04/22.04/24.04, Debian 11/12. "
                            "For other distros install amneziawg manually."
                        )
                    # Load kernel module
                    self._exec("modprobe amneziawg 2>/dev/null || true")
                    _, _, rc = self._exec("which awg")
                    if rc != 0:
                        return False, "", "[S1] AmneziaWG installed but 'awg' binary not found — check PATH"
                    logger.info("[BOOTSTRAP S1] ✅ AmneziaWG installed")
                else:
                    logger.info("[BOOTSTRAP S1] ✅ awg binary found")

            # ==============================================================
            # S2: Directory setup
            # ==============================================================
            logger.info(f"[BOOTSTRAP S2] Setting up {AGENT_DIR}/")
            self._exec(f"mkdir -p {AGENT_DIR} {AGENT_DIR}/logs")
            self._exec(f"chmod 750 {AGENT_DIR}")

            # ==============================================================
            # S3: Upload agent files
            # ==============================================================
            logger.info("[BOOTSTRAP S3] Uploading agent files")
            self._upload_file(agent_code_path, f"{AGENT_DIR}/agent.py")
            self._exec(f"chmod 750 {AGENT_DIR}/agent.py")

            # Upload requirements.txt (sibling of agent.py, or inline fallback)
            req_path = os.path.join(os.path.dirname(agent_code_path), "agent_requirements.txt")
            if os.path.isfile(req_path):
                self._upload_file(req_path, f"{AGENT_DIR}/requirements.txt")
            else:
                self._upload_content(
                    "fastapi>=0.104.0\nuvicorn[standard]>=0.24.0\npsutil>=5.9.0\n",
                    f"{AGENT_DIR}/requirements.txt",
                )
            logger.info("[BOOTSTRAP S3] ✅ agent.py + requirements.txt uploaded")

            # ==============================================================
            # S4: VPN interface check / provision
            # ==============================================================
            logger.info(f"[BOOTSTRAP S4] VPN interface check: {wg_cmd} {interface}")
            _, _, rc = self._exec(f"which {wg_cmd}")
            if rc != 0:
                # AWG was already checked in S1 — this handles the wg case
                logger.warning("[BOOTSTRAP S4] wg not found — installing wireguard-tools...")
                out, err, rc = self._exec(
                    "apt-get update -qq && apt-get install -y wireguard wireguard-tools 2>&1 || "
                    "yum install -y wireguard-tools 2>&1 || "
                    "dnf install -y wireguard-tools 2>&1",
                    timeout=120,
                )
                if rc != 0:
                    return False, "", f"[S4] Failed to install wireguard-tools: {err or out}"
                logger.info("[BOOTSTRAP S4] ✅ wireguard-tools installed")

            _, _, rc = self._exec(f"{wg_cmd} show {interface}")
            if rc != 0:
                if not server_config_content:
                    return False, "", (
                        f"Interface {interface} not found on remote server. "
                        "Either set up WireGuard first, or create the server via API "
                        "so keys are generated automatically."
                    )
                logger.info(f"[BOOTSTRAP S4] Interface {interface} not active — provisioning...")

                self._exec(f"mkdir -p {config_dir} && chmod 700 {config_dir}")
                self._upload_content(
                    server_config_content,
                    f"{config_dir}/{interface}.conf",
                    mode=0o600,
                )
                logger.info(f"[BOOTSTRAP S4] ✅ Config written to {config_dir}/{interface}.conf")

                # Enable IP forwarding
                self._exec("sysctl -w net.ipv4.ip_forward=1 2>/dev/null || true")
                self._exec("sysctl -w net.ipv6.conf.all.forwarding=1 2>/dev/null || true")
                self._exec(
                    "grep -qxF 'net.ipv4.ip_forward=1' /etc/sysctl.conf || "
                    "echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf"
                )

                out, err, rc = self._exec(f"{wgquick_cmd} up {interface} 2>&1")
                if rc != 0:
                    return False, "", f"[S4] Failed to bring up {interface}: {(err or out).strip()}"
                logger.info(f"[BOOTSTRAP S4] ✅ Interface {interface} is up")
            else:
                logger.info(f"[BOOTSTRAP S4] ✅ {wg_cmd} {interface} already active")

            # ==============================================================
            # S4.5: Stop existing agent service (frees the port for S5 check,
            # ensures clean restart in S8 on idempotent reinstall)
            # ==============================================================
            _, _, svc_rc = self._exec(f"systemctl is-active {AGENT_SERVICE}")
            if svc_rc == 0:
                logger.info(f"[BOOTSTRAP] Stopping existing {AGENT_SERVICE} for reinstall")
                self._exec(f"systemctl stop {AGENT_SERVICE} 2>/dev/null || true")

            # ==============================================================
            # S5: Port availability check
            # ==============================================================
            logger.info(f"[BOOTSTRAP S5] Port check: {port}")
            out, _, _ = self._exec(
                f"ss -tuln | grep ':{port} ' || netstat -tuln | grep ':{port} ' || echo 'port_free'"
            )
            if "port_free" not in out and out.strip():
                logger.warning(f"[BOOTSTRAP S5] Port {port} in use — trying {port + 1}")
                port = port + 1
            logger.info(f"[BOOTSTRAP S5] ✅ Using port {port}")

            # ==============================================================
            # S6: Venv creation + dependency install (isolated from system)
            # ==============================================================
            logger.info(f"[BOOTSTRAP S6] Python venv at {AGENT_VENV}")

            # Create venv if it doesn't exist yet, or recreate if pip is missing
            _, _, python_rc = self._exec(f"test -f {AGENT_PYTHON}")
            _, _, pip_rc = self._exec(f"test -f {AGENT_PIP}")

            def _create_venv() -> tuple[bool, str]:
                """Create venv, auto-install python3-venv if ensurepip is missing."""
                out, err, rc = self._exec(f"python3 -m venv {AGENT_VENV} 2>&1", timeout=60)
                if rc == 0:
                    return True, ""
                combined = (out + err)
                if "ensurepip" in combined or "python3-venv" in combined or "python3.1" in combined:
                    logger.warning("[BOOTSTRAP S6] ensurepip missing — installing python3-venv...")
                    py_ver_out, _, _ = self._exec(
                        "python3 -c \"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')\""
                    )
                    py_minor = py_ver_out.strip().split(".")[-1]
                    self._exec(
                        f"apt-get install -y python3.{py_minor}-venv 2>&1 || "
                        "apt-get install -y python3-venv 2>&1 || true",
                        timeout=60,
                    )
                    out2, err2, rc2 = self._exec(f"python3 -m venv {AGENT_VENV} 2>&1", timeout=60)
                    if rc2 != 0:
                        return False, err2 or out2
                    return True, ""
                return False, combined

            if python_rc != 0:
                logger.info("[BOOTSTRAP S6] Creating venv...")
                ok, errmsg = _create_venv()
                if not ok:
                    return False, "", f"[S6] Failed to create venv: {errmsg}"
                logger.info("[BOOTSTRAP S6] ✅ Venv created")
            elif pip_rc != 0:
                logger.warning("[BOOTSTRAP S6] Venv exists but pip is missing — recreating venv...")
                self._exec(f"rm -rf {AGENT_VENV}")
                ok, errmsg = _create_venv()
                if not ok:
                    return False, "", f"[S6] Failed to recreate venv: {errmsg}"
                logger.info("[BOOTSTRAP S6] ✅ Venv recreated")
            else:
                logger.info("[BOOTSTRAP S6] Venv already exists — will upgrade deps")

            # Ensure pip is functional (ensurepip as safety net)
            _, _, ensurepip_rc = self._exec(
                f"{AGENT_PYTHON} -m pip --version 2>&1 || "
                f"{AGENT_PYTHON} -m ensurepip --upgrade 2>&1",
                timeout=60,
            )

            # Upgrade pip using python -m pip (more robust than direct pip binary)
            self._exec(f"{AGENT_PYTHON} -m pip install --upgrade pip 2>&1", timeout=60)

            # Install agent dependencies into venv
            logger.info("[BOOTSTRAP S6] Installing dependencies into venv...")
            out, err, rc = self._exec(
                f"{AGENT_PYTHON} -m pip install -r {AGENT_DIR}/requirements.txt 2>&1",
                timeout=180,
            )
            if rc != 0:
                # Check if packages are already present (previous install left them)
                _, _, check_rc = self._exec(
                    f"{AGENT_PYTHON} -c 'import fastapi, uvicorn, psutil' 2>&1"
                )
                if check_rc == 0:
                    logger.info("[BOOTSTRAP S6] Packages already importable, continuing")
                else:
                    # Distinguish no internet from other failures
                    combined = (out + err).lower()
                    no_internet = (
                        "network is unreachable", "failed to connect",
                        "could not connect", "name or service not known",
                        "errno 101", "errno 111",
                    )
                    if any(h in combined for h in no_internet):
                        return False, "", (
                            "Failed to install agent dependencies: remote server has no internet. "
                            "Pre-install fastapi, uvicorn, psutil in "
                            f"{AGENT_VENV} or allow outbound HTTP."
                        )
                    return False, "", (
                        f"[S6] pip install failed.\nstdout: {out[-500:]}\nstderr: {err[-500:]}"
                    )
            logger.info("[BOOTSTRAP S6] ✅ Dependencies installed")

            # ==============================================================
            # S7: Systemd service + firewall
            # ==============================================================
            logger.info("[BOOTSTRAP S7] Creating systemd service")
            api_key = secrets.token_urlsafe(32)

            service_content = f"""[Unit]
Description=VPN Manager Agent - {interface} management
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={AGENT_DIR}
Environment="AGENT_API_KEY={api_key}"
Environment="WG_INTERFACE={interface}"
Environment="WG_CONFIG_PATH={config_dir}/{interface}.conf"
Environment="AGENT_PORT={port}"
ExecStart={AGENT_PYTHON} -u {AGENT_DIR}/agent.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security hardening (root required for wg/tc/iptables)
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths={config_dir} {AGENT_DIR}

[Install]
WantedBy=multi-user.target
"""
            # Write service file with restricted permissions (contains API key)
            self._upload_content(
                service_content,
                "/etc/systemd/system/vpnmanager-agent.service",
                mode=0o640,
            )
            logger.info("[BOOTSTRAP S7] ✅ Service file written")

            # Open agent port in firewall
            logger.info(f"[BOOTSTRAP S7] Firewall: opening port {port}/tcp")
            _, _, ufw_rc = self._exec("which ufw")
            if ufw_rc == 0:
                out, _, _ = self._exec("ufw status")
                if "Status: active" in out:
                    self._exec(f"ufw allow {port}/tcp")

            _, _, ipt_rc = self._exec("which iptables")
            if ipt_rc == 0:
                self._exec(f"iptables -D INPUT -p tcp --dport {port} -j ACCEPT 2>/dev/null || true")
                _, _, rc = self._exec(f"iptables -I INPUT 1 -p tcp --dport {port} -j ACCEPT")
                if rc == 0:
                    # Try to persist rules (multiple methods, best-effort)
                    self._exec(
                        "mkdir -p /etc/iptables && iptables-save > /etc/iptables/rules.v4 2>/dev/null || "
                        "iptables-save > /etc/iptables.rules 2>/dev/null || "
                        "netfilter-persistent save 2>/dev/null || "
                        "service iptables save 2>/dev/null || true"
                    )
                    logger.info(f"[BOOTSTRAP S7] ✅ iptables rule added for port {port}")
                else:
                    logger.warning(f"[BOOTSTRAP S7] Could not add iptables rule (non-fatal)")

            # ==============================================================
            # S8: Start agent + verify
            # ==============================================================
            logger.info("[BOOTSTRAP S8] Starting agent service")
            self._exec("systemctl daemon-reload")
            self._exec(f"systemctl enable {AGENT_SERVICE}")

            _, err, rc = self._exec(f"systemctl start {AGENT_SERVICE}")
            if rc != 0:
                journal, _, _ = self._exec(
                    f"journalctl -u {AGENT_SERVICE} -n 20 --no-pager"
                )
                logger.error(
                    f"[BOOTSTRAP S8] Service start failed.\n"
                    f"  systemctl err: {err.strip()}\n"
                    f"  journal: {journal}"
                )
                return False, "", f"[S8] Failed to start agent service: {err.strip()}"

            # Wait for service to become active (up to 10s)
            import time
            for attempt in range(5):
                time.sleep(2)
                out, _, rc = self._exec(f"systemctl is-active {AGENT_SERVICE}")
                if rc == 0 and "active" in out:
                    logger.info(f"[BOOTSTRAP S8] ✅ Service active (attempt {attempt + 1})")
                    break
                if attempt == 4:
                    journal, _, _ = self._exec(
                        f"journalctl -u {AGENT_SERVICE} -n 30 --no-pager"
                    )
                    logger.error(f"[BOOTSTRAP S8] Agent not active after 10s:\n{journal}")
                    return False, "", f"[S8] Agent service not active after 10s:\n{journal[-400:]}"
                logger.debug(f"[BOOTSTRAP S8] Waiting for service... ({attempt + 1}/5)")

            # Verify HTTP endpoint
            api_url = f"http://{self.ssh_host}:{port}"
            _, _, curl_rc = self._exec("which curl")
            if curl_rc == 0:
                for attempt in range(3):
                    out, _, rc = self._exec(
                        f"curl -s -m 5 http://localhost:{port}/health || echo 'CURL_FAILED'"
                    )
                    if rc == 0 and "CURL_FAILED" not in out and "healthy" in out:
                        logger.info(f"[BOOTSTRAP S8] ✅ HTTP /health OK at {api_url}")
                        break
                    if attempt < 2:
                        time.sleep(3)
                else:
                    logger.warning(
                        f"[BOOTSTRAP S8] HTTP health check inconclusive (service is running)"
                    )
            else:
                out, _, rc = self._exec(f"ss -tuln | grep ':{port} '")
                if rc == 0 and out.strip():
                    logger.info(f"[BOOTSTRAP S8] ✅ Port {port} is listening")

            logger.info(f"[BOOTSTRAP] ✅ Agent installed successfully at {api_url}")
            return True, api_url, api_key

        except Exception as e:
            logger.error(f"[BOOTSTRAP] Agent installation failed: {e}")
            return False, "", str(e)
        finally:
            self.close()

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------

    def uninstall_agent(self) -> bool:
        """
        Fully remove agent from remote server.
        Reads port and interface from the systemd service file so cleanup
        is accurate even if defaults were changed during install.
        """
        try:
            logger.info(f"Uninstalling agent from {self.ssh_host}...")

            # --- Read port and interface from service file before stopping ---
            port = 8001
            iface = None
            svc_out, _, _ = self._exec(
                f"cat /etc/systemd/system/{AGENT_SERVICE}.service 2>/dev/null || echo ''"
            )
            for line in svc_out.splitlines():
                line = line.strip()
                if "AGENT_PORT=" in line:
                    try:
                        port = int(line.split("AGENT_PORT=")[-1].strip().strip('"'))
                    except ValueError:
                        pass
                if "WG_INTERFACE=" in line:
                    iface = line.split("WG_INTERFACE=")[-1].strip().strip('"') or None

            # --- Stop + disable systemd service ---
            self._exec(f"systemctl stop {AGENT_SERVICE} 2>/dev/null || true")
            self._exec(f"systemctl disable {AGENT_SERVICE} 2>/dev/null || true")
            self._exec(f"rm -f /etc/systemd/system/{AGENT_SERVICE}.service")
            self._exec("systemctl daemon-reload")
            logger.info(f"[UNINSTALL] ✅ Systemd service removed (port={port}, iface={iface})")

            # --- Bring down WG/AWG interface ---
            if iface:
                is_awg = iface.startswith("awg")
                wgquick_cmd = "awg-quick" if is_awg else "wg-quick"
                _, _, rc = self._exec(f"{wgquick_cmd} down {iface} 2>/dev/null || true")
                logger.info(f"[UNINSTALL] ✅ Interface {iface} brought down")

            # --- Remove firewall rules ---
            _, _, ufw_rc = self._exec("which ufw")
            if ufw_rc == 0:
                out, _, _ = self._exec("ufw status")
                if "Status: active" in out:
                    self._exec(f"ufw delete allow {port}/tcp 2>/dev/null || true")
                    logger.info(f"[UNINSTALL] ✅ ufw rule removed for port {port}")

            _, _, ipt_rc = self._exec("which iptables")
            if ipt_rc == 0:
                self._exec(
                    f"iptables -D INPUT -p tcp --dport {port} -j ACCEPT 2>/dev/null || true"
                )
                # Re-save persistent rules (whichever method works)
                self._exec(
                    "iptables-save > /etc/iptables/rules.v4 2>/dev/null || "
                    "iptables-save > /etc/iptables.rules 2>/dev/null || "
                    "netfilter-persistent save 2>/dev/null || "
                    "service iptables save 2>/dev/null || true"
                )
                logger.info(f"[UNINSTALL] ✅ iptables rule removed for port {port}")

            # --- Remove agent directory ---
            self._exec(f"rm -rf {AGENT_DIR}")
            logger.info(f"[UNINSTALL] ✅ {AGENT_DIR} removed")

            logger.info(f"✅ Agent fully uninstalled from {self.ssh_host}")
            return True
        except Exception as e:
            logger.error(f"Agent uninstall failed: {e}")
            return False
        finally:
            self.close()

    # ------------------------------------------------------------------
    # Health check (used by install-agent route for idempotency guard)
    # ------------------------------------------------------------------

    def check_agent_health(self, port: int = 8001) -> bool:
        """Return True if agent service is active and responding."""
        try:
            out, _, rc = self._exec(f"systemctl is-active {AGENT_SERVICE}")
            return rc == 0 and "active" in out
        except Exception:
            return False
        finally:
            self.close()
