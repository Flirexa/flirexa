"""
Health Monitoring Routes — extended

GET  /api/v1/health/system                 — system health (quick by default)
GET  /api/v1/health/system?full=1          — full system health (all checks)
POST /api/v1/health/system/refresh         — force full refresh
GET  /api/v1/health/servers                — all servers (quick by default)
GET  /api/v1/health/servers?full=1         — all servers full check
GET  /api/v1/health/servers/{id}           — single server full health
POST /api/v1/health/servers/{id}/refresh   — force-refresh single server
GET  /api/v1/health/events                 — health event log
GET  /api/v1/health/issues                 — currently active issues
GET  /api/v1/health/components/{name}/history — component history
GET  /api/v1/health/servers/{id}/history   — server history
"""

import json
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy.orm import Session

from ...database.connection import get_db
from ...database.models import Server
from ...modules.health.checker import SystemHealthChecker
from ...modules.health.server_checker import ServerHealthChecker
from ...modules.health.cache import health_cache
from ...modules.health.state_store import health_state_store

router = APIRouter()

# Cache TTLs (seconds)
_SYSTEM_TTL_QUICK = 30
_SYSTEM_TTL_FULL  = 60
_SERVER_TTL_QUICK = 30
_SERVER_TTL_FULL  = 60


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_drift_info(server: Optional[Server]) -> dict:
    """Build a drift info dict from a Server ORM object."""
    if server is None:
        return {"detected": False}
    details = None
    if server.drift_details:
        try:
            details = json.loads(server.drift_details)
        except Exception:
            details = server.drift_details
    return {
        "detected": bool(server.drift_detected),
        "details": details,
        "detected_at": server.drift_detected_at.isoformat() if server.drift_detected_at else None,
        "last_reconcile_at": server.last_reconcile_at.isoformat() if server.last_reconcile_at else None,
    }


def _state_to_history(state) -> dict:
    """Convert a TargetState to a history dict for the API."""
    if state is None:
        return {}
    import time
    duration = None
    if state.last_status_change:
        try:
            from datetime import datetime, timezone
            t = datetime.fromisoformat(state.last_status_change)
            duration = int((datetime.now(timezone.utc) - t).total_seconds())
        except Exception:
            pass
    return {
        "current_status": state.current_status,
        "previous_status": state.previous_status,
        "last_status_change": state.last_status_change,
        "duration_seconds": duration,
        "last_healthy": state.last_healthy,
        "last_error": state.last_error,
        "last_checked": state.last_checked,
    }


# ── System Health ─────────────────────────────────────────────────────────────

@router.get("/system")
def get_system_health(
    full: bool = Query(False, description="Run full check (includes external HTTP pings)"),
    db: Session = Depends(get_db),
):
    """Return system health. Quick mode by default (fast, no external calls)."""
    cache_key = "system:full" if full else "system:quick"
    cached = health_cache.get(cache_key)
    if cached is not None:
        return cached

    checker = SystemHealthChecker(db_session=db)
    result = (checker.check_all() if full else checker.check_quick()).to_dict()

    # Attach state history for each component
    for comp in result.get("components", []):
        state = health_state_store.get_component_state(comp["name"])
        comp["history"] = _state_to_history(state)

    health_cache.set(cache_key, result, ttl=_SYSTEM_TTL_FULL if full else _SYSTEM_TTL_QUICK)
    return result


@router.post("/system/refresh")
def refresh_system_health(db: Session = Depends(get_db)):
    """Force full system health check, bypass cache."""
    health_cache.delete("system:quick")
    health_cache.delete("system:full")
    checker = SystemHealthChecker(db_session=db)
    result = checker.check_all().to_dict()
    for comp in result.get("components", []):
        state = health_state_store.get_component_state(comp["name"])
        comp["history"] = _state_to_history(state)
    health_cache.set("system:full", result, ttl=_SYSTEM_TTL_FULL)
    health_cache.set("system:quick", result, ttl=_SYSTEM_TTL_QUICK)
    return result


# ── Server Health ─────────────────────────────────────────────────────────────

@router.get("/servers")
def get_all_servers_health(
    full: bool = Query(False, description="Run full check (wg stats + system metrics)"),
    db: Session = Depends(get_db),
):
    """Return health for all servers in parallel. Quick by default."""
    servers = db.query(Server).all()
    checker = ServerHealthChecker(db_session=db)
    results = []
    servers_to_check = []

    ttl = _SERVER_TTL_FULL if full else _SERVER_TTL_QUICK

    for srv in servers:
        cache_key = f"server:{srv.id}:{'full' if full else 'quick'}"
        cached = health_cache.get(cache_key)
        if cached is not None:
            results.append(cached)
        else:
            servers_to_check.append(srv)

    if servers_to_check:
        fresh = checker.check_all(servers_to_check, quick=not full)
        for h in fresh:
            data = h.to_dict()
            # Attach state history
            state = health_state_store.get_server_state(h.server_id)
            data["history"] = _state_to_history(state)
            cache_key = f"server:{h.server_id}:{'full' if full else 'quick'}"
            health_cache.set(cache_key, data, ttl=ttl)
            results.append(data)

    results.sort(key=lambda r: r["server_id"])

    # Augment every result with fresh drift state from DB (always current, not cached)
    drift_map = {
        s.id: s for s in db.query(Server).filter(
            Server.id.in_([r["server_id"] for r in results])
        ).all()
    }
    for r in results:
        srv = drift_map.get(r["server_id"])
        r["drift"] = _build_drift_info(srv)

    priority = {"error": 4, "offline": 3, "warning": 2, "unknown": 1, "healthy": 0}
    overall = "healthy"
    if results:
        worst = max(results, key=lambda r: priority.get(r["status"], 0))
        overall = worst["status"] if priority.get(worst["status"], 0) > 0 else "healthy"

    healthy_count = sum(1 for r in results if r["status"] == "healthy")
    warning_count = sum(1 for r in results if r["status"] == "warning")
    offline_count = sum(1 for r in results if r["status"] in ("offline", "error"))

    return {
        "status": overall,
        "total": len(results),
        "healthy": healthy_count,
        "warning": warning_count,
        "offline": offline_count,
        "servers": results,
    }


@router.get("/servers/{server_id}")
def get_server_health(server_id: int, db: Session = Depends(get_db)):
    """Return full detailed health for a single server (cached 60s)."""
    cached = health_cache.get(f"server:{server_id}:full")
    if cached is not None:
        return cached

    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    checker = ServerHealthChecker(db_session=db)
    result = checker.check_server(server, quick=False)
    data = result.to_dict()

    state = health_state_store.get_server_state(server_id)
    data["history"] = _state_to_history(state)
    data["drift"] = _build_drift_info(server)

    health_cache.set(f"server:{server_id}:full", data, ttl=_SERVER_TTL_FULL)
    return data


@router.post("/servers/{server_id}/refresh")
def refresh_server_health(server_id: int, db: Session = Depends(get_db)):
    """Force-refresh full health for a single server."""
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    health_cache.delete(f"server:{server_id}:full")
    health_cache.delete(f"server:{server_id}:quick")

    checker = ServerHealthChecker(db_session=db)
    result = checker.check_server(server, quick=False)
    data = result.to_dict()

    state = health_state_store.get_server_state(server_id)
    data["history"] = _state_to_history(state)
    data["drift"] = _build_drift_info(server)

    health_cache.set(f"server:{server_id}:full", data, ttl=_SERVER_TTL_FULL)
    return data


# ── Events & History ──────────────────────────────────────────────────────────

@router.get("/events")
def get_health_events(
    target_type: Optional[str] = Query(None, description="Filter: 'component' or 'server'"),
    target_id:   Optional[str] = Query(None, description="Filter by target ID"),
    severity:    Optional[str] = Query(None, description="Filter: 'info', 'warning', 'critical'"),
    limit:       int           = Query(100, ge=1, le=500),
):
    """Return health event log (state transitions, last 1000 events in memory)."""
    events = health_state_store.get_events(
        target_type=target_type,
        target_id=target_id,
        severity=severity,
        limit=limit,
    )
    return {
        "total": len(events),
        "events": [
            {
                "id":          e.id,
                "timestamp":   e.timestamp,
                "target_type": e.target_type,
                "target_id":   e.target_id,
                "target_name": e.target_name,
                "old_status":  e.old_status,
                "new_status":  e.new_status,
                "severity":    e.severity,
                "event_code":  e.event_code,
                "message":     e.message,
                "details":     e.details,
            }
            for e in events
        ],
    }


@router.get("/issues")
def get_active_issues():
    """Return currently active health issues (degraded components/servers)."""
    issues = health_state_store.get_active_issues()
    recoveries = health_state_store.get_recent_recoveries(since_seconds=3600)
    return {
        "active_issues": issues,
        "recent_recoveries": [
            {
                "timestamp":   e.timestamp,
                "target_name": e.target_name,
                "target_type": e.target_type,
                "old_status":  e.old_status,
                "message":     e.message,
            }
            for e in recoveries
        ],
    }


@router.get("/components/{component_name}/history")
def get_component_history(component_name: str, events_limit: int = Query(50, ge=1, le=200)):
    """Return history for a specific system component."""
    state = health_state_store.get_component_state(component_name)
    if state is None:
        return {"component": component_name, "history": None, "events": []}
    events = health_state_store.get_events(
        target_type="component", target_id=component_name, limit=events_limit
    )
    return {
        "component": component_name,
        "history": _state_to_history(state),
        "events": [
            {
                "id": e.id, "timestamp": e.timestamp,
                "old_status": e.old_status, "new_status": e.new_status,
                "severity": e.severity, "message": e.message,
            }
            for e in events
        ],
    }


@router.get("/servers/{server_id}/history")
def get_server_history(server_id: int, events_limit: int = Query(50, ge=1, le=200)):
    """Return state history and event log for a specific server."""
    state = health_state_store.get_server_state(server_id)
    events = health_state_store.get_events(
        target_type="server", target_id=str(server_id), limit=events_limit
    )
    return {
        "server_id": server_id,
        "history": _state_to_history(state),
        "events": [
            {
                "id": e.id, "timestamp": e.timestamp,
                "old_status": e.old_status, "new_status": e.new_status,
                "severity": e.severity, "message": e.message,
            }
            for e in events
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# REAL-STATE FULL HEALTH ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/full")
def get_full_health(db: Session = Depends(get_db)):
    """
    Comprehensive real-state health check.

    Checks DB, WG servers, proxy servers, license, worker, and business
    invariants. Returns OK / DEGRADED / FAIL with a list of problems.

    Response format:
        status:   "ok" | "degraded" | "fail"
        problems: list of problem strings
        details:  component-by-component results
    """
    import time
    from datetime import datetime, timezone, timedelta
    from ...database.models import (
        Server, ServerStatus, Client, ClientStatus,
    )
    from ...modules.subscription.subscription_models import (
        ClientPortalPayment, ClientPortalSubscription,
    )

    problems = []
    details = {}
    start = time.monotonic()

    # ── 1. Database ──────────────────────────────────────────────────────────
    try:
        from sqlalchemy import text as _sql
        db.execute(_sql("SELECT 1"))
        details["database"] = {"status": "ok"}
    except Exception as exc:
        problems.append(f"database: unreachable ({exc})")
        details["database"] = {"status": "fail", "error": str(exc)}

    # ── 2. WG servers ────────────────────────────────────────────────────────
    servers = db.query(Server).filter(Server.lifecycle_status != "offline").all()
    wg_issues = []
    for srv in servers:
        if srv.agent_mode == "agent" and srv.agent_url:
            try:
                import httpx
                url = srv.agent_url.rstrip("/")
                r = httpx.get(f"{url}/health", headers={"X-Api-Key": srv.agent_api_key or ""}, timeout=5)
                if r.status_code >= 400:
                    wg_issues.append(f"{srv.name}: agent returned {r.status_code}")
            except Exception as exc:
                wg_issues.append(f"{srv.name}: agent unreachable ({exc})")
        # SSH/local servers: check drift flag as proxy for reachability
        elif srv.drift_detected:
            wg_issues.append(f"{srv.name}: drift detected ({srv.drift_details or 'unknown'})")
    if wg_issues:
        for issue in wg_issues:
            problems.append(f"wg_server: {issue}")
        details["wg_servers"] = {"status": "degraded", "issues": wg_issues}
    else:
        details["wg_servers"] = {"status": "ok", "checked": len(servers)}

    # ── 3. License ───────────────────────────────────────────────────────────
    try:
        from ...modules.license.manager import get_license_manager
        lm = get_license_manager(db)
        valid, info = lm.validate_license()
        if not valid:
            problems.append(f"license: invalid — {info}")
            details["license"] = {"status": "fail", "info": info}
        else:
            # Warn if expiring within 14 days
            exp = info.get("expires_at") if isinstance(info, dict) else None
            if exp:
                try:
                    from datetime import datetime, timezone
                    exp_dt = datetime.fromisoformat(exp) if isinstance(exp, str) else exp
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    days_left = (exp_dt - datetime.now(timezone.utc)).days
                    if days_left < 14:
                        problems.append(f"license: expiring in {days_left} days")
                        details["license"] = {"status": "degraded", "days_left": days_left}
                    else:
                        details["license"] = {"status": "ok", "days_left": days_left}
                except Exception:
                    details["license"] = {"status": "ok"}
            else:
                details["license"] = {"status": "ok"}
    except Exception as exc:
        details["license"] = {"status": "unknown", "error": str(exc)}

    # ── 4. Worker (check last worker heartbeat via DB) ───────────────────────
    try:
        from ...database.models import SystemConfig
        row = db.query(SystemConfig).filter(SystemConfig.key == "worker_last_heartbeat").first()
        if row and row.value:
            from datetime import datetime, timezone, timedelta
            last_beat = datetime.fromisoformat(row.value)
            if last_beat.tzinfo is None:
                last_beat = last_beat.replace(tzinfo=timezone.utc)
            age_min = (datetime.now(timezone.utc) - last_beat).total_seconds() / 60
            if age_min > 10:
                problems.append(f"worker: no heartbeat for {age_min:.0f}min (last: {row.value})")
                details["worker"] = {"status": "degraded", "last_heartbeat": row.value, "age_minutes": round(age_min)}
            else:
                details["worker"] = {"status": "ok", "last_heartbeat": row.value, "age_minutes": round(age_min)}
        else:
            details["worker"] = {"status": "unknown", "note": "no heartbeat key in system_config"}
    except Exception as exc:
        details["worker"] = {"status": "unknown", "error": str(exc)}

    # ── 5. Business invariants (fast DB-only checks, no WG connection) ───────
    try:
        now = datetime.now(timezone.utc)

        # expired+enabled clients (critical)
        expired_enabled = db.query(Client).filter(
            Client.enabled == True,
            Client.status.in_([ClientStatus.EXPIRED, ClientStatus.TRAFFIC_EXCEEDED]),
        ).count()

        # completed payments without active sub (last 7 days)
        cutoff = now - timedelta(days=7)
        payments_recent = db.query(ClientPortalPayment).filter(
            ClientPortalPayment.status == "completed",
            ClientPortalPayment.completed_at >= cutoff,
        ).all()
        orphaned_payments = 0
        for p in payments_recent:
            active = db.query(ClientPortalSubscription).filter(
                ClientPortalSubscription.user_id == p.user_id,
                ClientPortalSubscription.status == "active",
            ).first()
            if not active:
                orphaned_payments += 1

        # stale pending payments
        stale_pending = db.query(ClientPortalPayment).filter(
            ClientPortalPayment.status == "pending",
            ClientPortalPayment.created_at < now - timedelta(hours=48),
        ).count()

        bv_issues = []
        if expired_enabled > 0:
            bv_issues.append(f"{expired_enabled} clients with expired/traffic_exceeded status but enabled=True")
            problems.append(f"invariant: {expired_enabled} expired clients still enabled (access leak)")
        if orphaned_payments > 0:
            bv_issues.append(f"{orphaned_payments} completed payments in last 7d without active subscription")
            problems.append(f"invariant: {orphaned_payments} payments completed but no active sub (money loss risk)")
        if stale_pending > 0:
            bv_issues.append(f"{stale_pending} pending payments older than 48h")

        details["invariants"] = {
            "status": "fail" if (expired_enabled > 0 or orphaned_payments > 0) else (
                "degraded" if stale_pending > 0 else "ok"
            ),
            "expired_enabled_clients": expired_enabled,
            "orphaned_payments_7d": orphaned_payments,
            "stale_pending_payments": stale_pending,
            "issues": bv_issues,
        }
    except Exception as exc:
        details["invariants"] = {"status": "unknown", "error": str(exc)}

    # ── 6. Deep-check summary (cached from last BV run, no live WG connections) ─
    try:
        from ...database.models import SystemConfig as _SC

        def _cfg_val(key: str, default: str = "0") -> str:
            row = db.query(_SC).filter(_SC.key == key).first()
            return row.value if (row and row.value is not None) else default

        bw_mismatches = int(_cfg_val("bv_bandwidth_mismatches", "0"))
        peer_drift_servers = int(_cfg_val("bv_peer_drift_servers", "0"))
        proxy_drift = int(_cfg_val("bv_proxy_config_drift", "0"))
        worker_stale_cached = _cfg_val("bv_worker_stale", "false") == "true"
        last_deep_check = _cfg_val("bv_last_deep_check", "")

        deep_status = "ok"
        deep_issues = []
        if bw_mismatches > 0:
            deep_issues.append(f"{bw_mismatches} client(s) with bandwidth_limit but no TC rule")
            problems.append(f"drift: {bw_mismatches} bandwidth TC rule(s) missing")
            deep_status = "degraded"
        if peer_drift_servers > 0:
            deep_issues.append(f"{peer_drift_servers} WG server(s) with peer drift")
            deep_status = "degraded"
        if proxy_drift > 0:
            deep_issues.append(f"{proxy_drift} proxy server(s) with config drift")
            problems.append(f"drift: {proxy_drift} proxy config(s) out of sync")
            deep_status = "degraded"
        if worker_stale_cached:
            deep_issues.append("worker heartbeat stale (from last BV run)")
            deep_status = "degraded"

        details["deep_checks"] = {
            "status": deep_status,
            "bandwidth_mismatch_count": bw_mismatches,
            "peer_drift_server_count": peer_drift_servers,
            "proxy_config_drift_count": proxy_drift,
            "worker_stale": worker_stale_cached,
            "last_deep_check": last_deep_check or None,
            "issues": deep_issues,
            "note": "Cached from last BusinessValidator run (every 30 min); use /repair to force recheck",
        }
    except Exception as exc:
        details["deep_checks"] = {"status": "unknown", "error": str(exc)}

    # ── 7. Summary ───────────────────────────────────────────────────────────
    elapsed_ms = round((time.monotonic() - start) * 1000)

    if any(d.get("status") == "fail" for d in details.values()):
        status = "fail"
    elif problems:
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "problems": problems,
        "details": details,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": elapsed_ms,
    }
