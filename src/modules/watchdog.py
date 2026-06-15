"""Background watchdog for operator-facing health alerts.

Runs as an asyncio task from the api lifespan. Samples four signals
every WATCHDOG_INTERVAL_SECONDS, fires a Telegram message to the
admin chat when any cross threshold. Per-alert cooldown so a sticky
condition doesn't spam.

Signals:
  - CPU% of the api parent process and its workers (avg across them)
  - FD% (open file descriptors as fraction of soft limit)
  - Postgres oldest "idle in transaction" duration (catches zombies
    before they wedge writes the way 2026-06-11's 8h session did)
  - Resident memory % vs system total (smoke for a memory leak)

Threshold cross is intentionally generous — the panel handles a few
moments of spike from a refresh tick or backup job without paging
anyone. Sustained signals (sampled multiple times in a row) escalate.
"""

from __future__ import annotations

import asyncio
import os
import resource
import time
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


WATCHDOG_INTERVAL_SECONDS = float(os.getenv("WATCHDOG_INTERVAL_SECONDS", "60"))
WATCHDOG_COOLDOWN_SECONDS = float(os.getenv("WATCHDOG_COOLDOWN_SECONDS", "600"))

# Thresholds. Configurable via env without a code change so an
# operator with a heavier baseline workload can dial them up.
CPU_WARN_PERCENT       = float(os.getenv("WATCHDOG_CPU_WARN_PCT",        "80"))
FD_WARN_FRAC           = float(os.getenv("WATCHDOG_FD_WARN_FRAC",        "0.5"))
MEM_WARN_FRAC          = float(os.getenv("WATCHDOG_MEM_WARN_FRAC",       "0.85"))
PG_IDLE_TX_WARN_SEC    = float(os.getenv("WATCHDOG_PG_IDLE_TX_WARN_SEC", "1800"))

# Require N consecutive samples above threshold before alerting. Filters
# out single-tick spikes that recover on their own.
SUSTAINED_SAMPLES = int(os.getenv("WATCHDOG_SUSTAINED_SAMPLES", "2"))

# Disable entirely via env (operator might use external monitoring).
ENABLED = (os.getenv("WATCHDOG_ENABLED", "true") or "true").lower() != "false"


@dataclass
class _SignalState:
    consecutive_hits: int = 0
    last_alert_at: float = 0.0


@dataclass
class _WatchdogState:
    cpu:     _SignalState = field(default_factory=_SignalState)
    fd:      _SignalState = field(default_factory=_SignalState)
    mem:     _SignalState = field(default_factory=_SignalState)
    pg_idle: _SignalState = field(default_factory=_SignalState)


_state = _WatchdogState()


def _read_proc_stat_self_cpu() -> Optional[float]:
    """Return cumulative CPU seconds for this process from /proc/self/stat.
    None on non-Linux or read error."""
    try:
        with open("/proc/self/stat", "r") as f:
            parts = f.read().split()
        utime = int(parts[13])
        stime = int(parts[14])
        clk_tck = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        return (utime + stime) / clk_tck
    except Exception:
        return None


def _read_self_fd_count() -> Optional[int]:
    try:
        return len(os.listdir("/proc/self/fd"))
    except Exception:
        return None


def _read_fd_soft_limit() -> int:
    try:
        soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        return soft
    except Exception:
        return 1024


def _read_mem_fraction() -> Optional[float]:
    """Resident-set / system total. None on non-Linux."""
    try:
        with open("/proc/self/status", "r") as f:
            rss_kb = None
            for line in f:
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                    break
        with open("/proc/meminfo", "r") as f:
            total_kb = None
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                    break
        if rss_kb is None or not total_kb:
            return None
        return rss_kb / total_kb
    except Exception:
        return None


def _read_pg_oldest_idle_in_tx() -> Optional[float]:
    """Seconds since the oldest 'idle in transaction' session started.
    None if PG isn't reachable or no idle-tx sessions."""
    try:
        from sqlalchemy import text
        from src.database.connection import engine
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT COALESCE(EXTRACT(EPOCH FROM now() - min(query_start)), 0) "
                "FROM pg_stat_activity WHERE state = 'idle in transaction'"
            )).first()
        if row is None:
            return 0.0
        v = float(row[0] or 0.0)
        return v
    except Exception as e:
        logger.debug("watchdog: PG poll failed: {}", e)
        return None


# POSIX file lock for "I am the watchdog alert leader". Under
# multi-worker, every worker runs its own watchdog (the observation
# is per-process by design — each worker has its own CPU / fd /
# memory profile). But only ONE worker should actually send a TG
# alert when a threshold trips, otherwise the operator gets
# WORKERS× duplicate messages every time.
#
# The first worker to start grabs flock() on a well-known file and
# keeps it for the lifetime of the process — the kernel releases on
# process death. Other workers see EWOULDBLOCK at startup and never
# alert. Tried pg_advisory_lock first; session-level locks stuck to
# whichever pooled connection acquired them and the leader role
# flipped chaotically as SQLAlchemy reused connections across workers.
_WATCHDOG_LOCK_PATH = os.getenv(
    "WATCHDOG_LOCK_PATH", "/tmp/vpnmanager-watchdog.lock",
)
_lock_fh = None  # held for the lifetime of the leader process
_is_leader: Optional[bool] = None  # cached: None=unknown, True/False=resolved


def _try_acquire_alert_leader() -> bool:
    """Idempotent: try to grab the file lock once. Subsequent calls
    return the cached result. Non-leader workers never re-try — the
    leader is whichever process started first."""
    global _lock_fh, _is_leader
    if _is_leader is not None:
        return _is_leader
    try:
        import fcntl
        _lock_fh = open(_WATCHDOG_LOCK_PATH, "w")
        try:
            fcntl.flock(_lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _is_leader = True
            logger.info("watchdog: this worker is the alert leader")
        except (BlockingIOError, OSError):
            _is_leader = False
            try:
                _lock_fh.close()
            finally:
                _lock_fh = None
    except Exception as e:
        # Filesystem unavailable or fcntl missing — fall back to "send".
        # In a multi-worker setup the operator may see N copies, but
        # silence on a real CPU spike is worse than duplicate alerts.
        logger.debug("watchdog: leader-lock setup raised: {}", e)
        _is_leader = True
    return _is_leader


async def _send_alert(text: str) -> None:
    """Fire-and-forget admin Telegram. Run in a thread so a slow Telegram
    response can't park the watchdog loop. Skipped on workers that
    aren't the file-lock leader."""
    def _do():
        try:
            if not _try_acquire_alert_leader():
                return
            from src.database.connection import SessionLocal
            from src.modules.notifications import NotificationService
            db = SessionLocal()
            try:
                NotificationService(db).notify_admin(text)
            finally:
                db.close()
        except Exception as e:
            logger.warning("watchdog: notify_admin failed: {}", e)
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _do)
    except Exception as e:
        logger.warning("watchdog: alert dispatch failed: {}", e)


def _maybe_alert(sig: _SignalState, threshold_crossed: bool, message: str) -> Optional[str]:
    """Update sustained-cross counter; return the message to send (or
    None) given threshold + cooldown state."""
    if not threshold_crossed:
        sig.consecutive_hits = 0
        return None
    sig.consecutive_hits += 1
    if sig.consecutive_hits < SUSTAINED_SAMPLES:
        return None
    now = time.monotonic()
    if now - sig.last_alert_at < WATCHDOG_COOLDOWN_SECONDS:
        return None
    sig.last_alert_at = now
    return message


async def _tick(prev_cpu_seconds: Optional[float], prev_wall: Optional[float]) -> tuple[Optional[float], float]:
    """One observation pass. Returns (new_cpu_seconds_snapshot, new_wall_time)."""
    now_wall = time.monotonic()
    now_cpu = _read_proc_stat_self_cpu()

    # CPU% over the tick interval. First-tick returns None for the rate.
    cpu_pct = None
    if prev_cpu_seconds is not None and now_cpu is not None and prev_wall is not None:
        elapsed = max(0.001, now_wall - prev_wall)
        delta = max(0.0, now_cpu - prev_cpu_seconds)
        cpu_pct = (delta / elapsed) * 100.0

    fd_count = _read_self_fd_count()
    fd_frac = (fd_count / _read_fd_soft_limit()) if fd_count is not None else None

    mem_frac = _read_mem_fraction()
    pg_idle_age = _read_pg_oldest_idle_in_tx()

    # Evaluate thresholds + maybe dispatch.
    alerts: list[str] = []

    if cpu_pct is not None:
        msg = _maybe_alert(
            _state.cpu,
            cpu_pct > CPU_WARN_PERCENT,
            (
                f"<b>Flirexa — CPU high</b>\n"
                f"api process at <b>{cpu_pct:.0f}%</b> CPU sustained "
                f"({SUSTAINED_SAMPLES}× over {int(WATCHDOG_INTERVAL_SECONDS)}s).\n"
                f"Check the panel for a runaway endpoint or look at "
                f"<code>py-spy dump --pid $(pgrep -f 'main.py api')</code>."
            ),
        )
        if msg: alerts.append(msg)

    if fd_frac is not None:
        msg = _maybe_alert(
            _state.fd,
            fd_frac > FD_WARN_FRAC,
            (
                f"<b>Flirexa — file descriptors high</b>\n"
                f"api process at <b>{fd_count}/{_read_fd_soft_limit()}</b> open fds "
                f"({fd_frac*100:.0f}% of soft limit).\n"
                f"If it climbs further: bump LimitNOFILE on the systemd unit "
                f"or investigate dangling sockets (likely a dead agent leaking "
                f"keep-alive connections)."
            ),
        )
        if msg: alerts.append(msg)

    if mem_frac is not None:
        msg = _maybe_alert(
            _state.mem,
            mem_frac > MEM_WARN_FRAC,
            (
                f"<b>Flirexa — memory high</b>\n"
                f"api process at <b>{mem_frac*100:.0f}%</b> of system memory.\n"
                f"Sustained — check for a memory leak in a background task."
            ),
        )
        if msg: alerts.append(msg)

    if pg_idle_age is not None:
        msg = _maybe_alert(
            _state.pg_idle,
            pg_idle_age > PG_IDLE_TX_WARN_SEC,
            (
                f"<b>Flirexa — Postgres zombie session</b>\n"
                f"Oldest <code>idle in transaction</code> at "
                f"<b>{pg_idle_age/60:.0f} min</b>.\n"
                f"Auto-kill is set to "
                f"<code>idle_in_transaction_session_timeout</code> on prod — "
                f"if this fires it means an even longer session slipped "
                f"through. Inspect with "
                f"<code>SELECT pid, query FROM pg_stat_activity "
                f"WHERE state='idle in transaction';</code>."
            ),
        )
        if msg: alerts.append(msg)

    for a in alerts:
        await _send_alert(a)

    return now_cpu, now_wall


async def _watchdog_loop() -> None:
    """The forever loop. Catches and logs but never raises."""
    logger.info(
        "watchdog: armed (interval={}s, cpu>{}%, fd>{:.0%}, mem>{:.0%}, pg_idle>{}min, sustained={}x)",
        int(WATCHDOG_INTERVAL_SECONDS), int(CPU_WARN_PERCENT),
        FD_WARN_FRAC, MEM_WARN_FRAC, int(PG_IDLE_TX_WARN_SEC // 60),
        SUSTAINED_SAMPLES,
    )
    prev_cpu = None
    prev_wall = None
    while True:
        try:
            prev_cpu, prev_wall = await _tick(prev_cpu, prev_wall)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("watchdog: tick raised: {}", e)
        try:
            await asyncio.sleep(WATCHDOG_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise


_watchdog_task: Optional[asyncio.Task] = None


def start_watchdog() -> None:
    """Idempotent: schedules the watchdog on the running event loop.
    Called once from api lifespan."""
    global _watchdog_task
    if not ENABLED:
        logger.info("watchdog: disabled via WATCHDOG_ENABLED=false")
        return
    if _watchdog_task is not None and not _watchdog_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("watchdog: no running loop, cannot start")
        return
    _watchdog_task = loop.create_task(_watchdog_loop())
