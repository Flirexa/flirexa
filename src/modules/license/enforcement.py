"""License-tier enforcement for live server fleet.

Runs on a periodic worker tick (and on every license activation/refresh):

- If the install just lost the `multi_server` feature (subscription expired,
  was downgraded, or the operator removed their paid key), every server beyond
  the FREE per-protocol quota (1 of each `server_type`) is stopped and parked
  with `lifecycle_status = SUSPENDED_NO_LICENSE`. Their data stays — clients,
  configs, keys are untouched — so the operator just needs to re-activate to
  bring everything back.

- If the install gained `multi_server` again (renewal / new purchase), every
  `SUSPENDED_NO_LICENSE` server is moved back to OFFLINE. Operator can click
  Start manually; we don't auto-start so we don't surprise anyone with a
  bunch of interfaces coming up at once during a renewal flow.

The "kept FREE quota" picks the *oldest* server of each protocol type — that's
typically the auto-provisioned one from install, which the operator wants kept.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from ...database.connection import SessionLocal
from ...database.models import Server, ServerLifecycleStatus, ServerStatus


# Server types that count toward the FREE 1-per-protocol quota.
_FREE_QUOTA_TYPES = {"wireguard", "amneziawg"}


def _stop_server_runtime(server: Server) -> None:
    """Best-effort: bring the interface / proxy service down.

    We don't fail the whole sweep if a single stop call errors — the server
    will still be marked SUSPENDED_NO_LICENSE in the DB, which prevents
    re-start via the API. The systemd interface might keep running until the
    box reboots, which is acceptable for graceful degradation.
    """
    try:
        if server.server_type == "amneziawg":
            from ...core.amneziawg import AmneziaWGManager
            mgr = AmneziaWGManager(interface=server.interface)
        elif server.server_type in ("hysteria2", "tuic"):
            # Proxy services have their own stop_service() on the manager;
            # construct the matching manager and stop it. Importing lazily
            # so this module stays cheap to import elsewhere.
            from ...core.server_manager import ServerManager
            ServerManager(SessionLocal()).stop_server(server.id)
            return
        else:
            from ...core.wireguard import WireGuardManager
            mgr = WireGuardManager(interface=server.interface)
        try:
            mgr.stop_interface()
        finally:
            mgr.close()
    except Exception as exc:
        logger.warning(
            "License enforcement: could not stop server id={} ({}): {}",
            server.id, server.name, exc,
        )


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

        # FREE / no-multi-server tier: keep the *oldest* of each
        # FREE-quota protocol; suspend every other server.
        all_servers = db.query(Server).order_by(Server.id.asc()).all()
        kept_per_type: set[str] = set()
        for s in all_servers:
            if s.lifecycle_status == ServerLifecycleStatus.SUSPENDED_NO_LICENSE.value:
                continue  # already suspended, leave alone
            if s.server_type in _FREE_QUOTA_TYPES and s.server_type not in kept_per_type:
                kept_per_type.add(s.server_type)
                continue
            # Excess: suspend.
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
