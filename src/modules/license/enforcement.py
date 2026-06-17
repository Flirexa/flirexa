"""License-tier enforcement for live server fleet.

Runs on a periodic worker tick (and on every license activation/refresh):

- If the install just lost the `multi_server` feature (subscription expired,
  was downgraded, or the operator removed their paid key), every server beyond
  the FREE quota is stopped and parked with
  `lifecycle_status = SUSPENDED_NO_LICENSE`. Their data stays — clients,
  configs, keys are untouched — so the operator just needs to re-activate to
  bring everything back.

  The FREE quota is: up to **one LOCAL server of each `wireguard` / `amneziawg`**
  protocol (max 2), running on the install box itself. Remote/agent servers and
  proxy protocols (hysteria2 / tuic) are paid-only and always suspended on FREE.

- If the install gained `multi_server` again (renewal / new purchase), every
  `SUSPENDED_NO_LICENSE` server is moved back to OFFLINE. Operator can click
  Start manually; we don't auto-start so we don't surprise anyone with a
  bunch of interfaces coming up at once during a renewal flow.

The "kept FREE quota" picks the *oldest* server of each protocol type — that's
typically the auto-provisioned one from install, which the operator wants kept.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from ...database.connection import SessionLocal
from ...database.models import Server, ServerLifecycleStatus, ServerStatus


# Server types that count toward the FREE 1-per-protocol quota.
# Proxy protocols (hysteria2 / tuic) are intentionally absent — they're paid
# (extra_protocols), so on FREE they fall through to "suspend".
_FREE_QUOTA_TYPES = {"wireguard", "amneziawg"}


def _is_remote_server(s) -> bool:
    """True if the server is managed off-box (SSH or agent). The FREE tier only
    covers servers running on the install box itself; remote/agent servers are
    subscription-only, so on FREE they are always suspended regardless of the
    per-protocol quota."""
    return bool(getattr(s, "ssh_host", None)) or bool(getattr(s, "agent_url", None))

# ── Grace-on-suspend ──────────────────────────────────────────────────────────
# Don't drop the fleet on a *single* FREE-tier read. A transient FREE
# (license re-issue, network blip, parse hiccup) must not suspend live servers.
# We only suspend once FREE has PERSISTED past this window. A paid read at any
# point clears the timer. 0 = legacy immediate-suspend behaviour.
_SUSPEND_GRACE_H = int(os.getenv("LICENSE_SUSPEND_GRACE_HOURS", "72"))

# Persisted so a restart loop can't reset the grace clock (same rationale as
# the persisted first-startup time in online_validator). Lives in data/, which
# is excluded from the update tarball.
_STATE_FILE = Path(__file__).resolve().parents[3] / "data" / "license_suspend_state.json"


def _load_first_free() -> Optional[float]:
    """Epoch seconds of the first FREE observation in the current FREE streak,
    or None if not currently in a streak."""
    try:
        with open(_STATE_FILE) as f:
            v = json.load(f).get("first_free_at")
        return float(v) if v is not None else None
    except Exception:
        return None


def _save_first_free(ts: float) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump({"first_free_at": ts}, f)
        os.replace(tmp, _STATE_FILE)
    except Exception as exc:
        logger.warning("License grace: could not persist first_free_at: {}", exc)


def _clear_first_free() -> None:
    try:
        _STATE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _stop_server_runtime(server: Server) -> None:
    """Best-effort: bring the interface / proxy service down.

    Routes through ServerManager so local-vs-remote dispatch is handled the
    same way as the rest of the codebase. Without this, a remote server whose
    `interface` field collides with a local interface name (e.g. two servers
    both named `wg0`) would cause a local `wg-quick down` to fire and tear
    down the panel host's own tunnel — that's exactly the regression that
    rolled out in 1.5.86 and took prod offline for ~22h.
    """
    own_session = SessionLocal()
    try:
        from ...core.server_manager import ServerManager
        ServerManager(own_session).stop_server(server.id)
    except Exception as exc:
        logger.warning(
            "License enforcement: could not stop server id={} ({}): {}",
            server.id, server.name, exc,
        )
    finally:
        own_session.close()


def reconcile(db: Optional[Session] = None) -> dict:
    """Bring server fleet in line with the current license tier.

    Returns a small dict for logging / API exposure:
        {"suspended": int, "unsuspended": int, "tier": "free|paid"}
    """
    from .manager import get_license_manager

    own_session = db is None
    if db is None:
        db = SessionLocal()

    suspended = 0
    unsuspended = 0
    try:
        info = get_license_manager().get_license_info()
        has_multi_server = info.has_feature("multi_server")
        tier_label = "paid" if has_multi_server else "free"

        if has_multi_server:
            # Paid: end any FREE grace streak so a later blip starts fresh.
            _clear_first_free()
            # Restore anything previously suspended. Don't auto-start — the
            # operator clicks Start when they're ready.
            rows = (
                db.query(Server)
                .filter(Server.lifecycle_status == ServerLifecycleStatus.SUSPENDED_NO_LICENSE.value)
                .all()
            )
            for s in rows:
                s.lifecycle_status = ServerLifecycleStatus.OFFLINE.value
                s.status = ServerStatus.OFFLINE
                unsuspended += 1
            if rows:
                db.commit()
                logger.info(
                    "License enforcement: paid tier active — un-suspended {} server(s)",
                    unsuspended,
                )
            return {"suspended": 0, "unsuspended": unsuspended, "tier": tier_label}

        # FREE / no-multi-server tier. Debounce the suspend behind a grace
        # window so a transient FREE read can't drop the live fleet.
        if _SUSPEND_GRACE_H > 0:
            now = time.time()
            first_free = _load_first_free()
            if first_free is None:
                _save_first_free(now)
                logger.warning(
                    "License enforcement: FREE tier observed — grace started, "
                    "fleet stays up; will suspend in {}h if not restored.",
                    _SUSPEND_GRACE_H,
                )
                return {"suspended": 0, "unsuspended": 0, "tier": tier_label,
                        "grace_remaining_h": float(_SUSPEND_GRACE_H)}
            elapsed_h = (now - first_free) / 3600.0
            if elapsed_h < _SUSPEND_GRACE_H:
                remaining = round(_SUSPEND_GRACE_H - elapsed_h, 1)
                logger.warning(
                    "License enforcement: FREE tier persists — {}h/{}h grace "
                    "elapsed, fleet still up (suspend in {}h).",
                    round(elapsed_h, 1), _SUSPEND_GRACE_H, remaining,
                )
                return {"suspended": 0, "unsuspended": 0, "tier": tier_label,
                        "grace_remaining_h": remaining}
            logger.warning(
                "License enforcement: FREE tier grace ({}h) elapsed — "
                "suspending fleet now.", _SUSPEND_GRACE_H,
            )

        # Grace elapsed (or disabled): keep the *oldest* of each FREE-quota
        # protocol; suspend every other server.
        all_servers = db.query(Server).order_by(Server.id.asc()).all()
        kept_per_type: set[str] = set()
        for s in all_servers:
            if s.lifecycle_status == ServerLifecycleStatus.SUSPENDED_NO_LICENSE.value:
                continue  # already suspended, leave alone
            # FREE keeps up to one LOCAL server of each free-quota protocol
            # (wireguard + amneziawg) on the install box. Everything else is
            # paid-only and gets suspended: remote/agent servers, proxy
            # protocols (hysteria2/tuic), and any excess beyond one-per-protocol.
            keep = (
                not _is_remote_server(s)
                and s.server_type in _FREE_QUOTA_TYPES
                and s.server_type not in kept_per_type
            )
            if keep:
                kept_per_type.add(s.server_type)
                continue
            # Excess / remote / proxy: suspend.
            _stop_server_runtime(s)
            s.lifecycle_status = ServerLifecycleStatus.SUSPENDED_NO_LICENSE.value
            s.status = ServerStatus.OFFLINE
            suspended += 1

        if suspended:
            db.commit()
            logger.warning(
                "License enforcement: FREE tier active — suspended {} excess server(s) "
                "(re-activate paid license to restore)",
                suspended,
            )
        return {"suspended": suspended, "unsuspended": 0, "tier": tier_label}
    finally:
        if own_session:
            db.close()
