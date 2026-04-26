"""
VPN Management Studio — TUIC Manager

TUIC (Tailored UDP Internet Connection) is a QUIC-based proxy protocol.
Like Hysteria2, it is a forward proxy — NOT a VPN.
Clients authenticate via UUID + password; the server forwards traffic.

Default paths:
  config:  /etc/tuic/config.json
  certs:   /etc/tuic/server.crt + server.key
  service: tuic-server.service
  binary:  /usr/local/bin/tuic-server  (or tuic)

Official releases: https://github.com/EAimTY/tuic/releases
We use the tuic-server binary (server-side component of TUIC v5).
"""

import json
import re
import secrets
import string
import uuid as _uuid_mod
from typing import Optional, Dict, List, Any

from loguru import logger
from .proxy_base import ProxyBaseManager, build_proxy_uri


DEFAULT_CONFIG_PATH  = "/etc/tuic/config.json"
DEFAULT_CERT_PATH    = "/etc/tuic/server.crt"
DEFAULT_KEY_PATH     = "/etc/tuic/server.key"
DEFAULT_SERVICE_NAME = "tuic-server"
DEFAULT_PORT         = 8444


def _random_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _new_uuid() -> str:
    return str(_uuid_mod.uuid4())


class TUICManager(ProxyBaseManager):
    """
    Manages TUIC v5 proxy server installation and configuration.

    Server config is JSON; each user is identified by UUID + password.
    When clients are added/removed the config is rewritten and the
    service restarted.
    """

    def __init__(
        self,
        config_path: str = DEFAULT_CONFIG_PATH,
        cert_path: str = DEFAULT_CERT_PATH,
        key_path: str = DEFAULT_KEY_PATH,
        service_name: str = DEFAULT_SERVICE_NAME,
        listen_port: int = DEFAULT_PORT,
        domain: Optional[str] = None,
        tls_mode: str = "self_signed",   # self_signed | manual
        ssh_host: Optional[str] = None,
        ssh_port: int = 22,
        ssh_user: str = "root",
        ssh_password: Optional[str] = None,
        ssh_private_key: Optional[str] = None,
    ):
        super().__init__(
            config_path=config_path,
            service_name=service_name,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            ssh_password=ssh_password,
            ssh_private_key=ssh_private_key,
        )
        self.cert_path = cert_path
        self.key_path = key_path
        self.listen_port = listen_port
        self.domain = domain
        self.tls_mode = tls_mode

    # ── Binary / installation check ───────────────────────────────────────────

    def is_installed(self) -> bool:
        code, _, _ = self._run(
            "which tuic-server 2>/dev/null || which tuic 2>/dev/null "
            "|| test -f /usr/local/bin/tuic-server || test -f /usr/local/bin/tuic"
        )
        return code == 0

    def _get_binary(self) -> str:
        """Return tuic-server or tuic depending on what's installed."""
        code, _, _ = self._run("which tuic-server 2>/dev/null")
        if code == 0:
            return "tuic-server"
        code, _, _ = self._run("test -f /usr/local/bin/tuic-server")
        if code == 0:
            return "/usr/local/bin/tuic-server"
        return "tuic"

    def get_version(self) -> Optional[str]:
        bin_ = self._get_binary()
        code, out, _ = self._run(f"{bin_} --version 2>/dev/null | head -1")
        if code == 0 and out:
            m = re.search(r'v?(\d+\.\d+[\.\d]*)', out)
            return m.group(1) if m else out.strip()
        return None

    def install(self, log_cb=None) -> bool:
        """
        Install TUIC server binary from the latest GitHub release.
        Detects CPU arch, downloads the correct binary, installs to
        /usr/local/bin/tuic-server, and creates a systemd service.
        """
        msg = f"Installing TUIC on {self.ssh_host or 'local'}..."
        logger.info(msg)
        if log_cb:
            log_cb(f"⬇ {msg}")

        install_script = r"""#!/bin/bash
set -e
ARCH=$(uname -m)
case $ARCH in
  x86_64)  ARCH_SUFFIX="x86_64-unknown-linux-musl" ;;
  aarch64) ARCH_SUFFIX="aarch64-unknown-linux-musl" ;;
  *)       echo "Unsupported arch: $ARCH"; exit 1 ;;
esac
# tuic-protocol/tuic repo, tag format: tuic-server-X.Y.Z
# binary name: tuic-server-X.Y.Z-ARCH
LATEST=$(curl -fsSL https://api.github.com/repos/tuic-protocol/tuic/releases/latest 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null)
if [ -z "$LATEST" ]; then
  # Fallback to known stable version
  LATEST="tuic-server-1.0.0"
fi
VERSION="${LATEST#tuic-server-}"
URL="https://github.com/tuic-protocol/tuic/releases/download/${LATEST}/tuic-server-${VERSION}-${ARCH_SUFFIX}"
echo "Downloading TUIC ${VERSION} for $ARCH..."
curl -fsSL -o /usr/local/bin/tuic-server "$URL"
chmod +x /usr/local/bin/tuic-server
mkdir -p /etc/tuic
echo "TUIC ${VERSION} installed at /usr/local/bin/tuic-server"
"""

        systemd_unit = f"""[Unit]
Description=TUIC Proxy Server
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/tuic-server -c {self.config_path}
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
"""

        try:
            # Write and run install script
            self._write_file("/tmp/install_tuic.sh", install_script)
            code, out, err = self._run("bash /tmp/install_tuic.sh 2>&1", timeout=180)
            if code != 0:
                logger.error(f"TUIC install failed: {err or out}")
                if log_cb:
                    log_cb(f"✗ Install failed: {(err or out)[:200]}")
                return False

            # Write systemd unit
            self._write_file(f"/etc/systemd/system/{self.service_name}.service", systemd_unit)
            self._run("systemctl daemon-reload")
            if log_cb:
                log_cb("✓ TUIC binary installed")
            return True

        except Exception as e:
            logger.error(f"TUIC install error: {e}")
            if log_cb:
                log_cb(f"✗ Install error: {e}")
            return False

    # ── Config generation ─────────────────────────────────────────────────────

    def generate_server_config(self, clients: List[Dict[str, str]]) -> str:
        """
        Generate TUIC server config JSON.

        clients: list of {"uuid": str, "password": str}
        """
        users = {
            c["uuid"]: c["password"]
            for c in clients
            if c.get("uuid") and c.get("password")
        }

        # TUIC requires UUID keys — add a placeholder UUID so service can start
        # before any real clients are created (empty users map causes startup failure)
        if not users:
            users = {str(_uuid_mod.UUID("00000000-0000-0000-0000-000000000001")): _random_password(32)}

        cfg: Dict[str, Any] = {
            "server": f"[::]:{ self.listen_port}",
            "users": users,
            "certificate": self.cert_path,
            "private_key": self.key_path,
            "congestion_control": "bbr",
            "alpn": ["h3"],
            "udp_relay_ipv6": True,
            "zero_rtt_handshake": False,
            "auth_timeout": "3s",
            "max_idle_time": "10s",
            "log_level": "warn",
        }

        return json.dumps(cfg, indent=2)

    def generate_client_config(
        self,
        client_name: str,
        client_uuid: str,
        client_password: str,
        server_endpoint: str,
    ) -> Dict[str, Any]:
        """
        Generate TUIC client config dict and URI.

        URI format: tuic://uuid:password@host:port?...
        """
        ip_host = server_endpoint.split(":")[0]
        sni = self.domain or ip_host
        insecure = (self.tls_mode == "self_signed")
        # When a real TLS cert is issued for a domain, connect via domain
        host = self.domain if (self.domain and self.tls_mode != "self_signed") else ip_host

        params = f"congestion_control=bbr&alpn=h3&sni={sni}"
        if insecure:
            params += "&allow_insecure=1"

        uri = build_proxy_uri(
            scheme="tuic",
            user=client_uuid,
            password=client_password,
            host=host,
            port=self.listen_port,
            params=params,
            label=client_name,
        )

        # v2ray-compatible JSON format for GUI clients (NekoBox, v2rayN, etc.)
        v2ray_config = {
            "protocol": "tuic",
            "server": host,
            "server_port": self.listen_port,
            "uuid": client_uuid,
            "password": client_password,
            "tls": {
                "server_name": sni,
                "insecure": insecure,
                "alpn": ["h3"],
            },
            "congestion_control": "bbr",
        }

        return {
            "uri": uri,
            "config": v2ray_config,
            "config_json": json.dumps(v2ray_config, indent=2),
            "name": client_name,
        }

    # ── Apply config to server ────────────────────────────────────────────────

    def apply_config(self, clients: List[Dict[str, str]]) -> bool:
        """Write server config and restart service."""
        content = self.generate_server_config(clients)
        try:
            self._write_file(self.config_path, content)
            return self.restart_service()
        except Exception as e:
            logger.error(f"TUIC apply_config failed: {e}")
            return False

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    def bootstrap(
        self,
        clients: Optional[List[Dict[str, str]]] = None,
        log_callback=None,
    ) -> Dict[str, Any]:
        """
        Full bootstrap of TUIC on a fresh remote server.
        Steps: install binary → generate TLS cert → write config
               → enable + start service → verify health.

        log_callback: optional callable(str) for live progress reporting.
        Returns: {"success": bool, "message": str, "details": dict}
        """
        def _log(msg: str):
            logger.info(msg)
            if log_callback:
                log_callback(msg)

        details: Dict[str, Any] = {}

        # 1. Install binary if missing
        if not self.is_installed():
            _log(f"⬇ Downloading TUIC binary from GitHub (may take 1-2 min)...")
            ok = self.install(log_cb=log_callback)
            details["install"] = ok
            if not ok:
                return {"success": False, "message": "Failed to install TUIC", "details": details}
        else:
            _log("✓ TUIC already installed")
            details["install"] = "already_installed"

        # 1b. Ensure systemd unit exists (binary may be installed but unit missing)
        code, _, _ = self._run(f"systemctl cat {self.service_name} 2>/dev/null | head -1")
        if code != 0:
            _log(f"📝 Creating systemd unit: {self.service_name}")
            unit_content = (
                f"[Unit]\nDescription=TUIC Proxy Server\nAfter=network.target\n\n"
                f"[Service]\nType=simple\nUser=root\n"
                f"ExecStart=/usr/local/bin/tuic-server -c {self.config_path}\n"
                f"Restart=on-failure\nRestartSec=5\nLimitNOFILE=65536\n\n"
                f"[Install]\nWantedBy=multi-user.target\n"
            )
            self._write_file(f"/etc/systemd/system/{self.service_name}.service", unit_content)
            self._run("systemctl daemon-reload")
            details["unit_created"] = self.service_name
        else:
            details["unit_ok"] = self.service_name

        # 2. TLS cert
        if self.tls_mode == "self_signed":
            if not self.cert_exists(self.cert_path, self.key_path):
                _log(f"🔐 Generating self-signed TLS certificate (CN: {self.domain or self.ssh_host or 'proxy.local'})...")
                ok = self.generate_self_signed_cert(
                    self.cert_path, self.key_path, self.domain
                )
                details["tls"] = "generated_self_signed" if ok else "FAILED"
                if not ok:
                    return {"success": False, "message": "Failed to generate TLS cert", "details": details}
                _log("✓ Self-signed certificate generated")
            else:
                _log("✓ TLS certificate already exists")
                details["tls"] = "cert_exists"
        else:
            if not self.cert_exists(self.cert_path, self.key_path):
                return {
                    "success": False,
                    "message": f"Manual TLS: cert not found at {self.cert_path}",
                    "details": details,
                }
            _log("✓ Using existing manual TLS certificate")
            details["tls"] = "manual_exists"

        # 3. Write config
        _log(f"📝 Writing server config: {self.config_path}")
        config_content = self.generate_server_config(clients or [])
        self._write_file(self.config_path, config_content)
        details["config_written"] = self.config_path

        # 4. Enable + start
        _log(f"🚀 Starting service: {self.service_name}")
        self.enable_service()
        started = self.restart_service()
        details["service_started"] = started
        if not started:
            return {"success": False, "message": "Service failed to start", "details": details}

        # 5. Health
        import time; time.sleep(2)
        active = self.is_service_active()
        port_ok = self.is_port_listening(self.listen_port, proto="udp")
        details["service_active"] = active
        details["port_listening"] = port_ok

        if not active:
            _, logs, _ = self._run(
                f"journalctl -u {self.service_name} -n 20 --no-pager 2>/dev/null"
            )
            details["service_logs"] = logs
            err_snippet = (logs or "")[:300]
            _log(f"✗ Service failed to start. Journal:\n{err_snippet}")
            return {"success": False, "message": "Service not active after start", "details": details}

        _log(f"✅ TUIC running on UDP:{self.listen_port} (TLS: {self.tls_mode})")
        return {"success": True, "message": "TUIC bootstrapped successfully", "details": details}

    # ── Discover existing installation ────────────────────────────────────────

    def _find_service_name(self) -> Optional[str]:
        """Probe common TUIC systemd service names."""
        candidates = ["tuic-server", "tuic", "tuic-proxy", "tuicserver"]
        for name in candidates:
            code, out, _ = self._run(
                f"systemctl list-units --full --all --no-pager 2>/dev/null "
                f"| grep -w {name} | head -1"
            )
            if code == 0 and out.strip():
                return name
            code2, _, _ = self._run(f"systemctl cat {name} 2>/dev/null | head -1")
            if code2 == 0:
                return name
        return None

    def _extract_config_from_unit(self, service_name: str) -> Optional[str]:
        """Extract -c / --config path from systemd ExecStart."""
        code, unit_content, _ = self._run(
            f"systemctl cat {service_name} 2>/dev/null"
        )
        if code != 0 or not unit_content:
            return None
        for pattern in (r'-c\s+(\S+\.json)', r'--config\s+(\S+\.json)'):
            m = re.search(pattern, unit_content)
            if m:
                return m.group(1)
        return None

    def discover(self) -> Dict[str, Any]:
        """
        Discover existing TUIC installation on remote server.

        Always returns a dict — never None.  Contract:
          {
            "installed": bool,
            "found":     bool,
            "reason":    str | None,
            "service_name": str,
            "config_path": str | None,
            "checked_paths": [...],

            # Present only when found=True:
            "listen_port": int,
            "cert_path":   str,
            "key_path":    str,
            "tls_mode":    str,
            "existing_users": [...],
            "is_active":   bool,
          }
        """
        if not self.is_installed():
            return {
                "installed": False,
                "found": False,
                "reason": "binary_not_installed",
                "service_name": self.service_name,
                "config_path": None,
                "checked_paths": [],
            }

        # Find actual service name
        real_service = self._find_service_name() or self.service_name
        if real_service != self.service_name:
            logger.info(f"TUIC discover: found service '{real_service}' (expected '{self.service_name}')")
            self.service_name = real_service

        # Extract config path from service unit (most authoritative)
        config_from_unit = self._extract_config_from_unit(self.service_name)
        if config_from_unit and config_from_unit != self.config_path:
            logger.info(f"TUIC discover: config path from ExecStart = {config_from_unit}")

        path_candidates = []
        if config_from_unit:
            path_candidates.append(config_from_unit)
        path_candidates.append(self.config_path)
        path_candidates += [
            "/etc/tuic/config.json",
            "/etc/tuic/server.json",
            "/usr/local/etc/tuic/config.json",
        ]

        content = None
        found_path = None
        for path in path_candidates:
            if not path:
                continue
            content = self._read_file(path)
            if content and content.strip():
                found_path = path
                break

        if not content or not found_path:
            logger.warning(
                f"TUIC binary found on {self.ssh_host or 'local'} "
                f"but no config found in: {path_candidates}"
            )
            return {
                "installed": True,
                "found": False,
                "reason": "binary_installed_no_config",
                "service_name": self.service_name,
                "config_path": None,
                "checked_paths": path_candidates,
            }

        self.config_path = found_path

        try:
            cfg = json.loads(content)
            if not isinstance(cfg, dict):
                raise ValueError("Config is not a JSON object")
        except Exception as exc:
            logger.warning(f"TUIC discover: config at {found_path} is invalid JSON: {exc}")
            return {
                "installed": True,
                "found": False,
                "reason": f"config_invalid_json: {exc}",
                "config_path": found_path,
                "service_name": self.service_name,
                "checked_paths": path_candidates,
            }

        result: Dict[str, Any] = {
            "installed": True,
            "found": True,
            "reason": None,
            "config_path": found_path,
            "service_name": self.service_name,
            "checked_paths": path_candidates,
            "is_active": self.is_service_active(),
        }

        # Parse listen port
        server_addr = cfg.get("server", f"[::]:{DEFAULT_PORT}")
        m = re.search(r':(\d+)$', str(server_addr))
        result["listen_port"] = int(m.group(1)) if m else DEFAULT_PORT

        result["cert_path"] = cfg.get("certificate", DEFAULT_CERT_PATH)
        result["key_path"] = cfg.get("private_key", DEFAULT_KEY_PATH)
        result["tls_mode"] = "manual"  # assume manual if discovered (cert was pre-existing)

        # Existing users (UUID keys)
        result["existing_users"] = list(cfg.get("users", {}).keys())
        result["raw_config"] = content

        return result

    # ── Health check ──────────────────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """
        Structured health/diagnostic report for monitoring.

        Checks:
          1. Binary installed
          2. Systemd service unit exists
          3. Service is active (running)
          4. Config file exists and is valid JSON
          5. TLS cert/key files exist
          6. UDP port is listening

        Returns a dict with status, issues list, and per-check booleans.
        """
        issues: List[str] = []
        issue_codes: List[str] = []
        diagnostics: Dict[str, Any] = {
            "protocol": "tuic",
            "service": self.service_name,
            "port": self.listen_port,
        }

        def _finalize(active: bool = False) -> Dict[str, Any]:
            status = "offline" if not active else ("warning" if issues else "healthy")
            diagnostics["status"] = status
            diagnostics["issues"] = issues
            diagnostics["issue_codes"] = issue_codes
            diagnostics["message"] = "; ".join(issues[:2]) if issues else ""
            return diagnostics

        # 1. Binary — early exit: no point querying systemd or parsing config
        binary_ok = self.is_installed()
        diagnostics["binary_ok"] = binary_ok
        if not binary_ok:
            issues.append("tuic-server binary not found — run bootstrap to install")
            issue_codes.append("binary_missing")
            logger.warning(f"TUIC health [{self.ssh_host or 'local'}]: binary missing")
            diagnostics.update({
                "unit_exists": False, "service_active": False,
                "config_ok": False, "cert_ok": False, "port_listening": False,
            })
            return _finalize(active=False)

        # 2. Service unit
        code, _, _ = self._run(f"systemctl cat {self.service_name} 2>/dev/null | head -1")
        unit_exists = (code == 0)
        diagnostics["unit_exists"] = unit_exists
        if not unit_exists:
            issues.append(f"systemd unit '{self.service_name}' not found")
            issue_codes.append("unit_missing")
            logger.warning(f"TUIC health [{self.ssh_host or 'local'}]: unit missing ({self.service_name})")

        # 3. Service active
        active = self.is_service_active()
        diagnostics["service_active"] = active
        if not active:
            _, journal, _ = self._run(
                f"journalctl -u {self.service_name} -n 10 --no-pager 2>/dev/null"
            )
            diagnostics["service_log_tail"] = journal
            issues.append(f"service '{self.service_name}' is not running")
            issue_codes.append("service_down")
            logger.warning(f"TUIC health [{self.ssh_host or 'local'}]: service down")

        # 4. Config file — if missing skip parse attempt
        config_content = self._read_file(self.config_path)
        config_ok = False
        diagnostics["config_path"] = self.config_path
        if not config_content:
            issues.append(f"config file not found: {self.config_path}")
            issue_codes.append("config_missing")
            logger.warning(f"TUIC health [{self.ssh_host or 'local'}]: config missing ({self.config_path})")
        else:
            try:
                json.loads(config_content)
                config_ok = True
            except Exception as exc:
                issues.append(f"config JSON invalid: {exc}")
                issue_codes.append("config_invalid")
                logger.warning(f"TUIC health [{self.ssh_host or 'local'}]: config invalid — {exc}")
        diagnostics["config_ok"] = config_ok

        # 5. TLS cert/key
        cert_ok = self.cert_exists(self.cert_path, self.key_path)
        diagnostics["cert_ok"] = cert_ok
        diagnostics["cert_path"] = self.cert_path
        if not cert_ok:
            issues.append(f"TLS cert/key not found: {self.cert_path}")
            issue_codes.append("cert_missing")
            logger.warning(f"TUIC health [{self.ssh_host or 'local'}]: cert missing ({self.cert_path})")

        # 6. Port — only check when service is active
        port_ok = self.is_port_listening(self.listen_port, proto="udp")
        diagnostics["port_listening"] = port_ok
        if active and not port_ok:
            issues.append(f"UDP port {self.listen_port} not listening (firewall or startup failure?)")
            issue_codes.append("port_closed")
            logger.warning(f"TUIC health [{self.ssh_host or 'local'}]: port {self.listen_port} closed")

        metrics = self.get_system_metrics()
        diagnostics.update(metrics)

        return _finalize(active=active)

    # ── Backup ────────────────────────────────────────────────────────────────

    def get_config_for_backup(self) -> Optional[str]:
        """Return raw config content for backup inclusion."""
        return self._read_file(self.config_path)
