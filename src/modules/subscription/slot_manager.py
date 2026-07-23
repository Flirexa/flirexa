"""Device-slot manager.

A "device slot" is one customer device whose peer record is replicated on
every customer-visible server. The slot owns one shared keypair; exactly
one of the per-server Client rows has ``enabled=True`` at a time. The
portal-side toggle moves that flag between servers without rotating keys
or re-issuing configs.

What this module guarantees:
  • create_slot → atomic: creates the slot row, generates one keypair, and
    inserts a peer-Client row on every customer-visible WG/AWG server. The
    initial active server gets enabled=True; the rest enabled=False.
  • switch_active_server → atomic: flips enabled flags on the right peer
    rows AND pushes the change to the underlying WG/AWG interfaces via
    the agent so handshakes start/stop within a couple seconds.
  • delete_slot → cascades: removes every peer-Client owned by the slot.

It deliberately reuses ``ClientManager.delete_client`` / ``enable_client``
/ ``disable_client`` for the per-server operations so live ``wg set`` /
``awg set`` propagation and audit logging happen the same way as for
admin-side single-server peers.

Rate-limit: ``SLOT_SWITCH_COOLDOWN_SECONDS`` (default 30s) between toggles
to prevent a misbehaving client from hammering every node agent on the
network.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.database.models import Client, Server
from src.modules.subscription.subscription_models import (
    ClientUser,
    ClientUserClients,
    DeviceSlot,
)
from src.core.management import ManagementCore
from src.core.wireguard import WireGuardManager
from src.core.amneziawg import AmneziaWGManager

logger = logging.getLogger(__name__)


SLOT_SWITCH_COOLDOWN_SECONDS = int(os.getenv("SLOT_SWITCH_COOLDOWN_SECONDS", "30"))
# Token-bucket parameters for region switching. The fixed cooldown above
# blocks dual-tap and rapid testing equally — token bucket allows a small
# burst before throttling. Cooldown var kept for backwards compat in code
# paths that haven't been migrated, but switch_active_server uses bucket.
SLOT_SWITCH_BUCKET_SIZE = float(os.getenv("SLOT_SWITCH_BUCKET_SIZE", "5"))
SLOT_SWITCH_REFILL_SECONDS_PER_TOKEN = float(os.getenv(
    "SLOT_SWITCH_REFILL_SECONDS_PER_TOKEN", "6",
))


def _slot_peer_name(
    slot: "DeviceSlot",
    server: "Server",
    username: Optional[str] = None,
) -> str:
    """Build the per-server peer name shown to admins in the Clients list.

    Format: ``{username}-{hash}``. The server name used to be appended
    here, but every admin-side Clients table already has a separate
    `Server` column so the suffix was just duplicate noise — operators
    were complaining that names like ``Phone-b00c-USA-California`` were
    longer than they needed to be (operator report 2026-05-27). Dropping the
    server part also frees up room in the column for long usernames.

    Why the 4-char hash stays: ``Client.name`` is unique per server,
    and one user can hold multiple device slots — two slots from the
    same customer on the same region would collide on just the
    username. The hash is derived from the slot's keypair so it's
    stable across the slot's lifetime.

    When ``username`` isn't supplied (legacy callers) we fall back to
    the slot's customer-chosen label so we still produce something
    meaningful; new code paths in this file resolve the username from
    the db and pass it in.

    Output is sanitised to ``[A-Za-z0-9._-]`` and capped at 100 chars to
    fit the ``clients.name`` column.
    """
    import re
    import hashlib

    base = (username or getattr(slot, "label", None) or "Device").strip()
    base_clean = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-") or "Device"

    # 4-char suffix derived from the slot's shared public key. Stable per
    # slot, unpredictable enough to disambiguate two same-username slots
    # on the same server.
    pubkey = (getattr(slot, "public_key", None) or "").encode("utf-8")
    if pubkey:
        suffix = hashlib.sha256(pubkey).hexdigest()[:4]
    else:
        suffix = format(getattr(slot, "id", 0) or 0, "x")[-4:].rjust(4, "0")

    raw = f"{base_clean}-{suffix}"
    return raw[:100]


class SlotManagerError(Exception):
    """Surface-level error from slot ops with a customer-facing message."""

    def __init__(self, code: str, message: str, http_status: int = 400):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def _customer_visible_servers(db: Session) -> List[Server]:
    """Order matters: ``is_default`` server first, then by id for stable
    UI rendering. Proxy servers excluded — they don't have an IP pool
    and aren't a meaningful "region" to switch to."""
    rows = (
        db.query(Server)
        .filter(
            Server.is_active.is_(True),
            Server.customer_visible.is_(True),
        )
        .order_by(Server.is_default.desc(), Server.id.asc())
        .all()
    )
    return [
        s for s in rows
        if (getattr(s, "server_category", "vpn") or "vpn") == "vpn"
        and (getattr(s, "server_type", "wireguard") or "wireguard")
        in ("wireguard", "amneziawg")
    ]


def _generate_keypair_for(servers: List[Server]) -> Tuple[str, str, str]:
    """Pick a WG / AWG keygen — they produce identical X25519 keypairs but
    we stick with whichever tool corresponds to the first server's type
    so the codepath isn't surprising on AWG-only boxes."""
    for s in servers:
        st = (getattr(s, "server_type", "wireguard") or "wireguard").lower()
        if st == "amneziawg":
            mgr = AmneziaWGManager
            break
    else:
        mgr = WireGuardManager
    priv, pub = mgr.generate_keypair()
    psk = mgr.generate_preshared_key()
    return priv, pub, psk


def _agent_apply(core: ManagementCore, client: Client, action: str) -> bool:
    """Push the enable/disable to the node so handshakes flip immediately,
    not on the next config-sync tick.

    Returns True iff the wg set was actually applied. ``enable_client`` /
    ``disable_client`` already return a bool (False when the node/agent was
    unreachable — disable removes the peer FIRST then flips the DB flag, so a
    False disable means the old peer is STILL LIVE and the DB flag was rolled
    back). We surface that so the caller can decide whether a failed DISABLE is
    safe to ignore (dead node — its leftover peer serves nothing) or must block
    the switch (live node — leaving the peer enabled would leak access to the
    region the customer just switched off).
    """
    try:
        if action == "enable":
            return bool(core.enable_client(client.id))
        if action == "disable":
            return bool(core.disable_client(client.id, reason="device-slot region switch"))
        return False
    except Exception as exc:
        logger.warning(
            "slot agent push failed (client_id=%s, action=%s): %s",
            client.id, action, exc,
        )
        return False


class SlotManager:
    def __init__(self, db: Session):
        self.db = db
        self.core = ManagementCore(db)

    # ─────────────────────────────────────────────────────────────────
    # Read paths
    # ─────────────────────────────────────────────────────────────────

    def get_user_slots(self, user_id: int) -> List[DeviceSlot]:
        return (
            self.db.query(DeviceSlot)
            .filter(DeviceSlot.client_user_id == user_id)
            .order_by(DeviceSlot.id.asc())
            .all()
        )

    def get_slot(self, slot_id: int, user_id: int) -> Optional[DeviceSlot]:
        return (
            self.db.query(DeviceSlot)
            .filter(
                DeviceSlot.id == slot_id,
                DeviceSlot.client_user_id == user_id,
            )
            .first()
        )

    def get_slot_peers(self, slot_id: int) -> List[Client]:
        """All Client rows belonging to this slot, joined via the
        link table. One per server in the slot."""
        rows = (
            self.db.query(Client)
            .join(ClientUserClients, ClientUserClients.client_id == Client.id)
            .filter(ClientUserClients.slot_id == slot_id)
            .all()
        )
        return rows

    # ─────────────────────────────────────────────────────────────────
    # Mutations
    # ─────────────────────────────────────────────────────────────────

    def create_slot(
        self,
        user: ClientUser,
        label: str,
        initial_server_id: Optional[int] = None,
        bandwidth_limit_mbps: Optional[int] = None,
        traffic_limit_mb: Optional[int] = None,
        expiry_days: Optional[int] = None,
    ) -> DeviceSlot:
        """Spin up a slot + one peer on every customer-visible server.

        The initial active server is either ``initial_server_id`` (if
        supplied and visible) or the default server, falling back to the
        first visible row.

        Implementation does NOT route through ``ClientManager.create_client``
        because that helper auto-generates a per-row keypair, and we
        specifically need the same keypair on every server in the slot.
        Instead we allocate the IP + insert the Client row + push the
        peer to the node directly, mirroring what ``create_client`` does
        but with our shared key.
        """
        import ipaddress as _ipaddress

        servers = _customer_visible_servers(self.db)
        if not servers:
            raise SlotManagerError(
                "no_servers_available",
                "No servers are available for new devices. Contact support.",
                http_status=503,
            )

        # Pick initial active server
        active = None
        if initial_server_id is not None:
            active = next((s for s in servers if s.id == initial_server_id), None)
            if not active:
                raise SlotManagerError(
                    "invalid_server",
                    "Requested server is not available.",
                    http_status=400,
                )
        if active is None:
            active = next((s for s in servers if s.is_default), servers[0])

        private_key, public_key, psk = _generate_keypair_for(servers)

        slot = DeviceSlot(
            client_user_id=user.id,
            label=label.strip()[:64] or "Device",
            public_key=public_key,
            private_key=private_key,
            preshared_key=psk,
            active_server_id=active.id,
        )
        self.db.add(slot)
        self.db.flush()  # need slot.id for the per-server Client.name + link rows

        # Track (server, public_key) tuples we've pushed to nodes so we can
        # roll the live state back if we abort halfway. The DB rolls back
        # via session.rollback(); the node side needs explicit cleanup.
        pushed: List[Tuple[Server, str]] = []

        try:
            for server in servers:
                # 1. Allocate next free IP host-offset on this server.
                ip_index = self.core.clients._get_next_available_ip(
                    server.id, server.address_pool_ipv4
                )
                if ip_index is None:
                    raise SlotManagerError(
                        "no_ip_available",
                        f"Server {server.name} has no free IP addresses.",
                        http_status=503,
                    )

                # 2. Compute ipv4 / ipv6 from CIDR — works for any prefix.
                # Storage convention: bare address, no /32 or /128 suffix.
                # The legacy clients in the DB look like "10.66.66.5" or
                # "172.27.0.5". Existing callsites add the suffix when
                # they actually need CIDR form, so writing it here would
                # double up to "X/32/32" and break the client config.
                net4 = _ipaddress.IPv4Network(server.address_pool_ipv4, strict=False)
                ipv4 = str(net4.network_address + ip_index)

                ipv6 = None
                if server.address_pool_ipv6:
                    try:
                        net6 = _ipaddress.IPv6Network(server.address_pool_ipv6, strict=False)
                        ipv6 = str(net6.network_address + ip_index)
                    except Exception:
                        ipv6 = None

                expiry_date = None
                if expiry_days and expiry_days > 0:
                    expiry_date = datetime.now(timezone.utc) + timedelta(days=expiry_days)

                # 3. Create the Client row with the SHARED keypair.
                peer_name = _slot_peer_name(slot, server, user.username)
                is_active_peer = (server.id == active.id)
                client = Client(
                    name=peer_name,
                    server_id=server.id,
                    public_key=public_key,
                    private_key=private_key,
                    preshared_key=psk,
                    ip_index=ip_index,
                    ipv4=ipv4,
                    ipv6=ipv6,
                    bandwidth_limit=bandwidth_limit_mbps,
                    traffic_limit_mb=traffic_limit_mb,
                    expiry_date=expiry_date,
                    enabled=is_active_peer,
                )
                self.db.add(client)
                self.db.flush()  # need client.id for link row

                # 4. Push to the node ONLY for the active peer. The others
                # exist in DB but aren't installed on the interface — they
                # become live when the user switches regions to them.
                # This avoids unnecessary `wg set` churn on cold peers.
                if is_active_peer:
                    try:
                        wg = self.core.clients._get_wg(server)
                        try:
                            # WireGuard `wg set peer … allowed-ips X/32` needs
                            # CIDR form; storage holds the bare address.
                            allowed_ips = [f"{ipv4}/32"]
                            if ipv6:
                                allowed_ips.append(f"{ipv6}/128")
                            ok = wg.add_peer(
                                public_key=public_key,
                                allowed_ips=allowed_ips,
                                preshared_key=psk,
                            )
                            if ok is False:
                                raise SlotManagerError(
                                    "peer_push_failed",
                                    f"Failed to install peer on {server.name}.",
                                    http_status=500,
                                )
                            pushed.append((server, public_key))
                        finally:
                            try: wg.close()
                            except Exception: pass
                    except SlotManagerError:
                        raise
                    except Exception as exc:
                        raise SlotManagerError(
                            "peer_push_failed",
                            f"Node {server.name} agent error: {exc}",
                            http_status=500,
                        )

                # 5. Link Client to user via slot.
                link = ClientUserClients(
                    client_user_id=user.id,
                    client_id=client.id,
                    slot_id=slot.id,
                )
                self.db.add(link)

            self.db.commit()
            self.db.refresh(slot)
            return slot

        except Exception:
            # Roll back DB, remove live peer from any node we already
            # pushed to. Best-effort on the node side.
            self.db.rollback()
            for server, pk in pushed:
                try:
                    wg = self.core.clients._get_wg(server)
                    try:
                        wg.remove_peer(pk)
                    finally:
                        try: wg.close()
                        except Exception: pass
                except Exception as exc:
                    logger.warning(
                        "slot create rollback: failed to remove peer from %s: %s",
                        server.name, exc,
                    )
            raise

    def switch_active_server(
        self,
        slot: DeviceSlot,
        target_server_id: int,
    ) -> DeviceSlot:
        """Flip the slot's active server. Rate-limited."""
        if target_server_id == slot.active_server_id:
            return slot  # no-op

        # Token-bucket rate limit. The slot row carries ``switch_tokens``
        # (current available, float so partial refills are tracked) and
        # ``last_switched_at`` (the refill anchor — time of the previous
        # consumption / refill calc). On each switch:
        #   1. Refill: tokens += (now - last) / refill_seconds, capped.
        #   2. Decrement: tokens -= 1. If <0, reject with 429.
        # The DB write at the end of this function commits the new
        # `switch_tokens` and `last_switched_at`, so the next call sees a
        # consistent view.
        now = datetime.now(timezone.utc)
        bucket_size = SLOT_SWITCH_BUCKET_SIZE
        refill_seconds = max(1.0, SLOT_SWITCH_REFILL_SECONDS_PER_TOKEN)

        # Read stored tokens, default to a full bucket for legacy rows
        # that pre-date the 1.9.12 migration.
        stored = float(getattr(slot, "switch_tokens", None) or bucket_size)
        if slot.last_switched_at is not None:
            last = slot.last_switched_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = max(0.0, (now - last).total_seconds())
            stored = min(bucket_size, stored + elapsed / refill_seconds)
        else:
            stored = bucket_size

        if stored < 1.0:
            # Compute exact seconds until one whole token is available
            # again. Round UP so the customer's "wait Ns" hint never
            # tells them it's ready a fraction of a second early.
            wait = int((1.0 - stored) * refill_seconds) + 1
            raise SlotManagerError(
                "cooldown",
                f"Please wait {wait}s before switching servers again.",
                http_status=429,
            )

        # NB: the token is consumed at the very end, only when the switch
        # actually proceeds. A switch we refuse below (503 — couldn't release
        # the old region on a live node) must NOT cost the customer a token,
        # so they can retry immediately without hitting the cooldown.

        # Validate target is one of this slot's peers
        peers = self.get_slot_peers(slot.id)
        target_peer = next((p for p in peers if p.server_id == target_server_id), None)
        if not target_peer:
            raise SlotManagerError(
                "invalid_target_server",
                "That server isn't available for this device.",
                http_status=400,
            )

        # Validate target server is still customer-visible (admin might
        # have hidden it between page-load and click)
        target_server = self.db.query(Server).filter(Server.id == target_server_id).first()
        if not target_server or not getattr(target_server, "customer_visible", True):
            raise SlotManagerError(
                "server_unavailable",
                "That server is no longer available.",
                http_status=400,
            )

        # Apply: disable old, enable new. Order matters — disable first to
        # avoid a brief window where two peers with the same key are live
        # on different interfaces.
        #
        # IMPORTANT: don't pre-flip ``enabled`` here. ``ClientManager.
        # disable_client`` early-returns if it reads ``enabled=False``
        # from the session (short-circuit), skipping the actual
        # ``wg remove_peer`` call. The peer then stays live on the node
        # interface even though the DB reports DISABLED, and handshakes
        # continue to succeed against a region the customer thought they
        # had toggled off. Let enable/disable do both the DB flip and
        # the wg-set call themselves.
        old_peer = next((p for p in peers if p.server_id == slot.active_server_id), None)
        if old_peer and old_peer.enabled:
            disabled_ok = _agent_apply(self.core, old_peer, "disable")
            if not disabled_ok:
                # The old peer is still live on its node. Only a leak if that
                # node is actually up — a peer left enabled on a healthy node
                # keeps serving the region the customer just switched OFF.
                # If the old node is down/unreachable, its leftover peer serves
                # nothing, and blocking would trap the customer on a dead region
                # (they could never switch away), so we proceed in that case.
                old_server = (
                    self.db.query(Server)
                    .filter(Server.id == slot.active_server_id)
                    .first()
                )
                old_node_live = (
                    old_server is not None
                    and getattr(old_server, "effective_lifecycle_status", None) == "online"
                )
                if old_node_live:
                    # Nothing committed yet (token not consumed, pointer not
                    # flipped) → refuse cleanly so the client can retry; the
                    # reconciler is the backstop that eventually prunes the peer.
                    raise SlotManagerError(
                        "switch_release_failed",
                        "Couldn't release your current region just now — please try again in a moment.",
                        http_status=503,
                    )
                logger.warning(
                    "slot %s: old peer %s left enabled (node %s not online) — "
                    "proceeding with switch; reconcile will prune it",
                    slot.id, old_peer.id, slot.active_server_id,
                )

        if not target_peer.enabled:
            _agent_apply(self.core, target_peer, "enable")

        # Consume one token now that the switch is actually going through.
        slot.switch_tokens = stored - 1.0
        slot.active_server_id = target_server_id
        slot.last_switched_at = now
        self.db.add(slot)
        self.db.commit()
        self.db.refresh(slot)
        return slot

    # ─────────────────────────────────────────────────────────────────
    # Auto-sync — when the user flipped tunnels in their VPN app but
    # forgot to switch on the portal, follow the handshake instead of
    # trusting the stale DB flag.
    # ─────────────────────────────────────────────────────────────────

    def auto_sync_active_from_handshake(
        self,
        slot: DeviceSlot,
        handshake_window_seconds: int = 180,
        cooldown_seconds: int = 30,
        peers: Optional[List[Client]] = None,
    ) -> bool:
        """If the freshest handshake among the slot's peers is on a
        non-active region, flip the slot's active server to that region.

        Returns True if a flip happened.

        - ``handshake_window_seconds``: how recent the handshake must be
          to count as "the user is on this region right now". 3 min by
          default — survives a brief lapse without disqualifying a peer.
        - ``cooldown_seconds``: don't auto-flip if the user just did an
          explicit switch — give the explicit click priority. Lower than
          the manual-switch cooldown because this is a soft correction.

        Skips the cooldown rate-limit that ``switch_active_server``
        applies, because this is automation following a real handshake
        rather than a user mashing buttons.
        """
        if not slot.active_server_id:
            return False

        now = datetime.now(timezone.utc)
        if slot.last_switched_at is not None:
            last = slot.last_switched_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if (now - last).total_seconds() < cooldown_seconds:
                return False

        if peers is None:
            peers = self.get_slot_peers(slot.id)
        if len(peers) < 2:
            return False

        freshest = None
        for p in peers:
            hs = getattr(p, "last_handshake", None)
            if not hs:
                continue
            hs_aware = hs if hs.tzinfo else hs.replace(tzinfo=timezone.utc)
            if (now - hs_aware).total_seconds() > handshake_window_seconds:
                continue
            if freshest is None or hs_aware > freshest[1]:
                freshest = (p, hs_aware)

        if not freshest:
            return False
        winning_peer = freshest[0]
        if winning_peer.server_id == slot.active_server_id:
            return False

        target_server = self.db.query(Server).filter(
            Server.id == winning_peer.server_id
        ).first()
        if not target_server or not getattr(target_server, "customer_visible", True):
            return False

        old_peer = next(
            (p for p in peers if p.server_id == slot.active_server_id), None
        )
        try:
            if old_peer and old_peer.enabled:
                _agent_apply(self.core, old_peer, "disable")
            if not winning_peer.enabled:
                _agent_apply(self.core, winning_peer, "enable")
        except Exception:
            return False

        slot.active_server_id = winning_peer.server_id
        slot.last_switched_at = now
        self.db.add(slot)
        self.db.commit()
        self.db.refresh(slot)
        return True

    # ─────────────────────────────────────────────────────────────────
    # Backfill / heal — top up missing peers when a new server gets added
    # ─────────────────────────────────────────────────────────────────

    def provision_slot_on_server(
        self,
        slot: DeviceSlot,
        server: Server,
    ) -> Optional[Client]:
        """Ensure ``slot`` has a peer Client row on ``server``. Idempotent.

        Returns the new Client if one was created, ``None`` if the slot
        already has a peer there (so callers can decide whether to log /
        emit an event). Uses the slot's shared keypair so the existing
        downloaded configs on the user's phone don't need to rotate.

        The peer is NOT pushed to the node by default — it sits dormant
        (``enabled=False``) until the customer toggles to this region.
        Only exception: if the slot's ``active_server_id`` is the
        just-added server (vanishingly rare race), we push it live.
        """
        import ipaddress as _ipaddress

        # 1. Idempotency check — already provisioned?
        existing = (
            self.db.query(Client)
            .join(ClientUserClients, ClientUserClients.client_id == Client.id)
            .filter(
                ClientUserClients.slot_id == slot.id,
                Client.server_id == server.id,
            )
            .first()
        )
        if existing:
            return None

        # 2. Sanity — server must be VPN-capable. Proxy servers (hysteria2 /
        # tuic) don't belong in the slot system.
        server_type = (getattr(server, "server_type", "wireguard") or "wireguard").lower()
        server_category = getattr(server, "server_category", "vpn") or "vpn"
        if server_category == "proxy" or server_type in ("hysteria2", "tuic"):
            return None

        # 3. Allocate next-free IP from the server's pool.
        ip_index = self.core.clients._get_next_available_ip(
            server.id, server.address_pool_ipv4
        )
        if ip_index is None:
            logger.warning(
                "slot %d backfill on %s: pool exhausted, skipping peer creation",
                slot.id, server.name,
            )
            return None

        net4 = _ipaddress.IPv4Network(server.address_pool_ipv4, strict=False)
        ipv4 = str(net4.network_address + ip_index)

        ipv6 = None
        if server.address_pool_ipv6:
            try:
                net6 = _ipaddress.IPv6Network(server.address_pool_ipv6, strict=False)
                ipv6 = str(net6.network_address + ip_index)
            except Exception:
                ipv6 = None

        # 4. Carry over the original slot's per-client quota (so a slot
        # created on the "premium" plan keeps premium bandwidth/traffic
        # caps when a region is added later). Pull from any existing peer
        # in the slot — they all share the subscription's caps at creation
        # time. If the slot has no peers yet (slot was created when zero
        # servers were visible), fall back to "no caps" and trust that
        # the subscription's enforcement layer will catch overuse.
        peers = self.get_slot_peers(slot.id)
        bandwidth_limit = peers[0].bandwidth_limit if peers else None
        traffic_limit_mb = peers[0].traffic_limit_mb if peers else None
        expiry_date = peers[0].expiry_date if peers else None

        # 5. Create Client row with the slot's shared keypair.
        is_active_peer = (server.id == slot.active_server_id)
        # Pre-resolve the slot's owner so the peer name carries the
        # customer's username — matches what create_slot does and
        # keeps admin-side naming consistent across both code paths.
        owner = self.db.query(ClientUser).filter(
            ClientUser.id == slot.client_user_id
        ).first()
        peer_name = _slot_peer_name(slot, server, owner.username if owner else None)
        client = Client(
            name=peer_name,
            server_id=server.id,
            public_key=slot.public_key,
            private_key=slot.private_key,
            preshared_key=slot.preshared_key,
            ip_index=ip_index,
            ipv4=ipv4,
            ipv6=ipv6,
            bandwidth_limit=bandwidth_limit,
            traffic_limit_mb=traffic_limit_mb,
            expiry_date=expiry_date,
            enabled=is_active_peer,
        )
        self.db.add(client)
        self.db.flush()  # need client.id for the link row

        link = ClientUserClients(
            client_user_id=slot.client_user_id,
            client_id=client.id,
            slot_id=slot.id,
        )
        self.db.add(link)
        self.db.commit()
        self.db.refresh(client)

        # 6. Push to the node ONLY if this is somehow the active slot
        # peer right now. In the common backfill flow the slot is already
        # pinned to a different region, so the new peer sits dormant.
        if is_active_peer:
            try:
                wg = self.core.clients._get_wg(server)
                try:
                    allowed_ips = [f"{ipv4}/32"]
                    if ipv6:
                        allowed_ips.append(f"{ipv6}/128")
                    wg.add_peer(
                        public_key=slot.public_key,
                        allowed_ips=allowed_ips,
                        preshared_key=slot.preshared_key,
                    )
                finally:
                    try: wg.close()
                    except Exception: pass
            except Exception as exc:
                logger.warning(
                    "slot %d backfill on %s: node push failed, peer remains in DB: %s",
                    slot.id, server.name, exc,
                )

        logger.info(
            "slot %d backfilled on server %s (peer client_id=%d, active=%s)",
            slot.id, server.name, client.id, is_active_peer,
        )
        return client

    def heal_slot(self, slot: DeviceSlot) -> List[Client]:
        """Top up the slot with peers on every customer-visible VPN server
        it doesn't have yet. Idempotent. Returns the list of newly-created
        Client rows (empty if the slot was already complete).

        Cheap when there's nothing to do: one query for the slot's existing
        ``server_id`` set, one query for visible servers, diff in Python.
        """
        servers = _customer_visible_servers(self.db)
        if not servers:
            return []
        have_server_ids = {
            row.server_id for row in (
                self.db.query(Client.server_id)
                .join(ClientUserClients, ClientUserClients.client_id == Client.id)
                .filter(ClientUserClients.slot_id == slot.id)
                .all()
            )
        }
        created: List[Client] = []
        for server in servers:
            if server.id in have_server_ids:
                continue
            try:
                new_client = self.provision_slot_on_server(slot, server)
                if new_client:
                    created.append(new_client)
            except Exception as exc:
                # Don't let one bad server (pool full, network blip, etc.)
                # block the rest of the heal pass.
                logger.warning(
                    "heal_slot %d on %s failed, continuing: %s",
                    slot.id, server.name, exc,
                )
        return created

    def backfill_all_slots_on_server(self, server: Server) -> int:
        """Called when a new customer-visible server is added (or one
        flips from hidden → visible). Walks every existing slot and
        provisions a peer on this server for each. Returns the number
        of slots that got a new peer (others were already provisioned
        or skipped due to errors)."""
        if not getattr(server, "customer_visible", True):
            return 0
        if not getattr(server, "is_active", True):
            return 0
        slots = self.db.query(DeviceSlot).all()
        count = 0
        for slot in slots:
            try:
                if self.provision_slot_on_server(slot, server) is not None:
                    count += 1
            except Exception as exc:
                logger.warning(
                    "backfill slot %d on new server %s failed: %s",
                    slot.id, server.name, exc,
                )
        if count:
            logger.info(
                "Backfill: server %s added to %d existing slot(s)",
                server.name, count,
            )
        return count

    def delete_slot(self, slot: DeviceSlot) -> None:
        """Tear down every peer + link, then the slot itself."""
        peers = self.get_slot_peers(slot.id)
        for p in peers:
            try:
                self.core.delete_client(p.id)
            except Exception as exc:
                logger.warning("slot delete: failed to remove peer %s: %s", p.id, exc)
        # delete_client cascades the link rows via ondelete=CASCADE on
        # client_user_clients.client_id, but be explicit for safety:
        (
            self.db.query(ClientUserClients)
            .filter(ClientUserClients.slot_id == slot.id)
            .delete(synchronize_session=False)
        )
        self.db.delete(slot)
        self.db.commit()

    def rotate_slot_keys(self, slot: DeviceSlot) -> DeviceSlot:
        """Rotate the slot's WG/AWG keypair so any device still holding the
        OLD config is cryptographically locked out on its next handshake.

        Used on release / stale-rebind to actually displace the previously
        bound device — clearing ``device_id`` alone leaves a live tunnel
        because WireGuard handshakes never re-check the panel. DB is the source
        of truth: new keys are committed first, then the ACTIVE peer's
        interface is re-keyed best-effort (remove old pubkey, add new). Dormant
        peers (other regions, not installed) only get the DB key update and go
        live with the new key on the next switch. PSK rotation alone defeats
        the old device even if an agent is down and the stale peer entry
        lingers. Mirrors ``create_slot``'s push style (DB authoritative,
        ``wg set`` best-effort).
        """
        peers = self.get_slot_peers(slot.id)
        servers = [p.server for p in peers if p.server]
        new_priv, new_pub, new_psk = _generate_keypair_for(servers)
        old_pub = slot.public_key
        active_peer = next(
            (p for p in peers if p.server_id == slot.active_server_id), None
        )

        # 1. DB first — slot + every peer row share the new keypair.
        slot.public_key = new_pub
        slot.private_key = new_priv
        slot.preshared_key = new_psk
        for p in peers:
            p.public_key = new_pub
            p.private_key = new_priv
            p.preshared_key = new_psk
            self.db.add(p)
        self.db.add(slot)
        self.db.commit()
        self.db.refresh(slot)

        # 2. Re-key the live interface (best-effort, like create_slot).
        if active_peer and active_peer.server:
            server = active_peer.server
            try:
                wg = self.core.clients._get_wg(server)
                try:
                    allowed_ips = [f"{active_peer.ipv4}/32"]
                    if active_peer.ipv6:
                        allowed_ips.append(f"{active_peer.ipv6}/128")
                    if old_pub:
                        wg.remove_peer(old_pub)        # kill the ghost
                    wg.add_peer(
                        public_key=new_pub,
                        allowed_ips=allowed_ips,
                        preshared_key=new_psk,
                    )
                finally:
                    try: wg.close()
                    except Exception: pass
            except Exception as exc:
                logger.warning(
                    "rotate_slot_keys: live re-key failed on %s (slot=%s): %s",
                    getattr(server, "name", "?"), slot.id, exc,
                )
        return slot

    def rename_slot(self, slot: DeviceSlot, new_label: str) -> DeviceSlot:
        slot.label = new_label.strip()[:64] or slot.label
        self.db.add(slot)
        self.db.commit()
        self.db.refresh(slot)
        return slot
