"""
Update auto-check — periodic background poll of the manifest server.

Does NOT apply updates. Only refreshes the cached manifest so the panel's
GET /api/v1/updates/status returns fresh "available_update" info without
the operator having to click "Check for updates" in the UI.

Behavior:
  - Sleeps UPDATE_CHECK_INTERVAL seconds (default 6h, min 1h to avoid hammering)
  - Calls check_for_update(force=True) which:
      * Fetches manifest from license server
      * Verifies RSA signature
      * Caches result in checker._cache
  - Logs INFO when up-to-date, WARNING when an update is available
  - Disabled when AUTO_UPDATE_CHECK_ENABLED=false

The asyncio task is owned by api/main.py lifespan and is cancelled on shutdown.
"""

import asyncio
import os

from loguru import logger

_INTERVAL_DEFAULT  = 21600    # 6 hours
_INTERVAL_MIN      = 3600     # never poll faster than once an hour
_RETRY_INTERVAL    = 900      # 15 minutes after a transient failure
_STARTUP_DELAY     = 30       # let the API finish warming up before first check


def _interval() -> int:
    raw = os.getenv("UPDATE_CHECK_INTERVAL", "")
    try:
        v = int(raw) if raw else _INTERVAL_DEFAULT
    except ValueError:
        v = _INTERVAL_DEFAULT
    return max(v, _INTERVAL_MIN)


def _enabled() -> bool:
    return os.getenv("AUTO_UPDATE_CHECK_ENABLED", "true").lower() == "true"


def _get_channel() -> str:
    """Read the operator-selected channel from system_config (default: stable)."""
    try:
        from ...database.connection import SessionLocal
        from ...database.models import SystemConfig
    except Exception:
        return "stable"
    db = SessionLocal()
    try:
        cfg = db.query(SystemConfig).filter_by(key="update_channel").first()
        return cfg.value if cfg else "stable"
    finally:
        db.close()


async def _run_one_check() -> bool:
    """One pass: fetch manifest, log result. Returns True on hard failure (so caller can back off)."""
    from .checker import check_for_update
    from .manager import get_current_version

    current = get_current_version()
    channel = _get_channel()

    try:
        manifest, error = await check_for_update(current, channel, force=True)
    except Exception as exc:
        logger.warning("Update auto-check raised unexpectedly: {}", exc)
        return True

    if error:
        logger.info("Update auto-check ({}): {}", channel, error)
        return True

    if manifest is None:
        logger.info("Update auto-check ({}): up to date on {}", channel, current)
        return False

    new_version = manifest.get("version", "?")
    logger.warning(
        "Update auto-check ({}): new version available {} → {} (current {})",
        channel, current, new_version, current,
    )
    return False


async def run_auto_update_check_loop():
    """Long-running asyncio task — poll manifest every UPDATE_CHECK_INTERVAL seconds."""
    if not _enabled():
        logger.info("Auto update-check disabled (AUTO_UPDATE_CHECK_ENABLED=false)")
        return

    await asyncio.sleep(_STARTUP_DELAY)

    interval = _interval()
    logger.info("Auto update-check started (interval={}s)", interval)

    while True:
        had_failure = await _run_one_check()
        await asyncio.sleep(_RETRY_INTERVAL if had_failure else interval)
