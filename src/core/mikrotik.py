"""MikrotikWireGuardManager — RouterOS REST API backend.

Drop-in replacement for `WireGuardManager` / `AmneziaWGManager` that talks
to a Mikrotik RouterOS box over its REST API (port 80 by default, 443 if
the operator enabled `/ip/service/set www-ssl`). RouterOS 7.1+ exposes
`/rest/<path>` with basic auth.

Same method names as `WireGuardManager` so `RemoteServerAdapter` can
substitute it without the rest of the codebase (ClientManager,
TrafficManager, server lifecycle) caring.

What's intentionally NOT covered:
  - AmneziaWG. Mikrotik has no AWG support; the dispatch in
    `RemoteServerAdapter` should keep AWG servers on the SSH path.
  - Local-mode usage. This class is *always* remote — there's no
    "Mikrotik on localhost" use case.
  - File config edits. RouterOS doesn't expose `wg-quick`-style config;
    state lives in the router's CFS. So `read_config_file` /
    `write_config_file` / `save_config` are no-ops or stubs.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from loguru import logger

from .wireguard import PeerInfo


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_routeros_duration(s: str) -> Optional[timedelta]:
    """RouterOS reports durations as compact strings like '6d20h12m11s' or
    '45s' or '3w2d' or 'never'. Returns a timedelta, or None for invalid /
    'never'.
    """
    if not s or s == "never":
        return None
    units = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1, "ms": 0.001}
    total = 0.0
    num = ""
    i = 0
    while i < len(s):
        c = s[i]
        if c.isdigit() or c == ".":
            num += c
            i += 1
            continue
        # find longest unit (ms before s)
        unit = s[i:i + 2] if s[i:i + 2] == "ms" else c
        mult = units.get(unit)
        if mult is None:
            return None
        total += float(num or "0") * mult
        num = ""
        i += len(unit)
    if num:
        return None  # trailing digits without a unit
    return timedelta(seconds=total)


def _routeros_bool(v: Any) -> bool:
    """RouterOS returns booleans as the strings 'true' / 'false'."""
    if isinstance(v, bool):
        return v
    return str(v).lower() == "true"


# ── adapter ───────────────────────────────────────────────────────────────────


class MikrotikWireGuardManager:
    """Manages a WireGuard interface on a Mikrotik RouterOS box.

    The router is the authoritative store: peer state is on the device,
    not in our config file. We just translate WireGuardManager method
    calls into REST calls.
    """

    def __init__(
        self,
        interface: str = "wg0",
        # — RouterOS connection —
        host: Optional[str] = None,
        port: int = 80,
        scheme: str = "http",
        username: str = "admin",
        password: str = "",
        # — accepted for signature compatibility but unused —
        config_path: Optional[str] = None,
        ssh_host: Optional[str] = None,
        ssh_port: int = 22,
        ssh_user: str = "root",
        ssh_password: Optional[str] = None,
        ssh_private_key: Optional[str] = None,
    ):
        if not host:
            raise ValueError("MikrotikWireGuardManager: host is required")
        self.interface = interface
        self.host = host
        self.port = port
        self.scheme = scheme
        self.username = username
        self.password = password
        self.base = f"{scheme}://{host}:{port}/rest"
        # in-process cache of the interface's RouterOS internal id (`.id`),
        # so we don't hit `/interface/wireguard/print` on every operation.
        self._iface_id: Optional[str] = None
        # http session for connection reuse
        self._session = requests.Session()
        self._session.auth = (username, password)
        self._session.headers.update({"Content-Type": "application/json"})

    # — low-level REST plumbing ——————————————————————————————————————————

    def _req(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        timeout: int = 10,
    ) -> Any:
        url = self.base + path
        try:
            r = self._session.request(method, url, json=json, timeout=timeout)
        except requests.RequestException as e:
            logger.error(f"Mikrotik {self.host}: {method} {path} transport error: {e}")
            raise
        if not r.ok:
            logger.warning(
                f"Mikrotik {self.host}: {method} {path} → HTTP {r.status_code}: "
                f"{r.text[:200]}"
            )
            r.raise_for_status()
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return r.text

    def _get(self, path: str) -> Any:
        return self._req("GET", path)

    def _put(self, path: str, body: Dict[str, Any]) -> Any:
        # RouterOS REST uses PUT to create new items (yes, unusual).
        return self._req("PUT", path, json=body)

    def _patch(self, path: str, body: Dict[str, Any]) -> Any:
        return self._req("PATCH", path, json=body)

    def _delete(self, path: str) -> Any:
        return self._req("DELETE", path)

    # — interface state ——————————————————————————————————————————————

    def _iface_record(self) -> Optional[Dict[str, Any]]:
        """Fetch the wg interface record by name. Caches `.id`."""
        rows = self._get("/interface/wireguard")
        for row in rows or []:
            if row.get("name") == self.interface:
                self._iface_id = row.get(".id")
                return row
        return None

    def is_interface_up(self) -> bool:
        rec = self._iface_record()
        if not rec:
            return False
        return _routeros_bool(rec.get("running")) and not _routeros_bool(
            rec.get("disabled")
        )

    def start_interface(self) -> bool:
        rec = self._iface_record()
        if not rec:
            logger.error(f"Mikrotik {self.host}: interface {self.interface} not found")
            return False
        if not _routeros_bool(rec.get("disabled")):
            return True
        try:
            self._patch(f"/interface/wireguard/{rec['.id']}", {"disabled": "false"})
            return True
        except Exception as e:
            logger.error(f"Mikrotik {self.host}: start_interface failed: {e}")
            return False

    def stop_interface(self) -> bool:
        # The router's wg interface was set up by its operator BEFORE the
        # panel adopted it — we manage peers on top, not the interface
        # itself. Treating panel "delete server" or "stop server" as a
        # signal to bring the interface down on the router would surprise
        # the operator (and disconnect any peers managed outside the
        # panel). No-op here; explicit disable still works via
        # `_set_disabled(True)` if the caller really wants it.
        logger.debug(
            f"Mikrotik {self.host}: stop_interface is a no-op — router "
            "interface is owned by the operator, not the panel."
        )
        return True

    def _set_disabled(self, disabled: bool) -> bool:
        rec = self._iface_record()
        if not rec:
            return True
        try:
            self._patch(
                f"/interface/wireguard/{rec['.id']}",
                {"disabled": "true" if disabled else "false"},
            )
            return True
        except Exception as e:
            logger.error(f"Mikrotik {self.host}: _set_disabled({disabled}) failed: {e}")
            return False

    def restart_interface(self) -> bool:
        # Same rationale as stop_interface: don't touch the operator's
        # interface state. If they need a restart, they trigger it from
        # the router. Returning True so retrying-startup code paths don't
        # treat this as a recoverable error.
        return True

    def save_config(self) -> bool:
        # RouterOS auto-persists every API change to its CFS.
        return True

    # — server pubkey ————————————————————————————————————————————————

    def get_server_public_key(self) -> Optional[str]:
        rec = self._iface_record()
        return rec.get("public-key") if rec else None

    # — peer CRUD ————————————————————————————————————————————————————

    def add_peer(
        self,
        public_key: str,
        allowed_ips: List[str],
        preshared_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        persistent_keepalive: Optional[int] = None,
    ) -> bool:
        body: Dict[str, Any] = {
            "interface": self.interface,
            "public-key": public_key,
            "allowed-address": ",".join(allowed_ips),
        }
        if preshared_key:
            body["preshared-key"] = preshared_key
        if endpoint:
            host, _, eport = endpoint.rpartition(":")
            if host and eport:
                body["endpoint-address"] = host
                body["endpoint-port"] = eport
        if persistent_keepalive:
            body["persistent-keepalive"] = f"{int(persistent_keepalive)}s"
        try:
            self._put("/interface/wireguard/peers", body)
            return True
        except Exception as e:
            logger.error(
                f"Mikrotik {self.host}: add_peer({public_key[:12]}…) failed: {e}"
            )
            return False

    def _peer_record(self, public_key: str) -> Optional[Dict[str, Any]]:
        rows = self._get("/interface/wireguard/peers") or []
        for row in rows:
            if row.get("public-key") == public_key and row.get("interface") == self.interface:
                return row
        return None

    def remove_peer(self, public_key: str) -> bool:
        peer = self._peer_record(public_key)
        if not peer:
            return True  # already gone
        try:
            self._delete(f"/interface/wireguard/peers/{peer['.id']}")
            return True
        except Exception as e:
            logger.error(
                f"Mikrotik {self.host}: remove_peer({public_key[:12]}…) failed: {e}"
            )
            return False

    def update_peer_allowed_ips(self, public_key: str, allowed_ips: List[str]) -> bool:
        peer = self._peer_record(public_key)
        if not peer:
            return False
        try:
            self._patch(
                f"/interface/wireguard/peers/{peer['.id']}",
                {"allowed-address": ",".join(allowed_ips)},
            )
            return True
        except Exception as e:
            logger.error(f"Mikrotik {self.host}: update_peer_allowed_ips failed: {e}")
            return False

    # — peer stats ———————————————————————————————————————————————————

    def get_all_peers(self) -> List[PeerInfo]:
        rows = self._get("/interface/wireguard/peers") or []
        out: List[PeerInfo] = []
        now = datetime.now(timezone.utc)
        for row in rows:
            if row.get("interface") != self.interface:
                continue
            handshake = _parse_routeros_duration(row.get("last-handshake", ""))
            allowed = row.get("allowed-address", "") or ""
            allowed_list = [a.strip() for a in allowed.split(",") if a.strip()]
            endpoint = None
            if row.get("current-endpoint-address"):
                endpoint = (
                    f"{row['current-endpoint-address']}:{row.get('current-endpoint-port', '')}"
                ).rstrip(":")
            ka = row.get("persistent-keepalive")
            ka_secs = None
            if ka:
                td = _parse_routeros_duration(str(ka))
                ka_secs = int(td.total_seconds()) if td else None
            out.append(
                PeerInfo(
                    public_key=row.get("public-key", ""),
                    preshared_key=bool(row.get("preshared-key")),
                    endpoint=endpoint,
                    allowed_ips=allowed_list,
                    latest_handshake=(now - handshake) if handshake else None,
                    transfer_rx=int(row.get("rx", 0) or 0),
                    transfer_tx=int(row.get("tx", 0) or 0),
                    persistent_keepalive=ka_secs,
                )
            )
        return out

    def get_peer_transfer(self, public_key: str) -> Tuple[int, int]:
        peer = self._peer_record(public_key)
        if not peer:
            return (0, 0)
        return (int(peer.get("rx", 0) or 0), int(peer.get("tx", 0) or 0))

    def get_peer_latest_handshake(self, public_key: str) -> Optional[datetime]:
        peer = self._peer_record(public_key)
        if not peer:
            return None
        td = _parse_routeros_duration(peer.get("last-handshake", ""))
        return (datetime.now(timezone.utc) - td) if td else None

    def get_peer_endpoints(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for p in self.get_all_peers():
            if p.endpoint:
                out[p.public_key] = p.endpoint
        return out

    def get_interface_info(self) -> Optional[Dict[str, Any]]:
        rec = self._iface_record()
        if not rec:
            return None
        return {
            "interface": rec.get("name"),
            "public_key": rec.get("public-key"),
            "listen_port": int(rec.get("listen-port", 0) or 0),
            "mtu": int(rec.get("mtu", 1420) or 1420),
            "disabled": _routeros_bool(rec.get("disabled")),
            "running": _routeros_bool(rec.get("running")),
        }

    # — keys ——————————————————————————————————————————————————————————

    @staticmethod
    def generate_private_key() -> str:
        # WireGuard key generation is the same on either side; reuse the
        # plain `wg genkey` impl from WireGuardManager so we don't fork the
        # crypto path.
        from .wireguard import WireGuardManager
        return WireGuardManager.generate_private_key()

    @staticmethod
    def generate_public_key(private_key: str) -> str:
        from .wireguard import WireGuardManager
        return WireGuardManager.generate_public_key(private_key)

    @staticmethod
    def generate_keypair() -> Tuple[str, str]:
        from .wireguard import WireGuardManager
        return WireGuardManager.generate_keypair()

    @staticmethod
    def generate_preshared_key() -> str:
        from .wireguard import WireGuardManager
        return WireGuardManager.generate_preshared_key()

    # — config file stubs (RouterOS has no /etc/wireguard/*.conf) ————————

    @property
    def is_remote(self) -> bool:
        return True

    def read_config_file(self) -> Optional[str]:
        # Synthesize a wg-quick-style view from current state so callers
        # that want to inspect "the config" get something readable.
        rec = self._iface_record()
        if not rec:
            return None
        addr_rows = self._get("/ip/address") or []
        iface_addrs = [
            a.get("address") for a in addr_rows if a.get("interface") == self.interface
        ]
        lines = [
            "[Interface]",
            f"# Synthesized view of RouterOS device {self.host}",
            f"# This is read-only — RouterOS state is authoritative.",
            f"Address = {', '.join(iface_addrs)}" if iface_addrs else "",
            f"ListenPort = {rec.get('listen-port', '')}",
            f"PrivateKey = {rec.get('private-key', '')}",
        ]
        for peer in self.get_all_peers():
            lines.append("")
            lines.append("[Peer]")
            lines.append(f"PublicKey = {peer.public_key}")
            if peer.preshared_key:
                lines.append("PresharedKey = <hidden>")
            if peer.allowed_ips:
                lines.append(f"AllowedIPs = {', '.join(peer.allowed_ips)}")
            if peer.persistent_keepalive:
                lines.append(f"PersistentKeepalive = {peer.persistent_keepalive}")
        return "\n".join([line for line in lines if line is not None])

    def write_config_file(self, content: str) -> bool:
        logger.warning(
            f"Mikrotik {self.host}: write_config_file is a no-op — "
            "RouterOS state is API-managed, not file-managed."
        )
        return True

    def backup_config(self, backup_path: Optional[str] = None) -> Optional[str]:
        # RouterOS has its own /system/backup mechanism, separate concern.
        return None

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass
