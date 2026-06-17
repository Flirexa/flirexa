"""Grace-on-suspend in license enforcement (reconcile).

A transient FREE-tier read (license re-issue, network blip, misread) must NOT
drop the live fleet. reconcile() debounces the suspend behind
LICENSE_SUSPEND_GRACE_HOURS; a genuine lapse still suspends after the window.
"""
import time
import pytest

from src.modules.license import enforcement
from src.database.models import Server, ServerLifecycleStatus


def _mk_server(db, name, stype="amneziawg", lifecycle=None, ssh_host=None, agent_url=None):
    s = Server(
        name=name, endpoint=f"{name}.example.com:51820",
        public_key="K" * 44, private_key="K" * 44,
        interface="awg0", address_pool_ipv4="10.66.10.0/24",
        server_type=stype, customer_visible=True, is_active=True,
        ssh_host=ssh_host, agent_url=agent_url,
    )
    if lifecycle:
        s.lifecycle_status = lifecycle
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    # Isolate the persisted grace state file + never touch a real interface.
    monkeypatch.setattr(enforcement, "_STATE_FILE", tmp_path / "suspend_state.json")
    monkeypatch.setattr(enforcement, "_stop_server_runtime", lambda s: None)


@pytest.fixture
def set_tier(monkeypatch):
    """Force reconcile() to read paid (multi_server) or free."""
    def _set(paid: bool):
        info = type("I", (), {"has_feature": lambda self, f: (f == "multi_server" and paid)})()
        mgr = type("M", (), {"get_license_info": lambda self: info})()
        monkeypatch.setattr("src.modules.license.manager.get_license_manager", lambda: mgr)
    return _set


class TestGraceOnSuspend:
    def test_first_free_starts_grace_no_suspend(self, db_session, set_tier, monkeypatch):
        monkeypatch.setattr(enforcement, "_SUSPEND_GRACE_H", 72)
        set_tier(paid=False)
        _mk_server(db_session, "a", "amneziawg")
        _mk_server(db_session, "b", "amneziawg")   # excess
        r = enforcement.reconcile(db_session)
        assert r["suspended"] == 0
        assert r["grace_remaining_h"] == 72.0
        assert enforcement._load_first_free() is not None

    def test_within_grace_no_suspend(self, db_session, set_tier, monkeypatch):
        monkeypatch.setattr(enforcement, "_SUSPEND_GRACE_H", 72)
        set_tier(paid=False)
        _mk_server(db_session, "a", "amneziawg")
        _mk_server(db_session, "b", "amneziawg")
        enforcement._save_first_free(time.time() - 3600)   # 1h into the streak
        r = enforcement.reconcile(db_session)
        assert r["suspended"] == 0
        assert 70.0 < r["grace_remaining_h"] < 72.0

    def test_past_grace_suspends(self, db_session, set_tier, monkeypatch):
        monkeypatch.setattr(enforcement, "_SUSPEND_GRACE_H", 72)
        set_tier(paid=False)
        _mk_server(db_session, "a", "amneziawg")   # oldest amneziawg kept
        _mk_server(db_session, "b", "amneziawg")   # excess → suspended
        enforcement._save_first_free(time.time() - 73 * 3600)   # past the window
        r = enforcement.reconcile(db_session)
        assert r["suspended"] == 1

    def test_paid_clears_timer_and_unsuspends(self, db_session, set_tier, monkeypatch):
        monkeypatch.setattr(enforcement, "_SUSPEND_GRACE_H", 72)
        _mk_server(db_session, "a", "amneziawg",
                   lifecycle=ServerLifecycleStatus.SUSPENDED_NO_LICENSE.value)
        enforcement._save_first_free(time.time() - 3600)
        set_tier(paid=True)
        r = enforcement.reconcile(db_session)
        assert r["unsuspended"] == 1
        assert enforcement._load_first_free() is None   # streak cleared on paid

    def test_grace_disabled_suspends_immediately(self, db_session, set_tier, monkeypatch):
        monkeypatch.setattr(enforcement, "_SUSPEND_GRACE_H", 0)   # legacy behaviour
        set_tier(paid=False)
        _mk_server(db_session, "a", "amneziawg")
        _mk_server(db_session, "b", "amneziawg")   # excess
        r = enforcement.reconcile(db_session)
        assert r["suspended"] == 1
        assert enforcement._load_first_free() is None   # never recorded when grace=0


class TestFreeLocalQuota:
    """FREE = up to 1 LOCAL wireguard + 1 LOCAL amneziawg on the install box.
    Remote/agent servers and proxy protocols (hysteria2/tuic) are paid-only."""

    def _free_now(self, monkeypatch, set_tier):
        monkeypatch.setattr(enforcement, "_SUSPEND_GRACE_H", 0)  # suspend immediately
        set_tier(paid=False)

    def test_keeps_one_local_of_each_protocol(self, db_session, set_tier, monkeypatch):
        self._free_now(monkeypatch, set_tier)
        _mk_server(db_session, "wg", "wireguard")
        _mk_server(db_session, "awg", "amneziawg")
        r = enforcement.reconcile(db_session)
        assert r["suspended"] == 0   # two local, one per protocol → both kept

    def test_suspends_remote_server_even_if_only_one(self, db_session, set_tier, monkeypatch):
        self._free_now(monkeypatch, set_tier)
        _mk_server(db_session, "remote-wg", "wireguard", ssh_host="10.0.0.9")
        r = enforcement.reconcile(db_session)
        assert r["suspended"] == 1   # remote needs a subscription

    def test_suspends_agent_server(self, db_session, set_tier, monkeypatch):
        self._free_now(monkeypatch, set_tier)
        _mk_server(db_session, "agent-awg", "amneziawg", agent_url="http://10.0.0.9:8080")
        r = enforcement.reconcile(db_session)
        assert r["suspended"] == 1

    def test_suspends_proxy_protocols(self, db_session, set_tier, monkeypatch):
        self._free_now(monkeypatch, set_tier)
        _mk_server(db_session, "hy2", "hysteria2")   # local but proxy → paid-only
        _mk_server(db_session, "tuic", "tuic")
        r = enforcement.reconcile(db_session)
        assert r["suspended"] == 2

    def test_remote_does_not_consume_local_slot(self, db_session, set_tier, monkeypatch):
        self._free_now(monkeypatch, set_tier)
        _mk_server(db_session, "remote-wg", "wireguard", ssh_host="10.0.0.9")  # oldest, remote
        local = _mk_server(db_session, "local-wg", "wireguard")               # newer, local
        r = enforcement.reconcile(db_session)
        assert r["suspended"] == 1   # only the remote one
        db_session.refresh(local)
        assert local.lifecycle_status != ServerLifecycleStatus.SUSPENDED_NO_LICENSE.value
