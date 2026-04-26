"""
System-level health checker.

Checks all platform components:
  - PostgreSQL (DB latency)
  - API process (always OK if we're running)
  - Background worker
  - License server reachability
  - WireGuard (local interface)
  - Telegram bots (process/token check)
  - Payment providers (CryptoPay ping)
  - Disk / Memory / CPU

Modes:
  check_quick() — fast checks only (no external HTTP); used for dashboard polling
  check_all()   — all checks including network pings; used for full refresh

State tracking:
  Each result is fed to health_state_store for anti-flapping and event logging.
  Alerting is triggered via alert_manager on confirmed state transitions.
"""

import os
import time
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

import psutil
import certifi
from loguru import logger


# ─── Status constants (canonical source is status.py; re-exported here for compat) ──

class HealthStatus:
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR   = "error"
    UNKNOWN = "unknown"
    OFFLINE = "offline"


# ─── Data classes ──────────────────────────────────────────────────────────

@dataclass
class ComponentHealth:
    name: str
    status: str
    message: str = ""
    latency_ms: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealth:
    status: str
    checked_at: str
    components: List[ComponentHealth]
    summary: str = ""
    mode: str = "full"   # "quick" | "full"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "checked_at": self.checked_at,
            "summary": self.summary,
            "mode": self.mode,
            "components": [
                {
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                    "latency_ms": c.latency_ms,
                    "details": c.details,
                }
                for c in self.components
            ],
        }


# ─── Checker ───────────────────────────────────────────────────────────────

# Timeout for individual checks (seconds)
_TIMEOUT_QUICK = 3
_TIMEOUT_FULL  = 10

class SystemHealthChecker:
    """
    Runs platform component checks.

    After each run, results are fed into health_state_store (anti-flapping +
    event log) and alert_manager (Telegram/portal alerts on state transitions).
    """

    def __init__(self, db_session=None):
        self._db = db_session

    # ── Public API ──────────────────────────────────────────────────────────

    def check_quick(self) -> SystemHealth:
        """
        Fast subset of checks — no external HTTP calls.
        Returns quickly; suitable for frequent polling.
        Checks: database, api_process, worker, disk, memory, cpu, wireguard_local
        """
        checkers = [
            ("database",        self._check_database),
            ("api_process",     self._check_api),
            ("worker",          self._check_worker),
            ("wireguard_local", self._check_wireguard_local),
            ("disk",            self._check_disk),
            ("memory",          self._check_memory),
            ("cpu",             self._check_cpu_quick),
        ]
        return self._run_checks(checkers, mode="quick")

    def check_all(self) -> SystemHealth:
        """
        Full check — all 10 components including external HTTP pings.
        Slower; use on demand or for 60-second background polls.
        """
        checkers = [
            ("database",        self._check_database),
            ("api_process",     self._check_api),
            ("worker",          self._check_worker),
            ("license_server",  self._check_license_server),
            ("wireguard_local", self._check_wireguard_local),
            ("telegram_bots",   self._check_telegram_bots),
            ("payment_provider",self._check_payment_provider),
            ("disk",            self._check_disk),
            ("memory",          self._check_memory),
            ("cpu",             self._check_cpu),
        ]
        return self._run_checks(checkers, mode="full")

    # ── Internal runner ─────────────────────────────────────────────────────

    def _run_checks(self, checkers, mode: str) -> SystemHealth:
        from .status import aggregate_status, COMPONENT_CRITICALITY
        from .state_store import health_state_store
        from .alerting import alert_manager

        components = []
        t_start = time.perf_counter()

        for name, fn in checkers:
            t0 = time.perf_counter()
            try:
                result: ComponentHealth = fn()
            except Exception as exc:
                logger.warning(f"Health check '{name}' raised: {exc}")
                result = ComponentHealth(
                    name=name,
                    status=HealthStatus.UNKNOWN,
                    message=f"Check failed: {exc}",
                )

            elapsed = round((time.perf_counter() - t0) * 1000, 1)
            if elapsed > 2000:
                logger.warning(f"Health check '{name}' slow: {elapsed} ms")

            components.append(result)

            # Feed to state store (anti-flapping + event logging)
            is_critical = COMPONENT_CRITICALITY.get(name, "informational") == "critical"
            event = health_state_store.record_check(
                target_type="component",
                target_id=name,
                target_name=_COMPONENT_LABELS.get(name, name),
                raw_status=result.status,
                is_critical=is_critical,
                message=result.message,
                details={k: v for k, v in result.details.items()
                         if isinstance(v, (str, int, float, bool, type(None)))},
            )
            if event is not None and self._db is not None:
                alert_manager.maybe_alert(event, db=self._db)

        total_ms = round((time.perf_counter() - t_start) * 1000, 1)
        logger.debug(f"System health check ({mode}) completed in {total_ms} ms")

        # Aggregate using criticality-aware rules
        component_pairs = [(c.name, c.status) for c in components]
        overall = aggregate_status(component_pairs)

        healthy_count = sum(1 for c in components if c.status == HealthStatus.HEALTHY)
        total = len(components)
        summary = f"{healthy_count}/{total} components healthy"

        return SystemHealth(
            status=overall,
            checked_at=datetime.now(timezone.utc).isoformat(),
            components=components,
            summary=summary,
            mode=mode,
        )

    # ── Individual checks ───────────────────────────────────────────────────

    def _check_database(self) -> ComponentHealth:
        """PostgreSQL: connection latency + simple query."""
        try:
            from ...database.connection import check_db_connection
            t0 = time.perf_counter()
            ok = check_db_connection()
            latency = round((time.perf_counter() - t0) * 1000, 2)

            if not ok:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.ERROR,
                    message="Database connection failed",
                    latency_ms=latency,
                )

            details: Dict[str, Any] = {}
            if self._db:
                try:
                    from ...database.models import Server, Client
                    details["servers"] = self._db.query(Server).count()
                    details["clients"] = self._db.query(Client).count()
                except Exception:
                    pass

            if latency > 500:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.WARNING,
                    message=f"Slow query latency ({latency} ms)",
                    latency_ms=latency,
                    details=details,
                )
            return ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                message=f"Connected ({latency} ms)",
                latency_ms=latency,
                details=details,
            )
        except Exception as exc:
            return ComponentHealth(
                name="database",
                status=HealthStatus.ERROR,
                message=f"DB check failed: {type(exc).__name__}",
            )

    def _check_api(self) -> ComponentHealth:
        """API process is always healthy if this code is executing."""
        try:
            proc = psutil.Process()
            mem_mb = round(proc.memory_info().rss / 1024 / 1024, 1)
            return ComponentHealth(
                name="api_process",
                status=HealthStatus.HEALTHY,
                message=f"Running (PID {proc.pid}, {mem_mb} MB)",
                details={"pid": proc.pid, "memory_mb": mem_mb},
            )
        except Exception as exc:
            return ComponentHealth(
                name="api_process",
                status=HealthStatus.UNKNOWN,
                message=f"psutil error: {type(exc).__name__}",
            )

    def _check_worker(self) -> ComponentHealth:
        """Background worker check."""
        worker_enabled = os.getenv("WORKER_ENABLED", "false").lower() == "true"
        if worker_enabled:
            found = False
            for proc in psutil.process_iter(["pid", "cmdline"]):
                try:
                    cmdline = " ".join(proc.info["cmdline"] or [])
                    if "worker" in cmdline and "python" in cmdline:
                        found = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            if found:
                return ComponentHealth(
                    name="worker",
                    status=HealthStatus.HEALTHY,
                    message="External worker process running",
                    details={"mode": "external"},
                )
            return ComponentHealth(
                name="worker",
                status=HealthStatus.WARNING,
                message="External worker process not detected",
                details={"mode": "external"},
            )
        return ComponentHealth(
            name="worker",
            status=HealthStatus.HEALTHY,
            message="In-process background tasks active",
            details={"mode": "in_process"},
        )

    def _check_license_server(self) -> ComponentHealth:
        """Ping primary license server (full check only)."""
        try:
            from ..license.server_config import get_server_urls
            primary_url, _backup = get_server_urls()
        except Exception:
            primary_url = os.getenv("LICENSE_SERVER_URL", "")

        if not primary_url:
            return ComponentHealth(
                name="license_server",
                status=HealthStatus.UNKNOWN,
                message="License server URL not configured (offline mode)",
                details={"mode": "offline"},
            )

        import requests
        ping_url = f"{primary_url.rstrip('/')}/health"
        try:
            t0 = time.perf_counter()
            resp = requests.get(ping_url, timeout=_TIMEOUT_FULL, verify=certifi.where())
            latency = round((time.perf_counter() - t0) * 1000, 2)
            if resp.status_code == 200:
                return ComponentHealth(
                    name="license_server",
                    status=HealthStatus.HEALTHY,
                    message=f"Reachable ({latency} ms)",
                    latency_ms=latency,
                    details={"url": primary_url},
                )
            return ComponentHealth(
                name="license_server",
                status=HealthStatus.WARNING,
                message=f"HTTP {resp.status_code} from license server",
                latency_ms=latency,
                details={"url": primary_url, "status_code": resp.status_code},
            )
        except requests.exceptions.Timeout:
            return ComponentHealth(
                name="license_server",
                status=HealthStatus.OFFLINE,
                message="License server timed out",
                details={"url": primary_url},
            )
        except requests.exceptions.ConnectionError:
            return ComponentHealth(
                name="license_server",
                status=HealthStatus.OFFLINE,
                message="Cannot connect to license server",
                details={"url": primary_url},
            )
        except Exception as exc:
            return ComponentHealth(
                name="license_server",
                status=HealthStatus.UNKNOWN,
                message=f"Check error: {type(exc).__name__}",
            )

    def _check_wireguard_local(self) -> ComponentHealth:
        """Check if WireGuard or AmneziaWG has active local interfaces."""
        interfaces: list[str] = []
        wg_missing = False
        awg_missing = False

        for cmd in ("wg", "awg"):
            try:
                result = subprocess.run(
                    [cmd, "show", "interfaces"],
                    capture_output=True, text=True, timeout=_TIMEOUT_QUICK,
                )
                if result.returncode == 0:
                    interfaces.extend(result.stdout.strip().split())
            except FileNotFoundError:
                if cmd == "wg":
                    wg_missing = True
                else:
                    awg_missing = True
            except subprocess.TimeoutExpired:
                return ComponentHealth(
                    name="wireguard_local",
                    status=HealthStatus.WARNING,
                    message=f"{cmd} show timed out",
                )
            except Exception as exc:
                return ComponentHealth(
                    name="wireguard_local",
                    status=HealthStatus.UNKNOWN,
                    message=f"VPN check error: {type(exc).__name__}",
                )

        if not interfaces:
            if wg_missing and awg_missing:
                return ComponentHealth(
                    name="wireguard_local",
                    status=HealthStatus.WARNING,
                    message="Neither wg nor awg binary found — no local VPN installed",
                )
            return ComponentHealth(
                name="wireguard_local",
                status=HealthStatus.WARNING,
                message="No local VPN interfaces active (all servers may be remote)",
                details={"interfaces": []},
            )

        return ComponentHealth(
            name="wireguard_local",
            status=HealthStatus.HEALTHY,
            message=f"Active: {', '.join(interfaces)}",
            details={"interfaces": interfaces},
        )

    def _check_telegram_bots(self) -> ComponentHealth:
        """Check Telegram bot configuration."""
        bots_configured = []
        bots_issues = []

        client_token = os.getenv("CLIENT_BOT_TOKEN", "")
        client_enabled = os.getenv("CLIENT_BOT_ENABLED", "false").lower() == "true"
        if client_enabled:
            if client_token:
                bots_configured.append("client_bot")
            else:
                bots_issues.append("CLIENT_BOT_ENABLED=true but CLIENT_BOT_TOKEN missing")

        if not bots_configured and not bots_issues:
            return ComponentHealth(
                name="telegram_bots",
                status=HealthStatus.UNKNOWN,
                message="No Telegram bots configured",
                details={"configured": 0},
            )
        if bots_issues:
            return ComponentHealth(
                name="telegram_bots",
                status=HealthStatus.WARNING,
                message="; ".join(bots_issues),
                details={"configured": len(bots_configured), "issues": bots_issues},
            )
        return ComponentHealth(
            name="telegram_bots",
            status=HealthStatus.HEALTHY,
            message=f"{len(bots_configured)} bot(s) configured",
            details={"bots": bots_configured},
        )

    def _check_payment_provider(self) -> ComponentHealth:
        """
        Check CryptoPay availability.
        Uses safe read-only /getMe endpoint — no payments created.
        Debounced via state_store anti-flapping (not done here, done in _run_checks).
        """
        cryptopay_token = os.getenv("CRYPTOPAY_API_TOKEN", "")
        if not cryptopay_token:
            return ComponentHealth(
                name="payment_provider",
                status=HealthStatus.UNKNOWN,
                message="No payment provider configured (CRYPTOPAY_API_TOKEN not set)",
                details={"provider": "none"},
            )

        import requests
        try:
            t0 = time.perf_counter()
            resp = requests.get(
                "https://pay.crypt.bot/api/getMe",
                headers={"Crypto-Pay-API-Token": cryptopay_token},
                timeout=_TIMEOUT_FULL,
                verify=certifi.where(),
            )
            latency = round((time.perf_counter() - t0) * 1000, 2)
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                app_name = data.get("result", {}).get("name", "CryptoPay")
                return ComponentHealth(
                    name="payment_provider",
                    status=HealthStatus.HEALTHY,
                    message=f"CryptoPay reachable ({latency} ms)",
                    latency_ms=latency,
                    details={"provider": "cryptopay", "app_name": app_name},
                )
            err = data.get("error", {}).get("name", "unknown") if isinstance(data, dict) else "bad_response"
            return ComponentHealth(
                name="payment_provider",
                status=HealthStatus.WARNING,
                message=f"CryptoPay API error: {err}",
                latency_ms=latency,
                details={"provider": "cryptopay"},
            )
        except requests.exceptions.Timeout:
            return ComponentHealth(
                name="payment_provider",
                status=HealthStatus.OFFLINE,
                message="CryptoPay API timed out",
                details={"provider": "cryptopay"},
            )
        except requests.exceptions.ConnectionError:
            return ComponentHealth(
                name="payment_provider",
                status=HealthStatus.OFFLINE,
                message="Cannot reach CryptoPay API",
                details={"provider": "cryptopay"},
            )
        except Exception as exc:
            return ComponentHealth(
                name="payment_provider",
                status=HealthStatus.UNKNOWN,
                message=f"Check error: {type(exc).__name__}",
            )

    def _check_disk(self) -> ComponentHealth:
        """Disk usage check."""
        try:
            usage = psutil.disk_usage("/")
            percent = usage.percent
            free_gb = round(usage.free / 1024**3, 1)
            total_gb = round(usage.total / 1024**3, 1)
            if percent >= 95:
                status, msg = HealthStatus.ERROR, f"Disk critically full: {percent}% ({free_gb} GB free)"
            elif percent >= 85:
                status, msg = HealthStatus.WARNING, f"Disk usage high: {percent}% ({free_gb} GB free)"
            else:
                status, msg = HealthStatus.HEALTHY, f"{percent}% used, {free_gb} GB free of {total_gb} GB"
            return ComponentHealth(
                name="disk", status=status, message=msg,
                details={"percent": percent, "free_gb": free_gb, "total_gb": total_gb,
                         "used_gb": round((usage.total - usage.free) / 1024**3, 1)},
            )
        except Exception as exc:
            return ComponentHealth(name="disk", status=HealthStatus.UNKNOWN, message=f"{type(exc).__name__}")

    def _check_memory(self) -> ComponentHealth:
        """Memory usage check."""
        try:
            mem = psutil.virtual_memory()
            percent = mem.percent
            available_gb = round(mem.available / 1024**3, 2)
            total_gb = round(mem.total / 1024**3, 2)
            if percent >= 95:
                status, msg = HealthStatus.ERROR, f"Memory critically low: {percent}% used"
            elif percent >= 85:
                status, msg = HealthStatus.WARNING, f"Memory high: {percent}% used ({available_gb} GB free)"
            else:
                status, msg = HealthStatus.HEALTHY, f"{percent}% used, {available_gb} GB available"
            return ComponentHealth(
                name="memory", status=status, message=msg,
                details={"percent": percent, "available_gb": available_gb, "total_gb": total_gb,
                         "used_gb": round((mem.total - mem.available) / 1024**3, 2)},
            )
        except Exception as exc:
            return ComponentHealth(name="memory", status=HealthStatus.UNKNOWN, message=f"{type(exc).__name__}")

    def _check_cpu(self) -> ComponentHealth:
        """CPU check — 1-second sample (full mode)."""
        return self._cpu_check(interval=1.0)

    def _check_cpu_quick(self) -> ComponentHealth:
        """CPU check — non-blocking (quick mode uses cached value)."""
        return self._cpu_check(interval=None)

    def _cpu_check(self, interval) -> ComponentHealth:
        try:
            cpu_percent = psutil.cpu_percent(interval=interval)
            cpu_count = psutil.cpu_count()
            load_avg = list(psutil.getloadavg()) if hasattr(psutil, "getloadavg") else []
            if cpu_percent >= 95:
                status, msg = HealthStatus.ERROR, f"CPU critically high: {cpu_percent}%"
            elif cpu_percent >= 80:
                status, msg = HealthStatus.WARNING, f"CPU high: {cpu_percent}%"
            else:
                status, msg = HealthStatus.HEALTHY, f"{cpu_percent}% ({cpu_count} cores)"
            details: Dict[str, Any] = {"percent": cpu_percent, "cores": cpu_count}
            if load_avg:
                details["load_avg_1m"]  = round(load_avg[0], 2)
                details["load_avg_5m"]  = round(load_avg[1], 2)
                details["load_avg_15m"] = round(load_avg[2], 2)
            return ComponentHealth(name="cpu", status=status, message=msg, details=details)
        except Exception as exc:
            return ComponentHealth(name="cpu", status=HealthStatus.UNKNOWN, message=f"{type(exc).__name__}")


# ── Human-readable labels ──────────────────────────────────────────────────

_COMPONENT_LABELS: Dict[str, str] = {
    "database":        "Database",
    "api_process":     "API Process",
    "worker":          "Background Worker",
    "license_server":  "License Server",
    "wireguard_local": "WireGuard (local)",
    "telegram_bots":   "Telegram Bots",
    "payment_provider":"Payment Provider",
    "disk":            "Disk",
    "memory":          "Memory",
    "cpu":             "CPU",
}
