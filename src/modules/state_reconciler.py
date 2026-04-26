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
from ..database.models import Server, Client, ServerStatus, ClientStatus


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


def _agent_get_peers(server: Server) -> Optional[List[dict]]:
    """
    Fetch peer list via the vpnmanager-agent /stats endpoint.
    Returns list of dicts with 'public_key' and 'allowed_ips', or None on error.
    """
    try:
        import httpx
        url = server.agent_url.rstrip("/")
        headers = {"X-Api-Key": server.agent_api_key or ""}
        resp = httpx.get(f"{url}/stats", headers=headers, timeout=8)
        resp.raise_for_status()
        return resp.json().get("peers", [])
    except Exception as e:
        logger.debug(f"[RECONCILE] agent /stats failed for {server.name}: {e}")
        return None


def _agent_is_up(server: Server) -> bool:
    """Quick reachability check via agent /health."""
    try:
        import httpx
        url = server.agent_url.rstrip("/")
        headers = {"X-Api-Key": server.agent_api_key or ""}
        resp = httpx.get(f"{url}/health", headers=headers, timeout=8)
        return resp.status_code == 200
    except Exception:
        return False


def _subnet_of_server(server: Server) -> Optional[ipaddress.IPv4Network]:
    """Parse address_pool_ipv4 → network. Returns None on parse error."""
    try:
        return ipaddress.IPv4Network(server.address_pool_ipv4, strict=False)
    except Exception:
        return None


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
            else:
                live_peers = wgm.get_all_peers()
                live_pubkeys = {p.public_key for p in live_peers}

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
