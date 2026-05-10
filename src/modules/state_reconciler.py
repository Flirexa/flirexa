"""
VPN Management Studio — Configuration Drift Detector & Reconciler

Periodically compares DB state vs live WireGuard interface state for every
ONLINE server. Safe drifts (missing peers) are auto-reconciled; unsafe drifts
(interface down, agent unreachable, subnet mismatch) set the server's
drift_detected flag so the UI can show a 🟠 DRIFTED badge.

Drift categories
----------------
SAFE   — a DB peer is missing from the live interface → re-add via wg set
UNSAFE — interface is down / agent broken / subnet mismatch → flag DRIFTED

Prefix for all log lines: [RECONCILE]
"""

from __future__ import annotations

import json
import ipaddress
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from loguru import logger
from sqlalchemy.orm import Session

from ..database.connection import SessionLocal
from ..database.models import Server, Client, ServerStatus, ClientStatus, ServerLifecycleStatus


# Rate-limit interface auto-recovery to one attempt per 5 minutes per server,
# so a permanently broken interface doesn't get hammered every reconciler tick.
_LAST_RECOVERY_ATTEMPT: Dict[int, datetime] = {}
_RECOVERY_COOLDOWN_SECONDS = 300


# ─── helpers ─────────────────────────────────────────────────────────────────

def _wg_manager(server: Server):
    """Return the correct WireGuardManager subclass for the server."""
    ssh_kwargs = dict(
        interface=server.interface,
        config_path=server.config_path,
        ssh_host=server.ssh_host,
        ssh_port=server.ssh_port or 22,
        ssh_user=server.ssh_user or "root",
        ssh_password=server.ssh_password,
        ssh_private_key=server.ssh_private_key,
    )
    if server.server_type == "amneziawg":
        from ..core.amneziawg import AmneziaWGManager
        return AmneziaWGManager(
            **ssh_kwargs,
            jc=server.awg_jc or 4,
            jmin=server.awg_jmin or 50,
            jmax=server.awg_jmax or 100,
            s1=server.awg_s1 or 80,
            s2=server.awg_s2 or 40,
            h1=server.awg_h1 or 0,
            h2=server.awg_h2 or 0,
            h3=server.awg_h3 or 0,
            h4=server.awg_h4 or 0,
        )
    from ..core.wireguard import WireGuardManager
    return WireGuardManager(**ssh_kwargs)


def _agent_request_with_retries(
    server: Server, path: str, *, retries: int = 2, backoff_sec: float = 2.0
) -> Optional[dict]:
    """GET ``{agent_url}{path}`` with a small retry budget for transient blips.

    Home-hosted agents on port-forwarded connections lose 5-30 seconds at a
    time when the ISP shuffles routes or NAT entries expire. We retry up to
    ``retries`` extra times with a short backoff before giving up — that
    catches almost every real-world blip without making fan-out polls
    noticeably slower on a healthy agent (first try succeeds, no retry).

    Returns the parsed JSON dict on success, None on persistent failure.
    """
    import httpx
    url = server.agent_url.rstrip("/") + path
    headers = {"X-Api-Key": server.agent_api_key or ""}
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.get(url, headers=headers, timeout=8)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except Exception as e:
            last_exc = e
            if attempt < retries:
                import time as _time
                _time.sleep(backoff_sec)
    logger.debug(f"[RECONCILE] agent GET {path} failed for {server.name} after {retries + 1} tries: {last_exc}")
    return None


def _agent_get_peers(server: Server) -> Optional[List[dict]]:
    """Fetch peer list via /stats with retries; fall back to last-known cache."""
    from ..core import agent_health_cache as _cache
    data = _agent_request_with_retries(server, "/stats")
    if data is not None:
        peers = data.get("peers", [])
        _cache.record_stats(server.agent_url, peers)
        return peers
    cached = _cache.get_cached_stats(server.agent_url)
    if cached is not None:
        peers, age = cached
        logger.info(
            f"[RECONCILE] {server.name}: agent /stats unreachable, using cached peers ({age}s old)"
        )
        return peers
    return None


def _agent_is_up(server: Server) -> bool:
    """Quick reachability check via /health with retries.

    A successful probe also refreshes the health cache so server_checker
    and other consumers can show the agent as 'recently alive' even during
    the next blip.
    """
    from ..core import agent_health_cache as _cache
    data = _agent_request_with_retries(server, "/health", retries=1, backoff_sec=1.0)
    if data is not None:
        _cache.record_health(server.agent_url, data)
        return True
    return False


def _subnet_of_server(server: Server) -> Optional[ipaddress.IPv4Network]:
    """Parse address_pool_ipv4 → network. Returns None on parse error."""
    try:
        return ipaddress.IPv4Network(server.address_pool_ipv4, strict=False)
    except Exception:
        return None


def _record_endpoint_observations(
    db: Session, server_id: int, pairs: List[tuple]
) -> None:
    """Record current peer endpoints into peer_endpoint_log for the
    advisory key-sharing detector. Each tuple is (public_key, endpoint).

    To keep the table from exploding, we only insert a row when the
    observed endpoint IP differs from the most recent observation for the
    same client_id. Identical endpoints in consecutive ticks (the common
    case) skip the insert entirely.
    """
    if not pairs:
        return

    from ..database.models import PeerEndpointObservation

    # Resolve pubkeys → client_ids in one query
    pubkeys = [pk for pk, _ in pairs]
    rows = (
        db.query(Client.id, Client.public_key)
        .filter(Client.server_id == server_id, Client.public_key.in_(pubkeys))
        .all()
    )
    pk_to_cid = {pk: cid for cid, pk in rows}

    inserts = []
    for pk, endpoint in pairs:
        cid = pk_to_cid.get(pk)
        if cid is None:
            continue
        # Strip the :port off; we only care about the IP for flap detection.
        ip = endpoint.rsplit(":", 1)[0] if endpoint else None
        if not ip:
            continue
        # Skip if last observation has the same IP — keeps row count low.
        last = (
            db.query(PeerEndpointObservation.endpoint_ip)
            .filter(PeerEndpointObservation.client_id == cid)
            .order_by(PeerEndpointObservation.observed_at.desc())
            .limit(1)
            .first()
        )
        if last and last[0] == ip:
            continue
        inserts.append(PeerEndpointObservation(
            client_id=cid, server_id=server_id, endpoint_ip=ip,
        ))
    if inserts:
        db.add_all(inserts)
        # Don't commit here — let the outer reconciliation loop's commit
        # cover it. Avoids a second transaction round-trip per server.


def _try_recover_interface(server: Server, wgm, now: datetime) -> bool:
    """
    Attempt to bring a downed local interface back up. Returns True if a
    recovery attempt was made (regardless of outcome — caller should re-check
    is_interface_up to confirm). Returns False if recovery is being skipped
    (rate-limited, suspended server, remote server, operator-stopped, etc).
    """
    if server.ssh_host or server.agent_url:
        return False
    if server.lifecycle_status == ServerLifecycleStatus.SUSPENDED_NO_LICENSE.value:
        return False
    if server.lifecycle_status == ServerLifecycleStatus.OFFLINE.value:
        # Operator deliberately stopped this server — don't second-guess them.
        return False
    if server.status == ServerStatus.OFFLINE:
        return False

    last = _LAST_RECOVERY_ATTEMPT.get(server.id)
    if last and (now - last).total_seconds() < _RECOVERY_COOLDOWN_SECONDS:
        return False
    _LAST_RECOVERY_ATTEMPT[server.id] = now

    logger.warning(
        f"[RECONCILE] {server.name}: attempting auto-recovery of interface "
        f"{server.interface} (was DOWN, server expected ONLINE)"
    )
    try:
        wgm.start_interface()
    except Exception as exc:
        logger.error(f"[RECONCILE] {server.name}: auto-recovery raised: {exc}")
    return True


# ─── per-server reconciliation ────────────────────────────────────────────────

def reconcile_server(server: Server, db: Session) -> Dict[str, Any]:
    """
    Check and reconcile one server. Updates DB in-place (does NOT commit).
    Returns a result dict suitable for the API response.

    Result fields:
        server_id, server_name, drift_detected (bool),
        issues (list[str]), reconciled (list[str]), error (str|None)
    """
    result: Dict[str, Any] = {
        "server_id": server.id,
        "server_name": server.name,
        "drift_detected": False,
        "issues": [],
        "reconciled": [],
        "error": None,
    }

    now = datetime.now(timezone.utc)

    # ── 1. Determine connection mode and get live peers ───────────────────────
    live_pubkeys: Optional[set] = None
    interface_up: Optional[bool] = None
    wgm = None

    # Collected as (pubkey, endpoint_ip) tuples from whichever code path
    # actually reads the live peers — we feed this into the endpoint-flap
    # observation log below so the recording happens once per server tick
    # regardless of agent vs SSH mode.
    live_endpoint_pairs: List[tuple] = []

    if server.agent_mode == "agent" and server.agent_url:
        # Agent mode
        if not _agent_is_up(server):
            result["issues"].append("agent_unreachable")
            result["drift_detected"] = True
            logger.warning(f"[RECONCILE] {server.name}: agent unreachable → DRIFTED")
        else:
            peers = _agent_get_peers(server)
            if peers is None:
                result["issues"].append("agent_peers_unavailable")
                result["drift_detected"] = True
            else:
                live_pubkeys = {p["public_key"] for p in peers}
                live_endpoint_pairs = [(p["public_key"], p.get("endpoint")) for p in peers if p.get("endpoint")]
                interface_up = True  # if agent responds, interface is considered up
    else:
        # SSH / local mode
        try:
            wgm = _wg_manager(server)
            interface_up = wgm.is_interface_up()
            if not interface_up:
                result["issues"].append("interface_down")
                result["drift_detected"] = True
                logger.warning(f"[RECONCILE] {server.name}: interface {server.interface} is DOWN → DRIFTED")
                if _try_recover_interface(server, wgm, now):
                    interface_up = wgm.is_interface_up()
                    if interface_up:
                        result["reconciled"].append("interface_started")
                        result["drift_detected"] = False
                        result["issues"].remove("interface_down")
                        live_peers = wgm.get_all_peers()
                        live_pubkeys = {p.public_key for p in live_peers}
                        live_endpoint_pairs = [(p.public_key, p.endpoint) for p in live_peers if p.endpoint]
                        logger.info(f"[RECONCILE] {server.name}: interface {server.interface} auto-recovered")
            else:
                live_peers = wgm.get_all_peers()
                live_pubkeys = {p.public_key for p in live_peers}
                live_endpoint_pairs = [(p.public_key, p.endpoint) for p in live_peers if p.endpoint]

                # ── Subnet sanity check (via live interface address) ──────────
                try:
                    iface_info = wgm.get_interface_info()
                    # We can't easily get the interface address from `wg show` alone,
                    # so we skip subnet check here (would require `ip addr show` parsing)
                except Exception:
                    pass
        except Exception as e:
            result["issues"].append(f"connection_error: {e}")
            result["drift_detected"] = True
            logger.warning(f"[RECONCILE] {server.name}: connection failed: {e} → DRIFTED")
        finally:
            if wgm:
                try:
                    wgm.close()
                except Exception:
                    pass
                wgm = None

    if live_pubkeys is None:
        # Can't check peers — already flagged above
        _apply_drift_result(server, result, now, db)
        return result

    # NOTE: 1.5.92 introduced an "endpoint-flap" observation log meant to
    # surface possible config-sharing. The signal turned out unreliable —
    # mobile clients on cellular networks change source IPs frequently
    # without sharing, and a single home NAT hides shared keys behind one
    # IP. Disabled in 1.5.93. Per-customer device caps (customer_email +
    # max_devices_per_customer in clients.py) replace it.

    # ── 2. Compare DB peers vs live peers ────────────────────────────────────
    db_clients_enabled: List[Client] = (
        db.query(Client)
        .filter(Client.server_id == server.id, Client.enabled == True,
                Client.public_key.isnot(None))
        .all()
    )
    db_clients_disabled: List[Client] = (
        db.query(Client)
        .filter(Client.server_id == server.id, Client.enabled == False,
                Client.public_key.isnot(None))
        .all()
    )

    db_pubkeys_enabled  = {c.public_key for c in db_clients_enabled}
    db_pubkeys_disabled = {c.public_key for c in db_clients_disabled}

    missing_from_live = db_pubkeys_enabled - live_pubkeys   # enabled in DB but absent on iface → re-add
    ghost_peers       = db_pubkeys_disabled & live_pubkeys  # disabled in DB but still on iface → SECURITY
    extra_in_live     = live_pubkeys - db_pubkeys_enabled - db_pubkeys_disabled  # manual additions → ignore

    if extra_in_live:
        logger.debug(
            f"[RECONCILE] {server.name}: {len(extra_in_live)} extra peer(s) on interface "
            f"(not in DB) — ignoring (manual additions)"
        )

    # ── 3a. SECURITY: remove ghost peers (disabled in DB but live on interface) ──
    if ghost_peers:
        logger.warning(
            f"[RECONCILE] {server.name}: {len(ghost_peers)} GHOST peer(s) — "
            f"disabled in DB but still live on interface (access leak) — removing"
        )
        disabled_map = {c.public_key: c for c in db_clients_disabled}
        for pubkey in ghost_peers:
            client = disabled_map.get(pubkey)
            client_name = client.name if client else pubkey[:12]
            removed = _remove_peer(server, pubkey)
            if removed:
                result["reconciled"].append(f"GHOST_REMOVED:{client_name}")
                logger.warning(
                    f"[RECONCILE] {server.name}: removed ghost peer {client_name} (security fix)"
                )
            else:
                result["issues"].append(f"ghost_remove_failed:{client_name}")
                result["drift_detected"] = True
                logger.error(
                    f"[RECONCILE] {server.name}: FAILED to remove ghost peer {client_name} — ACCESS LEAK"
                )

    # ── 3b. Auto-reconcile missing peers (enabled in DB but absent live) ─────
    if missing_from_live:
        logger.info(
            f"[RECONCILE] {server.name}: {len(missing_from_live)} peer(s) missing from "
            f"live interface — attempting auto-reconcile"
        )
        client_map = {c.public_key: c for c in db_clients_enabled}

        for pubkey in missing_from_live:
            client = client_map.get(pubkey)
            if client is None:
                continue
            ok = _reconcile_peer(server, client)
            if ok:
                result["reconciled"].append(f"{client.name} ({pubkey[:12]}…)")
                logger.info(f"[RECONCILE] {server.name}: re-added peer {client.name}")
            else:
                result["issues"].append(f"reconcile_failed:{client.name}")
                result["drift_detected"] = True
                logger.warning(f"[RECONCILE] {server.name}: failed to re-add peer {client.name} → DRIFTED")

    # ── 4. Update DB state ───────────────────────────────────────────────────
    _apply_drift_result(server, result, now, db)
    return result


def _remove_peer(server: Server, public_key: str) -> bool:
    """Remove a peer from the live WireGuard interface (used to clean ghost peers)."""
    if server.agent_mode == "agent" and server.agent_url:
        try:
            import httpx
            url = server.agent_url.rstrip("/")
            headers = {"X-Api-Key": server.agent_api_key or ""}
            resp = httpx.post(
                f"{url}/peer/delete",
                json={"public_key": public_key},
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"[RECONCILE] agent /peer/delete failed for {public_key[:12]}: {e}")
            return False

    try:
        wgm = _wg_manager(server)
        try:
            ok = wgm.remove_peer(public_key)
            return bool(ok)
        finally:
            wgm.close()
    except Exception as e:
        logger.error(f"[RECONCILE] _remove_peer error for {public_key[:12]}: {e}")
        return False


def _reconcile_peer(server: Server, client: Client) -> bool:
    """Re-add a single peer to the live WireGuard interface."""
    allowed_ips = [f"{client.ipv4}/32"]
    if client.ipv6:
        allowed_ips.append(f"{client.ipv6}/128")

    # Agent mode: use Agent HTTP API
    if server.agent_mode == "agent" and server.agent_url:
        try:
            import httpx
            url = server.agent_url.rstrip("/")
            headers = {"X-Api-Key": server.agent_api_key or ""}
            payload = {
                "public_key": client.public_key,
                "allowed_ips": ",".join(allowed_ips),
                "preshared_key": client.preshared_key,
            }
            resp = httpx.post(f"{url}/peer/create", json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"[RECONCILE] agent /peer/create failed for {client.name}: {e}")
            return False

    # SSH / local mode: use WireGuardManager
    try:
        wgm = _wg_manager(server)
        try:
            ok = wgm.add_peer(
                public_key=client.public_key,
                allowed_ips=allowed_ips,
                preshared_key=client.preshared_key,
                persistent_keepalive=25,
            )
            return ok
        finally:
            wgm.close()
    except Exception as e:
        logger.error(f"[RECONCILE] _reconcile_peer error for {client.name}: {e}")
        return False


def _apply_drift_result(server: Server, result: dict, now: datetime, db: Session):
    """Persist drift state to server row."""
    server.last_reconcile_at = now

    if result["drift_detected"]:
        server.drift_detected = True
        server.drift_detected_at = now
        server.drift_details = json.dumps({
            "issues": result["issues"],
            "reconciled": result["reconciled"],
            "checked_at": now.isoformat(),
        })
    else:
        # Clear drift on clean check
        server.drift_detected = False
        server.drift_details = None
        server.drift_detected_at = None


# ─── batch run ───────────────────────────────────────────────────────────────

def run_reconciliation() -> List[Dict[str, Any]]:
    """
    Run reconciliation for all ONLINE servers.
    Opens its own DB session. Commits after each server.
    Called from the monitoring loop every ~5 minutes.
    """
    db = SessionLocal()
    results = []
    try:
        servers: List[Server] = (
            db.query(Server)
            .filter(Server.lifecycle_status == "online", Server.server_category != "proxy")
            .all()
        )
        logger.info(f"[RECONCILE] Starting reconciliation for {len(servers)} server(s)")

        for server in servers:
            try:
                r = reconcile_server(server, db)
                db.commit()
                results.append(r)
                if r["drift_detected"]:
                    logger.warning(
                        f"[RECONCILE] {server.name}: DRIFTED — issues: {r['issues']}"
                    )
                elif r["reconciled"]:
                    logger.info(
                        f"[RECONCILE] {server.name}: OK (reconciled {len(r['reconciled'])} peer(s))"
                    )
                else:
                    logger.debug(f"[RECONCILE] {server.name}: OK — no drift")
            except Exception as e:
                logger.error(f"[RECONCILE] Error reconciling {server.name}: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass

        logger.info(
            f"[RECONCILE] Done. Drifted: "
            f"{sum(1 for r in results if r['drift_detected'])} / {len(results)}"
        )
    except Exception as e:
        logger.error(f"[RECONCILE] run_reconciliation error: {e}")
    finally:
        db.close()
    return results
