"""
Per-server WireGuard health checker.

Modes:
  check_server(server, quick=False) — full check (wg stats + system metrics)
  check_server(server, quick=True)  — quick connectivity check only
  check_all(servers, quick=False)   — parallel batch, capped at MAX_WORKERS

Connection modes:
  local   — wg command on this machine
  ssh     — Paramiko SSH; timeout SSH_CONNECT_TIMEOUT
  agent   — HTTP agent API; timeout AGENT_TIMEOUT

State transitions are fed to health_state_store (anti-flapping + event log).
Alerts are dispatched via alert_manager on confirmed state changes.
"""

import re
import time
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger

# ─── Timeouts (seconds) ────────────────────────────────────────────────────

SSH_CONNECT_TIMEOUT  = 10   # TCP + auth
SSH_CMD_TIMEOUT      = 10   # per command
AGENT_TIMEOUT        = 8    # HTTP request
LOCAL_WG_TIMEOUT     = 5    # subprocess
MAX_WORKERS          = 8    # parallel server checks cap
BATCH_TOTAL_TIMEOUT  = 90   # max total time for check_all()
QUICK_SSH_TIMEOUT    = 6    # TCP connect only for quick check


# ─── Data classes ──────────────────────────────────────────────────────────

@dataclass
class WireGuardInterfaceHealth:
    interface: str
    status: str           # "up" / "down" / "unknown"
    peers_total: int = 0
    peers_active: int = 0   # handshake < 3 min
    peers_recent: int = 0   # handshake < 15 min
    rx_bytes: int = 0
    tx_bytes: int = 0
    message: str = ""


@dataclass
class ServerSystemMetrics:
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_percent: Optional[float] = None
    load_avg_1m: Optional[float] = None
    uptime_seconds: Optional[int] = None


@dataclass
class ServerHealth:
    server_id: int
    server_name: str
    status: str               # healthy / warning / error / offline / unknown
    checked_at: str
    connection_mode: str      # local / ssh / agent
    message: str = ""
    latency_ms: Optional[float] = None
    quick: bool = False
    wireguard: Optional[WireGuardInterfaceHealth] = None
    system: Optional[ServerSystemMetrics] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        wg = None
        if self.wireguard:
            wg = {
                "interface":     self.wireguard.interface,
                "status":        self.wireguard.status,
                "peers_total":   self.wireguard.peers_total,
                "peers_active":  self.wireguard.peers_active,
                "peers_recent":  self.wireguard.peers_recent,
                "rx_bytes":      self.wireguard.rx_bytes,
                "tx_bytes":      self.wireguard.tx_bytes,
                "message":       self.wireguard.message,
            }
        sys_m = None
        if self.system:
            sys_m = {
                "cpu_percent":    self.system.cpu_percent,
                "memory_percent": self.system.memory_percent,
                "disk_percent":   self.system.disk_percent,
                "load_avg_1m":    self.system.load_avg_1m,
                "uptime_seconds": self.system.uptime_seconds,
            }
        return {
            "server_id":      self.server_id,
            "server_name":    self.server_name,
            "status":         self.status,
            "checked_at":     self.checked_at,
            "connection_mode":self.connection_mode,
            "message":        self.message,
            "latency_ms":     self.latency_ms,
            "quick":          self.quick,
            "wireguard":      wg,
            "system":         sys_m,
            "details":        self.details,
        }


# ─── Parse helpers ─────────────────────────────────────────────────────────

def _parse_wg_show(output: str, interface: str) -> WireGuardInterfaceHealth:
    now_ts = int(time.time())
    peers_total = peers_active = peers_recent = 0
    rx_bytes = tx_bytes = 0
    current_peer: Dict[str, Any] = {}

    def _commit():
        nonlocal peers_total, peers_active, peers_recent
        if not current_peer:
            return
        peers_total += 1
        hs = current_peer.get("latest_handshake", 0)
        if hs and (now_ts - hs) < 180:
            peers_active += 1
        if hs and (now_ts - hs) < 900:
            peers_recent += 1

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("peer:"):
            _commit()
            current_peer = {}
        elif line.startswith("latest handshake:"):
            m = re.search(r"(\d+) seconds ago", line)
            if m:
                current_peer["latest_handshake"] = now_ts - int(m.group(1))
        elif line.startswith("transfer:"):
            m = re.search(r"([\d.]+)\s*(\w+)\s+received.*?([\d.]+)\s*(\w+)\s+sent", line)
            if m:
                rx_bytes += _parse_bytes(float(m.group(1)), m.group(2))
                tx_bytes += _parse_bytes(float(m.group(3)), m.group(4))
    _commit()

    return WireGuardInterfaceHealth(
        interface=interface,
        status="up",
        peers_total=peers_total,
        peers_active=peers_active,
        peers_recent=peers_recent,
        rx_bytes=rx_bytes,
        tx_bytes=tx_bytes,
    )


def _parse_bytes(value: float, unit: str) -> int:
    mul = {"b": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4,
           "kb": 1000, "mb": 1000**2, "gb": 1000**3}.get(unit.lower(), 1)
    return int(value * mul)


def _determine_status(wg: Optional[WireGuardInterfaceHealth],
                      sys_m: Optional[ServerSystemMetrics],
                      reachable: bool) -> Tuple[str, str]:
    if not reachable:
        return "offline", "Server not reachable"
    issues, warnings = [], []
    if wg and wg.status == "down":
        issues.append("WireGuard interface is down")
    if sys_m:
        for pct, name in [
            (sys_m.cpu_percent,    "CPU"),
            (sys_m.memory_percent, "Memory"),
            (sys_m.disk_percent,   "Disk"),
        ]:
            if pct is None:
                continue
            if pct >= 95:
                issues.append(f"{name} critical: {pct}%")
            elif pct >= 85:
                warnings.append(f"{name} high: {pct}%")
    if issues:
        return "error", "; ".join(issues)
    if warnings:
        return "warning", "; ".join(warnings)
    return "healthy", "All checks passed"


# ─── ServerHealthChecker ───────────────────────────────────────────────────

class ServerHealthChecker:
    """Checks the health of one or more VPN servers."""

    def __init__(self, db_session=None):
        self._db = db_session

    def check_server(self, server, quick: bool = False) -> ServerHealth:
        """
        Check a single Server ORM object.
        quick=True: fast connectivity check, no wg stats / system metrics.
        Thread-safe, no shared state.
        """
        # Route proxy servers to their own health check
        server_category = getattr(server, 'server_category', None)
        server_type = getattr(server, 'server_type', 'wireguard')
        if server_category == 'proxy' or server_type in ('hysteria2', 'tuic'):
            return self._check_proxy(server, quick=quick)

        mode = server.agent_mode or "ssh"
        if not server.ssh_host and mode != "agent":
            mode = "local"
        t0 = time.perf_counter()
        try:
            if mode == "agent" and server.agent_url and server.agent_api_key:
                result = self._check_agent(server, t0, quick=quick)
            elif server.ssh_host:
                result = self._check_ssh(server, t0, quick=quick)
            else:
                result = self._check_local(server, t0, quick=quick)
        except Exception as exc:
            latency = round((time.perf_counter() - t0) * 1000, 2)
            logger.warning(f"EVENT:AGENT_HEALTH_FAILURE server={server.name} mode={mode} error={type(exc).__name__}: {exc}")
            result = ServerHealth(
                server_id=server.id,
                server_name=server.name,
                status="offline",
                checked_at=datetime.now(timezone.utc).isoformat(),
                connection_mode=mode,
                message=f"Check failed: {type(exc).__name__}",
                latency_ms=latency,
                quick=quick,
            )

        # Feed to state store
        self._record_state(result)
        return result

    def check_all(self, servers: list, quick: bool = False,
                  max_workers: int = MAX_WORKERS) -> List[ServerHealth]:
        """
        Check all servers in parallel with bounded concurrency.
        Servers that time out are returned as offline/unknown — partial results
        are always returned; never raises.
        """
        results: List[ServerHealth] = []
        with ThreadPoolExecutor(max_workers=min(max_workers, len(servers) or 1)) as pool:
            futures = {pool.submit(self.check_server, srv, quick): srv for srv in servers}
            done_iter = as_completed(futures, timeout=BATCH_TOTAL_TIMEOUT)
            try:
                for fut in done_iter:
                    srv = futures[fut]
                    try:
                        results.append(fut.result(timeout=1))
                    except Exception as exc:
                        results.append(self._timeout_result(srv, str(exc), quick=quick))
            except Exception:
                # Timeout on as_completed — collect what we have + mark remaining
                done_keys = {f for f in futures if f.done()}
                for fut, srv in futures.items():
                    if fut not in done_keys:
                        results.append(self._timeout_result(srv, "Check timed out", quick=quick))

        results.sort(key=lambda r: r.server_id)
        return results

    def _timeout_result(self, server, msg: str, quick: bool = False) -> ServerHealth:
        mode = server.agent_mode or ("ssh" if server.ssh_host else "local")
        result = ServerHealth(
            server_id=server.id,
            server_name=server.name,
            status="unknown",
            checked_at=datetime.now(timezone.utc).isoformat(),
            connection_mode=mode,
            message=msg,
            quick=quick,
        )
        self._record_state(result)
        return result

    def _record_state(self, result: ServerHealth):
        """Feed result to state store and maybe alert."""
        try:
            from .state_store import health_state_store
            from .alerting import alert_manager
            event = health_state_store.record_check(
                target_type="server",
                target_id=str(result.server_id),
                target_name=result.server_name,
                raw_status=result.status,
                is_critical=False,
                message=result.message,
            )
            if event is not None and self._db is not None:
                alert_manager.maybe_alert(event, db=self._db)
        except Exception as exc:
            logger.debug(f"State store record failed for server {result.server_id}: {exc}")

    @staticmethod
    def _wg_cmd(server) -> str:
        """Return 'awg' for AmneziaWG servers, 'wg' for WireGuard."""
        return "awg" if getattr(server, 'server_type', 'wireguard') == 'amneziawg' else "wg"

    # ── Local ──────────────────────────────────────────────────────────────

    def _check_local(self, server, t0: float, quick: bool) -> ServerHealth:
        interface = server.interface or "wg0"
        wg_cmd = self._wg_cmd(server)
        latency = round((time.perf_counter() - t0) * 1000, 2)
        wg = self._local_wg_check(interface, wg_cmd=wg_cmd)
        sys_m = self._local_system_metrics() if not quick else None
        status, message = _determine_status(wg, sys_m, reachable=True)
        return ServerHealth(
            server_id=server.id, server_name=server.name,
            status=status, checked_at=datetime.now(timezone.utc).isoformat(),
            connection_mode="local", message=message, latency_ms=latency,
            quick=quick, wireguard=wg, system=sys_m,
            details={"server_type": getattr(server, 'server_type', 'wireguard')},
        )

    def _local_wg_check(self, interface: str, wg_cmd: str = "wg") -> Optional[WireGuardInterfaceHealth]:
        try:
            r = subprocess.run([wg_cmd, "show", interface], capture_output=True,
                               text=True, timeout=LOCAL_WG_TIMEOUT)
            if r.returncode != 0:
                return WireGuardInterfaceHealth(interface=interface, status="down",
                                               message=r.stderr.strip() or "Interface not found")
            return _parse_wg_show(r.stdout, interface)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return WireGuardInterfaceHealth(interface=interface, status="unknown", message=str(exc))

    def _local_system_metrics(self) -> ServerSystemMetrics:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.3)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            load = list(psutil.getloadavg()) if hasattr(psutil, "getloadavg") else []
            return ServerSystemMetrics(
                cpu_percent=round(cpu, 1), memory_percent=round(mem.percent, 1),
                disk_percent=round(disk.percent, 1),
                load_avg_1m=round(load[0], 2) if load else None,
                uptime_seconds=int(time.time() - psutil.boot_time()),
            )
        except Exception:
            return ServerSystemMetrics()

    # ── SSH ────────────────────────────────────────────────────────────────

    def _check_ssh(self, server, t0: float, quick: bool) -> ServerHealth:
        interface = server.interface or "wg0"
        wg_cmd = self._wg_cmd(server)
        try:
            import paramiko
            import io as _io
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            pkey = None
            if server.ssh_private_key:
                for _cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
                    try:
                        pkey = _cls.from_private_key(_io.StringIO(server.ssh_private_key))
                        break
                    except Exception:
                        pass
            try:
                ssh.connect(
                    server.ssh_host,
                    port=server.ssh_port or 22,
                    username=server.ssh_user or "root",
                    password=server.ssh_password if not pkey else None,
                    pkey=pkey,
                    timeout=SSH_CONNECT_TIMEOUT,
                    auth_timeout=SSH_CONNECT_TIMEOUT,
                    banner_timeout=SSH_CONNECT_TIMEOUT,
                )
                latency = round((time.perf_counter() - t0) * 1000, 2)
                if quick:
                    return ServerHealth(
                        server_id=server.id, server_name=server.name,
                        status="healthy", checked_at=datetime.now(timezone.utc).isoformat(),
                        connection_mode="ssh", message="SSH reachable", latency_ms=latency, quick=True,
                        details={"server_type": getattr(server, 'server_type', 'wireguard')},
                    )
                wg = self._ssh_wg_check(ssh, interface, wg_cmd=wg_cmd)
                sys_m = self._ssh_system_metrics(ssh)
                status, message = _determine_status(wg, sys_m, reachable=True)
                return ServerHealth(
                    server_id=server.id, server_name=server.name,
                    status=status, checked_at=datetime.now(timezone.utc).isoformat(),
                    connection_mode="ssh", message=message, latency_ms=latency,
                    quick=quick, wireguard=wg, system=sys_m,
                    details={"server_type": getattr(server, 'server_type', 'wireguard')},
                )
            finally:
                ssh.close()
        except Exception as exc:
            latency = round((time.perf_counter() - t0) * 1000, 2)
            return ServerHealth(
                server_id=server.id, server_name=server.name,
                status="offline", checked_at=datetime.now(timezone.utc).isoformat(),
                connection_mode="ssh", message=f"SSH failed: {type(exc).__name__}",
                latency_ms=latency, quick=quick,
            )

    def _ssh_exec(self, ssh, cmd: str) -> str:
        _, stdout, _ = ssh.exec_command(cmd, timeout=SSH_CMD_TIMEOUT)
        return stdout.read().decode(errors="replace").strip()

    def _ssh_wg_check(self, ssh, interface: str, wg_cmd: str = "wg") -> Optional[WireGuardInterfaceHealth]:
        try:
            out = self._ssh_exec(ssh, f"{wg_cmd} show {interface} 2>&1")
            if "No such device" in out or ("error" in out.lower() and not out.startswith("interface:")):
                return WireGuardInterfaceHealth(interface=interface, status="down", message=out[:120])
            return _parse_wg_show(out, interface)
        except Exception as exc:
            return WireGuardInterfaceHealth(interface=interface, status="unknown", message=str(exc))

    def _ssh_system_metrics(self, ssh) -> ServerSystemMetrics:
        try:
            raw = self._ssh_exec(
                ssh,
                "python3 -c \""
                "import json,psutil,time;"
                "cpu=psutil.cpu_percent(interval=0.3);"
                "mem=psutil.virtual_memory();"
                "disk=psutil.disk_usage('/');"
                "la=list(psutil.getloadavg()) if hasattr(psutil,'getloadavg') else [];"
                "up=int(time.time()-psutil.boot_time());"
                "print(json.dumps({'cpu':cpu,'mem':mem.percent,'disk':disk.percent,'load':la,'up':up}))"
                "\" 2>/dev/null"
            )
            if raw:
                import json
                d = json.loads(raw)
                return ServerSystemMetrics(
                    cpu_percent=round(d.get("cpu", 0), 1),
                    memory_percent=round(d.get("mem", 0), 1),
                    disk_percent=round(d.get("disk", 0), 1),
                    load_avg_1m=round(d["load"][0], 2) if d.get("load") else None,
                    uptime_seconds=d.get("up"),
                )
        except Exception:
            pass
        # Fallback via /proc
        try:
            mem_raw = self._ssh_exec(ssh, "cat /proc/meminfo")
            mem_total = mem_available = 0
            for line in mem_raw.splitlines():
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available = int(line.split()[1])
            mem_pct = round((mem_total - mem_available) / mem_total * 100, 1) if mem_total else None
            disk_raw = self._ssh_exec(ssh, "df / --output=pcent 2>/dev/null | tail -1")
            disk_pct = float(disk_raw.replace("%", "").strip()) if disk_raw else None
            return ServerSystemMetrics(memory_percent=mem_pct, disk_percent=disk_pct)
        except Exception:
            return ServerSystemMetrics()

    # ── Agent ──────────────────────────────────────────────────────────────

    def _check_agent(self, server, t0: float, quick: bool) -> ServerHealth:
        interface = server.interface or "wg0"
        import requests
        base = server.agent_url.rstrip("/")
        headers = {"X-API-Key": server.agent_api_key}
        try:
            resp = requests.get(f"{base}/health", headers=headers, timeout=AGENT_TIMEOUT)
            latency = round((time.perf_counter() - t0) * 1000, 2)
            resp.raise_for_status()
            health_data = resp.json()
        except requests.exceptions.Timeout:
            latency = round((time.perf_counter() - t0) * 1000, 2)
            return ServerHealth(
                server_id=server.id, server_name=server.name,
                status="offline", checked_at=datetime.now(timezone.utc).isoformat(),
                connection_mode="agent", message="Agent timed out", latency_ms=latency, quick=quick,
            )
        except Exception as exc:
            latency = round((time.perf_counter() - t0) * 1000, 2)
            return ServerHealth(
                server_id=server.id, server_name=server.name,
                status="offline", checked_at=datetime.now(timezone.utc).isoformat(),
                connection_mode="agent", message=f"Agent unreachable: {type(exc).__name__}",
                latency_ms=latency, quick=quick,
            )

        if quick:
            return ServerHealth(
                server_id=server.id, server_name=server.name,
                status="healthy", checked_at=datetime.now(timezone.utc).isoformat(),
                connection_mode="agent", message="Agent reachable", latency_ms=latency, quick=True,
            )

        # Parse stats
        wg = None
        try:
            sr = requests.get(f"{base}/stats", headers=headers, timeout=AGENT_TIMEOUT)
            if sr.status_code == 200:
                stats = sr.json()
                peers_data = stats.get("peers", [])
                now_ts = int(time.time())
                wg = WireGuardInterfaceHealth(
                    interface=interface, status="up",
                    peers_total=len(peers_data),
                    peers_active=sum(1 for p in peers_data
                                     if p.get("latest_handshake") and (now_ts - p["latest_handshake"]) < 180),
                    peers_recent=sum(1 for p in peers_data
                                     if p.get("latest_handshake") and (now_ts - p["latest_handshake"]) < 900),
                )
        except Exception:
            pass

        sys_m = None
        if isinstance(health_data, dict):
            sys_m = ServerSystemMetrics(
                cpu_percent=health_data.get("cpu_percent"),
                memory_percent=health_data.get("memory_percent"),
                disk_percent=health_data.get("disk_percent"),
                uptime_seconds=health_data.get("uptime_seconds"),
            )

        status, message = _determine_status(wg, sys_m, reachable=True)
        return ServerHealth(
            server_id=server.id, server_name=server.name,
            status=status, checked_at=datetime.now(timezone.utc).isoformat(),
            connection_mode="agent", message=message, latency_ms=latency,
            quick=quick, wireguard=wg, system=sys_m,
            details={"server_type": getattr(server, 'server_type', 'wireguard')},
        )

    def _check_proxy(self, server, quick: bool = False) -> ServerHealth:
        """
        Health check for proxy servers (Hysteria2 / TUIC).

        Uses the protocol-specific manager's health_check() which verifies:
          binary, service unit, service active, config file, TLS cert, UDP port.

        The 'issues' list from health_check() becomes the human-readable message.
        """
        server_type = getattr(server, 'server_type', 'hysteria2')
        t0 = time.perf_counter()
        checked_at = datetime.now(timezone.utc).isoformat()

        if not server.ssh_host:
            return self._check_proxy_local(server, t0, quick)

        try:
            # Instantiate the right manager for richer diagnostics
            ssh_kwargs = dict(
                ssh_host=server.ssh_host,
                ssh_port=server.ssh_port or 22,
                ssh_user=server.ssh_user or "root",
                ssh_password=server.ssh_password,
                ssh_private_key=server.ssh_private_key,
            )
            default_svc = "hysteria-server" if server_type == "hysteria2" else "tuic-server"

            if server_type == "hysteria2":
                from src.core.hysteria2 import Hysteria2Manager, DEFAULT_CERT_PATH, DEFAULT_KEY_PATH
                mgr = Hysteria2Manager(
                    config_path=server.proxy_config_path or "/etc/hysteria/config.yaml",
                    cert_path=server.proxy_cert_path or DEFAULT_CERT_PATH,
                    key_path=server.proxy_key_path or DEFAULT_KEY_PATH,
                    service_name=server.proxy_service_name or default_svc,
                    listen_port=server.listen_port or 8443,
                    domain=server.proxy_domain,
                    tls_mode=server.proxy_tls_mode or "self_signed",
                    **ssh_kwargs,
                )
            elif server_type == "tuic":
                from src.core.tuic import TUICManager, DEFAULT_CERT_PATH, DEFAULT_KEY_PATH
                mgr = TUICManager(
                    config_path=server.proxy_config_path or "/etc/tuic/config.json",
                    cert_path=server.proxy_cert_path or DEFAULT_CERT_PATH,
                    key_path=server.proxy_key_path or DEFAULT_KEY_PATH,
                    service_name=server.proxy_service_name or default_svc,
                    listen_port=server.listen_port or 8444,
                    domain=server.proxy_domain,
                    tls_mode=server.proxy_tls_mode or "self_signed",
                    **ssh_kwargs,
                )
            else:
                # Fallback to base manager for unknown proxy types
                from src.core.proxy_base import ProxyBaseManager
                mgr = ProxyBaseManager(
                    config_path=server.proxy_config_path or "",
                    service_name=server.proxy_service_name or default_svc,
                    **ssh_kwargs,
                )
                health = {
                    "service_active": mgr.is_service_active(),
                    "port_listening": mgr.is_port_listening(server.listen_port or 8443, proto="udp"),
                    "status": "unknown",
                    "issues": [],
                }
                mgr.close()
                latency = round((time.perf_counter() - t0) * 1000, 2)
                return ServerHealth(
                    server_id=server.id, server_name=server.name,
                    status=health["status"], checked_at=checked_at,
                    connection_mode="ssh", message="Unknown proxy type",
                    latency_ms=latency, quick=quick,
                    details={"server_type": server_type, "server_category": "proxy", **health},
                )

            # Run full diagnostic health check
            health = mgr.health_check()
            mgr.close()
            latency = round((time.perf_counter() - t0) * 1000, 2)

            status = health.get("status", "offline")
            issues = health.get("issues", [])
            message = "; ".join(issues) if issues else "All checks passed"

            return ServerHealth(
                server_id=server.id,
                server_name=server.name,
                status=status,
                checked_at=checked_at,
                connection_mode="ssh",
                message=message,
                latency_ms=latency,
                quick=quick,
                wireguard=None,
                system=ServerSystemMetrics(
                    cpu_percent=health.get("cpu_percent"),
                    memory_percent=health.get("memory_percent"),
                    disk_percent=health.get("disk_percent"),
                ) if not quick else None,
                details={
                    "server_type": server_type,
                    "server_category": "proxy",
                    "service_active": health.get("service_active", False),
                    "port": health.get("port"),
                    "port_listening": health.get("port_listening", False),
                    "binary_ok": health.get("binary_ok"),
                    "config_ok": health.get("config_ok"),
                    "cert_ok": health.get("cert_ok"),
                    "config_path": health.get("config_path"),
                    "cert_path": health.get("cert_path"),
                    "issues": issues,
                },
            )

        except Exception as exc:
            latency = round((time.perf_counter() - t0) * 1000, 2)
            logger.warning(f"Proxy health check failed for {server.name}: {exc}")
            return ServerHealth(
                server_id=server.id,
                server_name=server.name,
                status="offline",
                checked_at=checked_at,
                connection_mode="ssh",
                message=f"SSH connection failed: {type(exc).__name__}: {exc}",
                latency_ms=latency,
                quick=quick,
                details={"server_type": server_type, "server_category": "proxy",
                         "issues": [f"SSH connection failed: {exc}"]},
            )

    def _check_proxy_local(self, server, t0: float, quick: bool) -> ServerHealth:
        """Health check for local proxy server."""
        import subprocess
        server_type = getattr(server, 'server_type', 'hysteria2')
        svc = server.proxy_service_name or (
            "hysteria-server" if server_type == "hysteria2" else "tuic-server"
        )
        try:
            r = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True, text=True, timeout=5
            )
            active = r.stdout.strip() == "active"
        except Exception:
            active = False

        port = server.listen_port
        latency = round((time.perf_counter() - t0) * 1000, 2)
        status = "healthy" if active else "offline"
        return ServerHealth(
            server_id=server.id,
            server_name=server.name,
            status=status,
            checked_at=datetime.now(timezone.utc).isoformat(),
            connection_mode="local",
            message="All checks passed" if active else "Service not running",
            latency_ms=latency,
            quick=quick,
            details={
                "server_type": server_type,
                "server_category": "proxy",
                "service_active": active,
                "port": port,
            },
        )

    def _record_state(self, result: ServerHealth):
        """Feed result to health state store (anti-flapping)."""
        try:
            from src.modules.health.state_store import health_state_store
            health_state_store.update(result)
        except Exception:
            pass
