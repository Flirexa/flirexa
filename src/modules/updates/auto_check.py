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


def _auto_apply_enabled() -> bool:
    """
    Whether the panel should auto-apply updates as soon as it sees one on
    the configured channel. Defaults to True for installs that never set
    the value (covers fresh installs that ran migration 028 on an empty
    DB and got 'true' written; also covers very old installs predating
    the toggle that haven't seen the migration yet — for those we'd rather
    err on the side of "stay current" since they explicitly chose to
    upgrade by hitting Apply on the previous step).
    """
    try:
        from ...database.connection import SessionLocal
        from ...database.models import SystemConfig
    except Exception:
        return True
    db = SessionLocal()
    try:
        cfg = db.query(SystemConfig).filter_by(key="updates_auto_apply").first()
        if cfg is None:
            return True
        return (cfg.value or "").strip().lower() in ("1", "true", "yes", "on")
    finally:
        db.close()


# If a previous auto-apply attempt for the same target version FAILED within
# this window, skip retrying. Without this guard a permanent failure (DKMS
# can't build the new module, disk full, dependency conflict, …) would have
# the panel re-attempt the same broken upgrade every check interval — every
# 6 hours by default — flooding the update history with FAILED rows and
# wasting the operator's time. Manual `/updates/apply` always bypasses this:
# only `started_by='auto'` records count toward the cooldown.
_AUTO_APPLY_COOLDOWN_HOURS = 24


async def _try_auto_apply(manifest: dict, current_version: str, channel: str) -> None:
    """
    Trigger apply_update for this manifest if it's safe to do so.

    Safety gates:
      - auto-apply must be enabled (`updates_auto_apply` system config)
      - manifest version must be strictly newer than current
      - no other update may already be in flight
      - the box must not be in maintenance mode (operator paused work)
      - the same version must not have failed via auto-apply recently
        (cooldown window above)
    Failures here are logged but never crash the auto-check loop.
    """
    if not _auto_apply_enabled():
        return
    try:
        from .manager import apply_update, is_newer
        from ...modules.operational_mode import (
            get_active_update_state,
            get_explicit_maintenance_state,
        )
        from ...database.connection import SessionLocal
        from ...database.models import UpdateHistory, UpdateStatus
    except Exception as e:
        logger.warning("auto-apply: import failed: {}", e)
        return

    new_version = manifest.get("version")
    if not new_version or not is_newer(new_version, current_version):
        return

    db = SessionLocal()
    try:
        active, _, active_id = get_active_update_state(db)
        if active:
            logger.info("auto-apply: skipped — update {} already in flight", active_id)
            return
        maintenance = get_explicit_maintenance_state(db)
        if maintenance.enabled:
            logger.info("auto-apply: skipped — panel is in maintenance mode")
            return

        # Cooldown: don't auto-retry a version we already failed to apply
        # automatically in the last 24h. Operator can still apply manually.
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=_AUTO_APPLY_COOLDOWN_HOURS)
        recent_failed_auto = (
            db.query(UpdateHistory)
            .filter(
                UpdateHistory.to_version == new_version,
                UpdateHistory.started_by == "auto",
                UpdateHistory.status == UpdateStatus.FAILED,
                UpdateHistory.started_at >= cutoff,
            )
            .order_by(UpdateHistory.started_at.desc())
            .first()
        )
        if recent_failed_auto:
            logger.warning(
                "auto-apply: skipped — {} failed via auto-apply at {} "
                "(cooldown {}h, retry manually via Apply button)",
                new_version,
                recent_failed_auto.started_at.isoformat() if recent_failed_auto.started_at else "?",
                _AUTO_APPLY_COOLDOWN_HOURS,
            )
            return

        try:
            update_id = await apply_update(manifest, started_by="auto", db=db)
            logger.warning(
                "auto-apply: started update {} → {} on channel {} (id={})",
                current_version, new_version, channel, update_id,
            )
        except Exception as e:
            logger.error("auto-apply: failed to start: {}", e)
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
    # Optionally auto-apply (gated by `updates_auto_apply` system config).
    await _try_auto_apply(manifest, current, channel)
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
