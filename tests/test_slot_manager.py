"""
Tests for the multi-server device-slot system.

Two layers covered here:

  1. Pure helpers (``_slot_peer_name``, ``is_free_tier_enabled``) —
     deterministic, no DB, no agent.
  2. Lightweight SlotManager flows against the in-memory SQLite engine
     from conftest. The wg/awg side is mocked through ``ClientManager``
     so we don't need real interfaces — these tests exercise the DB and
     accounting logic that's hard to verify without a customer.

Why this file exists: every slot-system regression so far landed in a
production database before anyone caught it. The smoke-tests below
take seconds to run and catch the regressions we already lived through:

  • slot name shape (the "slot-N → slot-N+1 after recreate" UX issue)
  • IP-suffix-in-storage drift (the "Address = X/32/32" bug)
  • Backfill idempotency (re-running heal doesn't dup peers)
  • Free-tier gate flip
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ──────────────────────────────────────────────────────────────────────────
# Pure helper: _slot_peer_name
# ──────────────────────────────────────────────────────────────────────────

class TestSlotPeerName:
    """Naming convention that customers don't see directly but admins
    do — has to be stable across recreates and safe for the
    ``clients.name`` column (≤100 chars, ``[A-Za-z0-9._-]``)."""

    def _slot(self, label="Phone", public_key="abc123", id_=5):
        s = MagicMock()
        s.label = label
        s.public_key = public_key
        s.id = id_
        return s

    def _server(self, name="TexasUSA"):
        s = MagicMock()
        s.name = name
        return s

    def test_uses_label_not_slot_id(self):
        from src.modules.subscription.slot_manager import _slot_peer_name
        name = _slot_peer_name(self._slot(label="Phone"), self._server())
        assert "Phone" in name
        assert "slot-5" not in name  # legacy slot-{id} prefix must not appear

    def test_stable_across_recreates(self):
        """Same label + same shared keypair → same suffix → same name.
        That's the whole point of using a key-derived suffix instead of
        the auto-incrementing slot.id."""
        from src.modules.subscription.slot_manager import _slot_peer_name
        s1 = self._slot(label="Phone", public_key="same-key", id_=5)
        s2 = self._slot(label="Phone", public_key="same-key", id_=99)
        a = _slot_peer_name(s1, self._server())
        b = _slot_peer_name(s2, self._server())
        assert a == b

    def test_differs_when_keypair_differs(self):
        """Two slots with the same label but different keys disambiguate.
        Without this two devices both labelled 'Phone' would collide on
        the per-server (server_id, name) unique constraint."""
        from src.modules.subscription.slot_manager import _slot_peer_name
        a = _slot_peer_name(
            self._slot(label="Phone", public_key="key-a"),
            self._server(),
        )
        b = _slot_peer_name(
            self._slot(label="Phone", public_key="key-b"),
            self._server(),
        )
        assert a != b

    def test_sanitises_label(self):
        from src.modules.subscription.slot_manager import _slot_peer_name
        name = _slot_peer_name(
            self._slot(label="My Phone / 2024 !!"),
            self._server(),
        )
        # All chars valid for clients.name
        import re
        assert re.fullmatch(r"[A-Za-z0-9._-]+", name)

    def test_empty_label_falls_back_to_device(self):
        from src.modules.subscription.slot_manager import _slot_peer_name
        name = _slot_peer_name(self._slot(label=""), self._server())
        assert name.startswith("Device-")

    def test_caps_at_100_chars(self):
        from src.modules.subscription.slot_manager import _slot_peer_name
        long_label = "A" * 200
        name = _slot_peer_name(self._slot(label=long_label), self._server())
        assert len(name) <= 100


# ──────────────────────────────────────────────────────────────────────────
# Pure helper: is_free_tier_enabled
# ──────────────────────────────────────────────────────────────────────────

class TestFreeTierToggle:
    """Defaults to True on every install. Admin can flip to False via
    Settings → Free tier; new sign-ups then skip auto-creation of the
    free subscription row."""

    def test_default_true_when_no_row(self, db_session):
        from src.modules.subscription.subscription_manager import is_free_tier_enabled
        assert is_free_tier_enabled(db_session) is True

    def test_respects_false(self, db_session):
        from src.database.models import SystemConfig
        from src.modules.subscription.subscription_manager import is_free_tier_enabled
        db_session.add(SystemConfig(
            key="enable_free_tier", value="false", value_type="bool",
        ))
        db_session.commit()
        assert is_free_tier_enabled(db_session) is False

    @pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes", "on", " true "])
    def test_truthy_variants(self, db_session, raw):
        from src.database.models import SystemConfig
        from src.modules.subscription.subscription_manager import is_free_tier_enabled
        db_session.add(SystemConfig(
            key="enable_free_tier", value=raw, value_type="bool",
        ))
        db_session.commit()
        assert is_free_tier_enabled(db_session) is True

    @pytest.mark.parametrize("raw", ["false", "0", "no", "off", "FALSE"])
    def test_falsy_variants(self, db_session, raw):
        from src.database.models import SystemConfig
        from src.modules.subscription.subscription_manager import is_free_tier_enabled
        db_session.add(SystemConfig(
            key="enable_free_tier", value=raw, value_type="bool",
        ))
        db_session.commit()
        assert is_free_tier_enabled(db_session) is False


# ──────────────────────────────────────────────────────────────────────────
# SlotManager — DB-backed flows
# ──────────────────────────────────────────────────────────────────────────

@pytest.fixture
def two_visible_servers(db_session):
    """Insert two customer-visible AmneziaWG servers into the test DB.

    Both have a /24 pool so the IP allocator can hand out addresses
    deterministically (offsets 2, 3, 4, …). Each gets a distinct fake
    server pubkey — the slot system doesn't care about server keys,
    but the Server schema requires non-null.
    """
    from src.database.models import Server
    servers = [
        Server(
            name="server-a", endpoint="a.example.com:51820",
            public_key="A" * 44, private_key="A" * 44,
            interface="awg0",
            address_pool_ipv4="10.66.10.0/24",
            server_type="amneziawg",
            customer_visible=True, is_active=True,
        ),
        Server(
            name="server-b", endpoint="b.example.com:51820",
            public_key="B" * 44, private_key="B" * 44,
            interface="awg0",
            address_pool_ipv4="10.66.20.0/24",
            server_type="amneziawg",
            customer_visible=True, is_active=True,
        ),
    ]
    for s in servers:
        db_session.add(s)
    db_session.commit()
    for s in servers:
        db_session.refresh(s)
    return servers


@pytest.fixture
def client_user(db_session):
    """One ClientUser to anchor the slot."""
    from src.modules.subscription.subscription_models import ClientUser
    u = ClientUser(
        email="test@example.com",
        password_hash="x",
        username="test",
        email_verified=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def patched_wg(monkeypatch):
    """Stub ``ClientManager._get_wg`` so SlotManager.create_slot doesn't
    try to reach a real WireGuard interface. The mock returns a context
    that pretends ``add_peer`` succeeded — that's enough for the DB
    accounting we want to test."""
    fake_wg = MagicMock()
    fake_wg.add_peer.return_value = True
    fake_wg.remove_peer.return_value = True
    fake_wg.close.return_value = None
    with patch(
        "src.core.client_manager.ClientManager._get_wg",
        return_value=fake_wg,
    ):
        yield fake_wg


class TestSlotProvisioning:
    def test_create_slot_provisions_one_peer_per_visible_server(
        self, db_session, two_visible_servers, client_user, patched_wg,
    ):
        from src.modules.subscription.slot_manager import SlotManager
        from src.modules.subscription.subscription_models import ClientUserClients
        from src.database.models import Client

        mgr = SlotManager(db_session)
        slot = mgr.create_slot(user=client_user, label="Phone")

        # One peer per server.
        peers = (
            db_session.query(Client)
            .join(ClientUserClients, ClientUserClients.client_id == Client.id)
            .filter(ClientUserClients.slot_id == slot.id)
            .all()
        )
        assert len(peers) == 2
        # Shared keypair across both peers — that's the whole point of slots.
        assert peers[0].public_key == peers[1].public_key
        assert peers[0].private_key == peers[1].private_key
        # Exactly one enabled (the slot's active server).
        enabled = [p for p in peers if p.enabled]
        assert len(enabled) == 1
        assert enabled[0].server_id == slot.active_server_id

    def test_ipv4_stored_without_cidr_suffix(
        self, db_session, two_visible_servers, client_user, patched_wg,
    ):
        """Regression for the "Address = X/32/32" bug — the Client.ipv4
        column must hold a bare address, not "10.x.x.x/32"."""
        from src.modules.subscription.slot_manager import SlotManager
        from src.modules.subscription.subscription_models import ClientUserClients
        from src.database.models import Client

        mgr = SlotManager(db_session)
        slot = mgr.create_slot(user=client_user, label="Phone")
        peers = (
            db_session.query(Client)
            .join(ClientUserClients, ClientUserClients.client_id == Client.id)
            .filter(ClientUserClients.slot_id == slot.id)
            .all()
        )
        for p in peers:
            assert "/" not in (p.ipv4 or ""), (
                f"ipv4 stored with CIDR suffix: {p.ipv4!r}"
            )

    def test_heal_slot_is_idempotent(
        self, db_session, two_visible_servers, client_user, patched_wg,
    ):
        """heal_slot should be safe to call multiple times — it's
        invoked from GET /devices as a lazy backfill, so any redundancy
        would create duplicate Client rows on every portal page-load."""
        from src.modules.subscription.slot_manager import SlotManager
        from src.modules.subscription.subscription_models import ClientUserClients

        mgr = SlotManager(db_session)
        slot = mgr.create_slot(user=client_user, label="Phone")
        # Both servers are already provisioned by create_slot. heal_slot
        # should find nothing to do.
        a = mgr.heal_slot(slot)
        b = mgr.heal_slot(slot)
        assert a == [] and b == []
        # Sanity: still exactly two link rows.
        count = (
            db_session.query(ClientUserClients)
            .filter(ClientUserClients.slot_id == slot.id)
            .count()
        )
        assert count == 2

    def test_backfill_when_new_server_added(
        self, db_session, two_visible_servers, client_user, patched_wg,
    ):
        """Add a third customer-visible server after the slot exists,
        then call backfill — the slot must end up with a peer on the
        new server. That's the operator-facing promise of "spin up a
        new region and existing devices pick it up automatically"."""
        from src.modules.subscription.slot_manager import SlotManager
        from src.modules.subscription.subscription_models import ClientUserClients
        from src.database.models import Server

        mgr = SlotManager(db_session)
        slot = mgr.create_slot(user=client_user, label="Phone")
        new_srv = Server(
            name="server-c", endpoint="c.example.com:51820",
            public_key="C" * 44, private_key="C" * 44,
            interface="awg0",
            address_pool_ipv4="10.66.30.0/24",
            server_type="amneziawg",
            customer_visible=True, is_active=True,
        )
        db_session.add(new_srv)
        db_session.commit()
        db_session.refresh(new_srv)

        count_added = mgr.backfill_all_slots_on_server(new_srv)
        assert count_added == 1

        peer_count = (
            db_session.query(ClientUserClients)
            .filter(ClientUserClients.slot_id == slot.id)
            .count()
        )
        assert peer_count == 3

    def test_hidden_server_skipped_in_backfill(
        self, db_session, client_user, patched_wg,
    ):
        """customer_visible=False must not seed peers — those are
        operator-side test servers and should never reach customers."""
        from src.modules.subscription.slot_manager import SlotManager
        from src.modules.subscription.subscription_models import ClientUserClients
        from src.database.models import Server

        # Visible primary first so create_slot has somewhere to land.
        visible = Server(
            name="visible", endpoint="v.example.com:51820",
            public_key="V" * 44, private_key="V" * 44,
            interface="awg0", address_pool_ipv4="10.66.10.0/24",
            server_type="amneziawg",
            customer_visible=True, is_active=True,
        )
        hidden = Server(
            name="hidden", endpoint="h.example.com:51820",
            public_key="H" * 44, private_key="H" * 44,
            interface="awg0", address_pool_ipv4="10.66.99.0/24",
            server_type="amneziawg",
            customer_visible=False, is_active=True,
        )
        db_session.add_all([visible, hidden])
        db_session.commit()
        db_session.refresh(hidden)

        from src.database.models import Client
        mgr = SlotManager(db_session)
        slot = mgr.create_slot(user=client_user, label="Phone")

        # Slot should not contain the hidden server.
        peer_servers = {
            p.server_id for p in db_session.query(Client)
            .join(ClientUserClients, ClientUserClients.client_id == Client.id)
            .filter(ClientUserClients.slot_id == slot.id)
            .all()
        }
        assert hidden.id not in peer_servers

        # Even an explicit backfill request on the hidden server is a no-op.
        added = mgr.backfill_all_slots_on_server(hidden)
        assert added == 0


class TestSlotKeyRotation:
    def test_rotate_changes_keys_and_rekeys_active_peer(
        self, db_session, two_visible_servers, client_user, patched_wg,
    ):
        from src.modules.subscription.slot_manager import SlotManager
        from src.modules.subscription.subscription_models import ClientUserClients
        from src.database.models import Client

        mgr = SlotManager(db_session)
        slot = mgr.create_slot(user=client_user, label="Phone")
        old_pub = slot.public_key
        old_priv = slot.private_key

        # Forget create_slot's own add_peer call so we assert only rotation's.
        patched_wg.reset_mock()

        mgr.rotate_slot_keys(slot)
        db_session.refresh(slot)

        # Keypair actually changed.
        assert slot.public_key != old_pub
        assert slot.private_key != old_priv

        # Every peer row shares the NEW keypair (slots are one-key-many-peers).
        peers = (
            db_session.query(Client)
            .join(ClientUserClients, ClientUserClients.client_id == Client.id)
            .filter(ClientUserClients.slot_id == slot.id)
            .all()
        )
        assert peers, "rotation test needs at least one peer"
        assert all(p.public_key == slot.public_key for p in peers)
        assert all(p.private_key == slot.private_key for p in peers)

        # The live (active) interface was re-keyed: old pubkey removed, new added.
        patched_wg.remove_peer.assert_called_once_with(old_pub)
        assert patched_wg.add_peer.call_count == 1
        _, kw = patched_wg.add_peer.call_args
        assert kw["public_key"] == slot.public_key

    def test_rotate_is_idempotent(
        self, db_session, two_visible_servers, client_user, patched_wg,
    ):
        from src.modules.subscription.slot_manager import SlotManager
        mgr = SlotManager(db_session)
        slot = mgr.create_slot(user=client_user, label="Phone")
        p1 = slot.public_key
        mgr.rotate_slot_keys(slot); db_session.refresh(slot)
        p2 = slot.public_key
        mgr.rotate_slot_keys(slot); db_session.refresh(slot)
        p3 = slot.public_key
        # Each rotation yields a distinct keypair; no error on repeat.
        assert len({p1, p2, p3}) == 3


class TestSwitchRegionLeakGuard:
    """switch_active_server must not flip the active pointer (leaking access to
    the 'off' region) when the OLD peer couldn't be disabled AND the old node is
    still live — but must PROCEED when the old node is down (its leftover peer
    serves nothing, and blocking would trap the customer on a dead region)."""

    def _slot_and_target(self, db_session, servers, user):
        from src.modules.subscription.slot_manager import SlotManager
        mgr = SlotManager(db_session)
        slot = mgr.create_slot(user=user, label="Phone")
        old_id = slot.active_server_id
        target = next(s for s in servers if s.id != old_id)
        return mgr, slot, old_id, target

    def test_refuses_503_when_old_node_online_and_disable_fails(
        self, db_session, two_visible_servers, client_user, patched_wg, monkeypatch,
    ):
        import src.modules.subscription.slot_manager as sm
        from src.modules.subscription.slot_manager import SlotManagerError
        from src.database.models import Server

        mgr, slot, old_id, target = self._slot_and_target(
            db_session, two_visible_servers, client_user)
        db_session.query(Server).filter(Server.id == old_id).update(
            {"lifecycle_status": "online"}); db_session.commit()
        # disable always fails; enable would succeed.
        monkeypatch.setattr(sm, "_agent_apply",
                            lambda core, client, action: action == "enable")

        with pytest.raises(SlotManagerError) as ei:
            mgr.switch_active_server(slot, target.id)
        assert ei.value.http_status == 503

        db_session.refresh(slot)
        assert slot.active_server_id == old_id, "must NOT flip on a live-node leak"

    def test_proceeds_when_old_node_down_even_if_disable_fails(
        self, db_session, two_visible_servers, client_user, patched_wg, monkeypatch,
    ):
        import src.modules.subscription.slot_manager as sm
        from src.database.models import Server

        mgr, slot, old_id, target = self._slot_and_target(
            db_session, two_visible_servers, client_user)
        db_session.query(Server).filter(Server.id == old_id).update(
            {"lifecycle_status": "offline"}); db_session.commit()
        monkeypatch.setattr(sm, "_agent_apply",
                            lambda core, client, action: action == "enable")

        result = mgr.switch_active_server(slot, target.id)
        assert result.active_server_id == target.id, "dead old node → switch proceeds"
