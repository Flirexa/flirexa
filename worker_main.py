#!/usr/bin/env python3
"""
VPN Manager Background Worker
Runs monitoring, backups, and scheduled tasks independently from the API process.

Usage:
    python worker_main.py
    python worker_main.py --interval 30

Can be run alongside the API (recommended) or the API can run tasks itself (legacy mode).
When this worker is running, set WORKER_ENABLED=true in .env to disable tasks in the API process.
"""

import os
import sys
import time
import signal
import argparse
from datetime import datetime, timezone
from loguru import logger
from dotenv import load_dotenv

# Load .env file
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Add project root and src/ to path (src/ needed for PyArmor runtime lookup)
_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, "src"))

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    _shutdown = True


def _sleep_until_next_cycle(interval_seconds: int) -> None:
    """
    Sleep in short slices so SIGTERM-driven shutdown does not wait for the full
    monitoring interval before the worker can exit.
    """
    deadline = time.monotonic() + max(interval_seconds, 0)
    while not _shutdown:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(1.0, remaining))


def run_monitoring_cycle():
    """Single monitoring cycle delegated to the shared scheduler implementation."""
    from src.api.scheduler import monitoring_cycle as _shared_monitoring_cycle

    _shared_monitoring_cycle()


def run_backup_cycle():
    """Single backup cycle delegated to the shared scheduler implementation."""
    from src.api.scheduler import backup_cycle as _shared_backup_cycle

    _shared_backup_cycle()


def should_run_backup():
    """Check if it's time for a backup based on DB config"""
    from src.database.connection import SessionLocal
    from src.database.models import SystemConfig

    defaults = {
        "backup_enabled": "true",
        "backup_interval_hours": "24",
        "backup_hour_utc": "3",
    }

    db = SessionLocal()
    try:
        rows = db.query(SystemConfig).filter(
            SystemConfig.key.in_(list(defaults.keys()))
        ).all()
        config = {r.key: r.value for r in rows}
    except Exception:
        config = {}
    finally:
        db.close()

    enabled = config.get("backup_enabled", "true").lower() == "true"
    if not enabled:
        return False

    backup_hour = int(config.get("backup_hour_utc", "3"))
    now = datetime.now(timezone.utc)
    return now.hour == backup_hour and now.minute < 2  # Run within first 2 minutes of the hour


def run_business_validation():
    """
    Periodically validate business invariants and auto-fix violations.
    Runs every 30 minutes (tracked via _last_bv_run).
    """
    try:
        from src.modules.business_validator import run_validation
        report = run_validation(auto_fix=True)
        if report.violations:
            unfixed = [v for v in report.violations if not v.fixed]
            logger.error(
                "Worker BV: %d violations found (%d auto-fixed, %d unfixed)",
                len(report.violations), report.auto_fixed, len(unfixed),
            )
            if unfixed:
                try:
                    from src.database.connection import SessionLocal
                    from src.modules.notifications import NotificationService
                    db = SessionLocal()
                    try:
                        ns = NotificationService(db)
                        lines = [f"<b>Business invariant violations</b>"]
                        for v in unfixed[:5]:
                            lines.append(f"• [{v.invariant}] {v.description[:120]}")
                        if len(unfixed) > 5:
                            lines.append(f"• …and {len(unfixed) - 5} more")
                        ns.notify_admin("\n".join(lines))
                    finally:
                        db.close()
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Worker business validation error: {e}")


def run_daily_report():
    """
    Daily financial health report: financial holes, pending payments, expired+enabled clients.
    """
    try:
        from src.database.connection import SessionLocal
        from src.modules.business_validator import BusinessValidator
        from src.modules.notifications import NotificationService

        db = SessionLocal()
        try:
            bv = BusinessValidator(db)
            report = bv.run_all(auto_fix=False)

            # Build report message
            lines = ["<b>📊 Daily health report</b>"]
            lines.append(f"Checked: {report.checked} entities")

            critical = [v for v in report.violations if v.severity == "critical"]
            errors = [v for v in report.violations if v.severity == "error"]
            warnings = [v for v in report.violations if v.severity == "warning"]

            if not report.violations:
                lines.append("✅ All business invariants OK")
            else:
                if critical:
                    lines.append(f"🔴 Critical: {len(critical)}")
                    for v in critical[:3]:
                        lines.append(f"  [{v.invariant}] {v.description[:100]}")
                if errors:
                    lines.append(f"🟠 Errors: {len(errors)}")
                if warnings:
                    lines.append(f"🟡 Warnings: {len(warnings)}")

            ns = NotificationService(db)
            ns.notify_admin("\n".join(lines))
            logger.info("Worker: daily health report sent")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Worker daily report error: {e}")


def _write_worker_heartbeat(now: datetime) -> None:
    try:
        from src.database.connection import SessionLocal
        from src.database.models import SystemConfig
        _hb_db = SessionLocal()
        try:
            hb_row = _hb_db.query(SystemConfig).filter(
                SystemConfig.key == "worker_last_heartbeat"
            ).first()
            if hb_row:
                hb_row.value = now.isoformat()
            else:
                _hb_db.add(SystemConfig(
                    key="worker_last_heartbeat",
                    value=now.isoformat(),
                    value_type="string",
                    description="Last time worker_main.py wrote a heartbeat",
                ))
            _hb_db.commit()
        finally:
            _hb_db.close()
    except Exception as e:
        logger.debug(f"Worker heartbeat write failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="VPN Manager Background Worker")
    parser.add_argument("--interval", type=int, default=None,
                        help="Monitoring interval in seconds (default: from MONITOR_INTERVAL env or 60)")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    args = parser.parse_args()

    interval = args.interval or int(os.getenv("MONITOR_INTERVAL", "60"))

    # Setup logging
    from src.modules.log_config import setup_logging as _setup_logging
    _setup_logging("worker", level=args.log_level)

    # Handle graceful shutdown
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Initialize database
    from src.database.connection import init_db
    init_db()

    logger.info(f"EVENT:WORKER_START Background worker started (interval: {interval}s)")

    last_backup_date = None
    last_bv_run = datetime.now(timezone.utc)  # run first check after 30 min
    last_daily_report_date = None
    BV_INTERVAL_SECONDS = 30 * 60  # 30 minutes

    _write_worker_heartbeat(datetime.now(timezone.utc))

    while not _shutdown:
        _sleep_until_next_cycle(interval)
        if _shutdown:
            break

        now = datetime.now(timezone.utc)

        # Monitoring cycle
        try:
            run_monitoring_cycle()
        except Exception as e:
            logger.error(f"Worker monitoring error: {e}")

        # Worker heartbeat — write to DB so /health/full can detect stale worker
        _write_worker_heartbeat(now)

        # Fail-safe refresh every 5 min
        try:
            from src.database.connection import SessionLocal as _SL2
            from src.modules.failsafe import FailSafeManager
            _fs_db = _SL2()
            try:
                FailSafeManager.instance().refresh(_fs_db)
            finally:
                _fs_db.close()
        except Exception as e:
            logger.debug(f"Worker fail-safe refresh error: {e}")

        # Business invariant validation every 30 min
        try:
            if (now - last_bv_run).total_seconds() >= BV_INTERVAL_SECONDS:
                last_bv_run = now
                run_business_validation()
        except Exception as e:
            logger.error(f"Worker BV schedule error: {e}")

        # Daily health report at 08:00 UTC
        try:
            if now.hour == 8 and now.minute < 2:
                today = now.date()
                if last_daily_report_date != today:
                    last_daily_report_date = today
                    run_daily_report()
        except Exception as e:
            logger.error(f"Worker daily report schedule error: {e}")

        # Backup check (runs at configured hour)
        try:
            if should_run_backup():
                today = now.date()
                if last_backup_date != today:
                    last_backup_date = today
                    run_backup_cycle()
        except Exception as e:
            logger.error(f"Worker backup error: {e}")

    logger.info("EVENT:WORKER_STOP Background worker stopped")


if __name__ == "__main__":
    main()
