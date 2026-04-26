"""
VPN Management Studio — Hysteria 2 Manager

Hysteria 2 is a QUIC-based proxy protocol designed for censorship
circumvention. It works as a SOCKS5/HTTP forward proxy, NOT as a VPN.
Clients connect via password auth; the server routes traffic outward.

Default paths:
  config:  /etc/hysteria/config.yaml
  certs:   /etc/hysteria/server.crt + server.key
  service: hysteria-server.service

Official installer: https://get.hy2.sh/ (installs to /usr/local/bin/hysteria)
"""

import re
import secrets
import string
import yaml
from typing import Optional, Dict, List, Any
from urllib.parse import quote

from loguru import logger
from .proxy_base import ProxyBaseManager, build_proxy_uri


DEFAULT_CONFIG_PATH  = "/etc/hysteria/config.yaml"
DEFAULT_CERT_PATH    = "/etc/hysteria/server.crt"
DEFAULT_KEY_PATH     = "/etc/hysteria/server.key"
DEFAULT_SERVICE_NAME = "hysteria-server"
DEFAULT_PORT         = 8443


def _random_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Hysteria2Manager(ProxyBaseManager):
    """
    Manages Hysteria 2 proxy server installation and configuration.

    Server config is a YAML file that lists users under `auth.userpass`.
    Each client = one entry in that map (username → password).

    When a client is created or deleted, the full server config is
    regenerated and the service is restarted (Hy2 reloads on SIGHUP
    or restart — restart is simpler and more reliable).
    """

    def __init__(
        self,
        config_path: str = DEFAULT_CONFIG_PATH,
        cert_path: str = DEFAULT_CERT_PATH,
        key_path: str = DEFAULT_KEY_PATH,
        service_name: str = DEFAULT_SERVICE_NAME,
        listen_port: int = DEFAULT_PORT,
        domain: Optional[str] = None,
        tls_mode: str = "self_signed",        # self_signed | acme | manual
        obfs_password: Optional[str] = None,   # optional OBFS password
        auth_password: Optional[str] = None,   # server-level auth password (shared by all clients)
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
        self.obfs_password = obfs_password
        self.auth_password = auth_password

    # ── Binary / installation check ───────────────────────────────────────────

    def is_installed(self) -> bool:
        """Check if the hysteria binary is available."""
        code, _, _ = self._run("which hysteria 2>/dev/null || test -f /usr/local/bin/hysteria")
        return code == 0

    def get_version(self) -> Optional[str]:
        code, out, _ = self._run("hysteria version 2>/dev/null | head -1")
        if code == 0 and out:
            m = re.search(r'v?(\d+\.\d+[\.\d]*)', out)
            return m.group(1) if m else out.strip()
        return None

    def install(self, log_cb=None) -> bool:
        """
        Install Hysteria 2 on the remote server using the official installer.
        Requires: curl, bash. The installer writes /usr/local/bin/hysteria
        and creates the hysteria-server.service systemd unit.
        """
        msg = f"Installing Hysteria 2 on {self.ssh_host or 'local'}..."
        logger.info(msg)
        if log_cb:
            log_cb(f"⬇ {msg}")
        cmd = "curl -fsSL https://get.hy2.sh/ | bash 2>&1"
        code, out, err = self._run(cmd, timeout=180)
        if code != 0:
            logger.error(f"Hysteria2 install failed: {err or out}")
            if log_cb:
                log_cb(f"✗ Install failed: {(err or out)[:200]}")
            return False
        logger.info("Hysteria 2 installed successfully")
        if log_cb:
            log_cb("✓ Hysteria 2 binary installed")
        return True

    # ── Config generation ─────────────────────────────────────────────────────

    def generate_server_config(self, clients: List[Dict[str, str]]) -> str:
        """
        Generate Hysteria 2 server config YAML.

        Uses 'password' auth type (not 'userpass') for sing-box/Hiddify compatibility.
        Hiddify rejects URIs with user:password format — it requires plain password@host.
        The server-level auth_password is shared by all clients of this server.

        clients: list of {"name": str, "password": str} — not used for auth config,
                 kept for API compatibility.
        """
        # Use server-level auth password; generate one once if not set yet.
        auth_pw = self.auth_password or _random_password(32)
        self.auth_password = auth_pw

        cfg: Dict[str, Any] = {
            "listen": f":{self.listen_port}",
            "auth": {
                "type": "password",
                "password": auth_pw,
            },
            "masquerade": {
                "type": "proxy",
                "proxy": {
                    "url": "https://news.ycombinator.com/",
                    "rewriteHost": True,
                },
            },
        }

        if self.tls_mode == "acme" and self.domain:
            # For ACME mode we obtain the cert via certbot (in bootstrap()) and
            # then run Hysteria2 in manual TLS mode pointing at certbot's live certs.
            # This avoids the httpPort race-condition entirely.
            cb_cert = f"/etc/letsencrypt/live/{self.domain}/fullchain.pem"
            cb_key  = f"/etc/letsencrypt/live/{self.domain}/privkey.pem"
            cfg["tls"] = {"cert": cb_cert, "key": cb_key}
        else:
            # self_signed or manual: explicit cert/key paths
            cfg["tls"] = {
                "cert": self.cert_path,
                "key": self.key_path,
            }

        if self.obfs_password:
            cfg["obfs"] = {
                "type": "salamander",
                "salamander": {"password": self.obfs_password},
            }

        return yaml.dump(cfg, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def generate_client_config(
        self,
        client_name: str,
        client_password: str,
        server_endpoint: str,
    ) -> Dict[str, Any]:
        """
        Generate Hysteria 2 client config dict and URI.

        Uses password-only URI format (hysteria2://password@host:port) for
        sing-box/Hiddify compatibility. The password is the server-level
        auth_password; client_password is kept for API compatibility but
        auth_password takes precedence when set.

        Returns:
            {
                "uri": "hysteria2://...",
                "config": {yaml-compatible dict},
                "config_yaml": "...",
            }
        """
        # Use server-level auth password if available, fall back to client password
        auth_pw = self.auth_password or client_password

        # Determine SNI and insecure flag
        sni = self.domain or server_endpoint.split(":")[0]
        insecure = (self.tls_mode == "self_signed")

        # URI format: hysteria2://password@host:port?sni=...&insecure=1#ProfileName
        # No username — sing-box/Hiddify only support plain password in URI
        # When a real TLS cert is issued for a domain, the client must connect
        # via that domain (not IP) so the TLS handshake succeeds.
        host = self.domain if (self.domain and self.tls_mode != "self_signed") else server_endpoint.split(":")[0]
        uri_params = f"sni={sni}"
        if insecure:
            uri_params += "&insecure=1"
        if self.obfs_password:
            uri_params += f"&obfs=salamander&obfs-password={quote(self.obfs_password, safe='')}"
        enc_pw = quote(auth_pw, safe="")
        enc_label = quote(client_name, safe="")
        # Hiddify requires a path component (/) before query params: host:port/?params
        uri = f"hysteria2://{enc_pw}@{host}:{self.listen_port}/?{uri_params}#{enc_label}"

        config = {
            "server": f"{host}:{self.listen_port}",
            "auth": auth_pw,
            "tls": {
                "sni": sni,
                "insecure": insecure,
            },
            "socks5": {"listen": "127.0.0.1:1080"},
            "http": {"listen": "127.0.0.1:8080"},
        }

        if self.obfs_password:
            config["obfs"] = {
                "type": "salamander",
                "salamander": {"password": self.obfs_password},
            }

        config_yaml = yaml.dump(
            config, default_flow_style=False, allow_unicode=True, sort_keys=False
        )

        return {"uri": uri, "config": config, "config_yaml": config_yaml}

    # ── Apply config to server ────────────────────────────────────────────────

    def apply_config(self, clients: List[Dict[str, str]]) -> bool:
        """Write server config and restart service."""
        content = self.generate_server_config(clients)
        try:
            self._write_file(self.config_path, content)
            return self.restart_service()
        except Exception as e:
            logger.error(f"Hysteria2 apply_config failed: {e}")
            return False

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    def bootstrap(
        self,
        clients: Optional[List[Dict[str, str]]] = None,
        log_callback=None,
    ) -> Dict[str, Any]:
        """
        Full bootstrap of Hysteria 2 on a fresh remote server:
        1. Install hysteria binary (if missing)
        2. Generate TLS certificate (if self_signed)
        3. Write server config
        4. Enable + start service
        5. Verify health

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
            _log(f"⬇ Downloading Hysteria 2 binary (may take 1-2 min)...")
            ok = self.install(log_cb=log_callback)
            details["install"] = ok
            if not ok:
                return {"success": False, "message": "Failed to install Hysteria 2", "details": details}
        else:
            _log("✓ Hysteria 2 already installed")
            details["install"] = "already_installed"

        # 1b. Always write per-interface systemd unit (ensures correct config path binding)
        _log(f"📝 Создаём systemd unit: {self.service_name}")
        unit_content = (
            f"[Unit]\nDescription=Hysteria2 Proxy ({self.service_name})\nAfter=network.target\n\n"
            f"[Service]\nType=simple\nUser=root\n"
            f"ExecStart=/usr/local/bin/hysteria server -c {self.config_path}\n"
            f"Restart=on-failure\nRestartSec=5\nLimitNOFILE=1048576\n\n"
            f"[Install]\nWantedBy=multi-user.target\n"
        )
        self._write_file(f"/etc/systemd/system/{self.service_name}.service", unit_content)
        self._run("systemctl daemon-reload")
        details["unit_created"] = self.service_name

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
        elif self.tls_mode == "acme":
            if not self.domain:
                return {"success": False, "message": "ACME mode requires a domain name", "details": details}
            _log(f"🌐 ACME/Let's Encrypt — домен: {self.domain}")
            self._run(f"mkdir -p {self.config_path.rsplit('/', 1)[0]}")

            # Obtain cert via certbot (webroot method through nginx).
            # Install certbot if missing.
            cb_cert = f"/etc/letsencrypt/live/{self.domain}/fullchain.pem"
            cb_key  = f"/etc/letsencrypt/live/{self.domain}/privkey.pem"
            c, _, _ = self._run(f"test -f {cb_cert}")
            if c != 0:
                # Install certbot if needed
                c2, _, _ = self._run("which certbot 2>/dev/null")
                if c2 != 0:
                    _log("📦 Устанавливаем certbot...")
                    self._run("apt-get install -y certbot python3-certbot-nginx 2>/dev/null || snap install --classic certbot 2>/dev/null")
                # Ensure webroot dir exists
                self._run("mkdir -p /var/www/acme-challenge")
                # Add nginx webroot location if not present
                _WEBROOT_CONF = "/etc/nginx/conf.d/acme-webroot.conf"
                c3, _, _ = self._run(f"test -f {_WEBROOT_CONF}")
                if c3 != 0:
                    webroot_cfg = (
                        "server {\n"
                        "    listen 80;\n"
                        "    server_name _;\n"
                        "    location /.well-known/acme-challenge/ {\n"
                        "        root /var/www/acme-challenge;\n"
                        "    }\n"
                        "    location / { return 301 https://$host$request_uri; }\n"
                        "}\n"
                    )
                    self._write_file(_WEBROOT_CONF, webroot_cfg)
                    self._run("nginx -s reload 2>/dev/null || systemctl reload nginx 2>/dev/null")
                    _log("🔀 Настроен nginx webroot для ACME challenge")

                _log(f"🔐 Запрашиваем сертификат Let's Encrypt для {self.domain}...")
                c4, out4, err4 = self._run(
                    f"certbot certonly --webroot -w /var/www/acme-challenge "
                    f"-d {self.domain} --non-interactive --agree-tos "
                    f"--email webmaster@{self.domain} --no-eff-email 2>&1"
                )
                for line in (out4 or "").splitlines():
                    if any(k in line.lower() for k in ("congratulations", "successfully", "error", "failed", "problem", "cert")):
                        _log(f"   {line.strip()}")

                c5, _, _ = self._run(f"test -f {cb_cert}")
                if c5 != 0:
                    err_snippet = (err4 or out4 or "")[:300]
                    _log(f"✗ Не удалось получить сертификат: {err_snippet}")
                    return {"success": False, "message": f"certbot failed to obtain cert for {self.domain}", "details": details}
                _log(f"✅ Сертификат получен: {cb_cert}")
            else:
                _log(f"✓ Сертификат уже есть: {cb_cert}")

            details["tls"] = "acme_certbot"
        else:
            # manual: cert_path / key_path must already exist
            if not self.cert_exists(self.cert_path, self.key_path):
                return {
                    "success": False,
                    "message": f"Manual TLS mode: cert not found at {self.cert_path}",
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
        import time

        _log(f"🚀 Запускаем сервис: {self.service_name}")
        self.enable_service()
        started = self.restart_service()
        details["service_started"] = started
        if not started:
            return {"success": False, "message": "Service failed to start", "details": details}

        # 5. Wait for service to settle
        time.sleep(3)

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
            _log(f"✗ Сервис не запустился. Journal:\n{err_snippet}")
            return {"success": False, "message": "Service not active after start", "details": details}

        if self.tls_mode == "acme":
            _log(f"✅ Hysteria 2 запущен на UDP:{self.listen_port} — сертификат Let's Encrypt для {self.domain} активен")
        else:
            _log(f"✅ Hysteria 2 запущен на UDP:{self.listen_port} (TLS: {self.tls_mode})")
        return {"success": True, "message": "Hysteria 2 bootstrapped successfully", "details": details}

    # ── Discover existing installation ────────────────────────────────────────

    def _find_service_name(self) -> Optional[str]:
        """
        Probe common Hysteria 2 systemd service names.
        Returns the active/installed name, or None.
        """
        candidates = ["hysteria-server", "hysteria2", "hysteria", "hysteria2-server"]
        for name in candidates:
            code, out, _ = self._run(
                f"systemctl list-units --full --all --no-pager 2>/dev/null "
                f"| grep -w {name} | head -1"
            )
            if code == 0 and out.strip():
                return name
            # Also check unit file exists even if inactive
            code2, _, _ = self._run(
                f"systemctl cat {name} 2>/dev/null | head -1"
            )
            if code2 == 0:
                return name
        return None

    def _extract_config_from_unit(self, service_name: str) -> Optional[str]:
        """
        Read ExecStart from a systemd unit file and extract the -c / --config argument.
        Returns config file path string, or None.
        """
        code, unit_content, _ = self._run(
            f"systemctl cat {service_name} 2>/dev/null"
        )
        if code != 0 or not unit_content:
            return None
        # Match: ExecStart=... -c /path/to/config.yaml  or --config /path
        for pattern in (r'-c\s+(\S+\.ya?ml)', r'--config\s+(\S+\.ya?ml)', r'server\s+(-c|--config)\s+(\S+)'):
            m = re.search(pattern, unit_content)
            if m:
                return m.group(m.lastindex)
        return None

    def discover(self) -> Dict[str, Any]:
        """
        Discover existing Hysteria 2 installation on remote server.

        Always returns a dict — never None.  Contract:
          {
            "installed": bool,         # binary found on PATH
            "found":     bool,         # config found AND valid
            "reason":    str | None,   # why found=False (None when found=True)
            "service_name": str,
            "config_path": str | None,
            "checked_paths": [...],

            # Present only when found=True:
            "listen_port":    int,
            "cert_path":      str,
            "key_path":       str,
            "tls_mode":       str,
            "domain":         str | None,
            "obfs_password":  str | None,
            "auth_password":  str | None,
            "existing_users": [...],
            "is_active":      bool,
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

        # Find actual service name — may differ from the default
        real_service = self._find_service_name() or self.service_name
        if real_service != self.service_name:
            logger.info(f"Hysteria2 discover: found service '{real_service}' (expected '{self.service_name}')")
            self.service_name = real_service

        # Try to resolve config path from service ExecStart first
        config_from_unit = self._extract_config_from_unit(self.service_name)
        if config_from_unit and config_from_unit != self.config_path:
            logger.info(f"Hysteria2 discover: config path from unit ExecStart = {config_from_unit}")

        # Full list of paths to try, in priority order:
        # 1. Path extracted from service unit (most authoritative)
        # 2. Currently stored config_path (user-provided or previous discover)
        # 3. Standard installation paths
        path_candidates = []
        if config_from_unit:
            path_candidates.append(config_from_unit)
        path_candidates.append(self.config_path)
        path_candidates += [
            "/etc/hysteria/config.yaml",
            "/etc/hysteria/server.yaml",
            "/etc/hysteria/config.yml",
            "/usr/local/etc/hysteria/config.yaml",
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
                f"Hysteria2 binary found on {self.ssh_host or 'local'} "
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
            cfg = yaml.safe_load(content)
            if not isinstance(cfg, dict):
                raise ValueError("Config is not a YAML mapping")
        except Exception as exc:
            logger.warning(f"Hysteria2 discover: config at {found_path} is invalid YAML: {exc}")
            return {
                "installed": True,
                "found": False,
                "reason": f"config_invalid_yaml: {exc}",
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
        listen = cfg.get("listen", f":{DEFAULT_PORT}")
        m = re.search(r':(\d+)$', str(listen))
        result["listen_port"] = int(m.group(1)) if m else DEFAULT_PORT

        # TLS
        tls = cfg.get("tls", {})
        result["cert_path"] = tls.get("cert", DEFAULT_CERT_PATH)
        result["key_path"] = tls.get("key", DEFAULT_KEY_PATH)
        acme_block = cfg.get("acme", {})
        if acme_block.get("domains"):
            # Old-style built-in ACME block (pre-certbot)
            result["tls_mode"] = "acme"
            result["domain"] = acme_block["domains"][0] if acme_block["domains"] else None
        elif "/etc/letsencrypt/live/" in result.get("cert_path", ""):
            # New-style: certbot cert used as manual TLS
            result["tls_mode"] = "acme"
            # Extract domain from path: /etc/letsencrypt/live/<domain>/fullchain.pem
            import re as _re
            _m = _re.search(r"/etc/letsencrypt/live/([^/]+)/", result["cert_path"])
            result["domain"] = _m.group(1) if _m else None
        else:
            # Distinguish manual vs self-signed by cert file origin
            result["tls_mode"] = "manual"
            result["domain"] = None

        # OBFS
        obfs = cfg.get("obfs", {})
        result["obfs_password"] = obfs.get("salamander", {}).get("password")

        # Auth info
        auth = cfg.get("auth", {})
        result["auth_type"] = auth.get("type")
        result["auth_password"] = auth.get("password") if auth.get("type") == "password" else None
        result["existing_users"] = list(auth.get("userpass", {}).keys())
        result["raw_config"] = content

        return result

    # ── Health check ──────────────────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """
        Structured health/diagnostic report for monitoring.

        Checks (in order):
          1. Binary installed
          2. Systemd service unit exists
          3. Service is active (running)
          4. Config file exists and is valid YAML
          5. TLS cert/key files exist
          6. UDP port is listening

        Returns a dict with:
          status:          healthy | warning | offline
          issues:          list of human-readable problem strings (empty = all good)
          service_active:  bool
          port_listening:  bool
          binary_ok:       bool
          config_ok:       bool
          cert_ok:         bool
        """
        issues: List[str] = []
        issue_codes: List[str] = []
        diagnostics: Dict[str, Any] = {
            "protocol": "hysteria2",
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
            issues.append("hysteria binary not found — run bootstrap to install")
            issue_codes.append("binary_missing")
            logger.warning(f"Hysteria2 health [{self.ssh_host or 'local'}]: binary missing")
            diagnostics.update({
                "unit_exists": False, "service_active": False,
                "config_ok": False, "cert_ok": False, "port_listening": False,
            })
            return _finalize(active=False)

        # 2. Service unit exists
        code, _, _ = self._run(f"systemctl cat {self.service_name} 2>/dev/null | head -1")
        unit_exists = (code == 0)
        diagnostics["unit_exists"] = unit_exists
        if not unit_exists:
            issues.append(f"systemd unit '{self.service_name}' not found")
            issue_codes.append("unit_missing")
            logger.warning(f"Hysteria2 health [{self.ssh_host or 'local'}]: unit missing ({self.service_name})")

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
            logger.warning(f"Hysteria2 health [{self.ssh_host or 'local'}]: service down")

        # 4. Config file — if missing skip parse attempt
        config_content = self._read_file(self.config_path)
        config_ok = False
        diagnostics["config_path"] = self.config_path
        if not config_content:
            issues.append(f"config file not found: {self.config_path}")
            issue_codes.append("config_missing")
            logger.warning(f"Hysteria2 health [{self.ssh_host or 'local'}]: config missing ({self.config_path})")
        else:
            try:
                yaml.safe_load(config_content)
                config_ok = True
            except Exception as exc:
                issues.append(f"config YAML invalid: {exc}")
                issue_codes.append("config_invalid")
                logger.warning(f"Hysteria2 health [{self.ssh_host or 'local'}]: config invalid — {exc}")
        diagnostics["config_ok"] = config_ok

        # 5. TLS cert/key
        cert_ok = self.cert_exists(self.cert_path, self.key_path)
        diagnostics["cert_ok"] = cert_ok
        diagnostics["cert_path"] = self.cert_path
        if not cert_ok and self.tls_mode != "acme":
            issues.append(f"TLS cert/key not found: {self.cert_path}")
            issue_codes.append("cert_missing")
            logger.warning(f"Hysteria2 health [{self.ssh_host or 'local'}]: cert missing ({self.cert_path})")

        # 6. Port — only check when service claims to be active (avoids false port_closed spam)
        port_ok = self.is_port_listening(self.listen_port, proto="udp")
        diagnostics["port_listening"] = port_ok
        if active and not port_ok:
            issues.append(f"UDP port {self.listen_port} not listening (firewall or startup failure?)")
            issue_codes.append("port_closed")
            logger.warning(f"Hysteria2 health [{self.ssh_host or 'local'}]: port {self.listen_port} closed")

        # System metrics
        metrics = self.get_system_metrics()
        diagnostics.update(metrics)

        return _finalize(active=active)

    # ── Backup ────────────────────────────────────────────────────────────────

    def get_config_for_backup(self) -> Optional[str]:
        """Return raw config content for backup inclusion."""
        return self._read_file(self.config_path)
