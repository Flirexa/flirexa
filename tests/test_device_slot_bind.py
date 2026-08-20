"""API-level regression tests for device-bind get-or-create on
``POST /client-portal/devices``.

Bug being locked down: two Android phones on a 2-device plan ended up
sharing ONE slot. The endpoint used to always create a slot and rely on
a fragile *client-side* label match for idempotency — so a second device
of the same platform (both labelled "Phone") reused the first's slot.

The endpoint now keys on the ``X-Device-Id`` header the apps already
send on every request:

  1. same device id  -> same slot (idempotent across logout/login)
  2. different device -> its own slot (up to max_devices)
  3. an unbound slot  -> remains reserved for its original device
  4. at the cap       -> 409 device_limit_reached
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("SMTP_ENABLED", "false")
os.environ.setdefault("LICENSE_CHECK_ENABLED", "false")

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.models import Base, Client, Server
from src.database.connection import get_db
from src.api.main import create_app
from src.api.routes import client_portal as cp
from src.modules.subscription.slot_manager import SlotManager
from src.modules.subscription.subscription_models import (
    ClientUser,
    ClientUserClients,
    DeviceSlot,
    SubscriptionPlan,
    ClientPortalSubscription,
    SubscriptionStatus,
)

USER_ID = 1
DEV_A = "A" * 20
DEV_B = "B" * 20
DEV_C = "C" * 20


def _fake_create_slot(self, user, label, initial_server_id=None,
                      bandwidth_limit_mbps=None, traffic_limit_mb=None,
                      expiry_days=None):
    """Insert a minimal slot row without touching wg/agent provisioning."""
    import uuid
    slot = DeviceSlot(
        client_user_id=user.id,
        label=label,
        public_key=uuid.uuid4().hex.ljust(43, "x")[:43] + "=",
        private_key="k" * 43 + "=",
        active_server_id=initial_server_id,
    )
    self.db.add(slot)
    self.db.flush()
    return slot


@pytest.fixture
def ctx():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    app = create_app(debug=True)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[cp.get_current_user] = lambda: USER_ID

    db = Session()
    db.add(Server(
        name="wg0", interface="wg0", endpoint="203.0.113.1:57473", listen_port=57473,
        public_key="S" * 43 + "=", private_key="P" * 43 + "=",
        address_pool_ipv4="10.66.66.0/24", dns="1.1.1.1", max_clients=250,
        config_path="/etc/wireguard/wg0.conf",
    ))
    db.add(ClientUser(id=USER_ID, email="a@b.c", username="u", password_hash="x"))
    db.add(SubscriptionPlan(
        tier="Pro", name="Pro", description="", max_devices=2,
        traffic_limit_gb=None, bandwidth_limit_mbps=None, price_monthly_usd=9.0,
        is_active=True, is_visible=True, display_order=1, features={},
    ))
    db.add(ClientPortalSubscription(
        user_id=USER_ID, tier="Pro", status=SubscriptionStatus.ACTIVE,
        max_devices=2,  # the cap lives on the subscription row, not the plan
        expiry_date=datetime.now(timezone.utc) + timedelta(days=30),
    ))
    db.commit()
    server_id = db.query(Server).first().id
    db.close()

    yield TestClient(app), Session, server_id

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _post(client, device_id=None, label="Phone"):
    headers = {"X-Device-Id": device_id} if device_id else {}
    return client.post("/client-portal/devices", json={"label": label}, headers=headers)


def test_same_device_id_is_idempotent(ctx):
    client, Session, _ = ctx
    with patch.object(SlotManager, "create_slot", _fake_create_slot):
        r1 = _post(client, DEV_A)
        assert r1.status_code == 200, r1.text
        r2 = _post(client, DEV_A)
        assert r2.status_code == 200, r2.text
    assert r1.json()["id"] == r2.json()["id"]
    db = Session()
    assert db.query(DeviceSlot).count() == 1   # not leaked on the 2nd call
    db.close()


def test_two_different_devices_get_two_slots(ctx):
    client, Session, _ = ctx
    with patch.object(SlotManager, "create_slot", _fake_create_slot):
        id_a = _post(client, DEV_A).json()["id"]
        id_b = _post(client, DEV_B).json()["id"]
    assert id_a != id_b                         # the core bug: must NOT collide
    db = Session()
    assert db.query(DeviceSlot).count() == 2
    db.close()


def test_unbound_slot_is_not_stolen_by_new_device(ctx):
    # A pre-existing UNBOUND slot (another device that hasn't connected yet,
    # or a legacy / web-portal slot) must NOT be adopted by a fresh device —
    # that was the "phone grabs the Windows card and shows Windows" bug. The
    # new device gets its OWN slot; the unbound one is left untouched.
    client, Session, server_id = ctx
    db = Session()
    db.add(DeviceSlot(
        client_user_id=USER_ID, label="Windows",
        public_key="u" * 43 + "=", private_key="k" * 43 + "=",
        active_server_id=server_id,
    ))
    db.commit()
    db.close()
    with patch.object(SlotManager, "create_slot", _fake_create_slot):
        r = _post(client, DEV_B, label="Phone")
    assert r.status_code == 200, r.text
    db = Session()
    assert db.query(DeviceSlot).count() == 2            # created its own, didn't adopt
    win = db.query(DeviceSlot).filter(DeviceSlot.label == "Windows").first()
    assert win is not None and win.device_id is None    # left untouched / still unbound
    mine = db.query(DeviceSlot).filter(DeviceSlot.device_id == DEV_B).first()
    assert mine is not None and mine.label == "Phone"   # bound to the new device
    db.close()


def test_device_over_cap_gets_409(ctx):
    client, Session, server_id = ctx
    db = Session()
    for d in (DEV_A, DEV_B):
        db.add(DeviceSlot(
            client_user_id=USER_ID, label="x",
            public_key=d + "x" * 30 + "=", private_key="k" * 43 + "=",
            device_id=d, active_server_id=server_id,
        ))
    db.commit()
    db.close()
    r = _post(client, DEV_C)                     # cap=2 already used by A+B
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "device_limit_reached"


def test_slot_qr_requires_ownership_and_uses_existing_peer_renderer(ctx, monkeypatch):
    client, Session, server_id = ctx
    db = Session()
    slot = DeviceSlot(
        client_user_id=USER_ID,
        label="Laptop",
        public_key="u" * 43 + "=",
        private_key="k" * 43 + "=",
        active_server_id=server_id,
    )
    db.add(slot)
    db.flush()
    peer = Client(
        name="Laptop",
        server_id=server_id,
        public_key="c" * 43 + "=",
        private_key="p" * 43 + "=",
        ipv4="10.66.66.2",
        ip_index=2,
        enabled=True,
    )
    db.add(peer)
    db.flush()
    db.add(ClientUserClients(client_user_id=USER_ID, client_id=peer.id, slot_id=slot.id))
    db.commit()
    slot_id = slot.id
    peer_id = peer.id
    db.close()

    seen = []

    class FakeAdminApi:
        async def get_client_qrcode(self, client_id):
            seen.append(client_id)
            return b"\x89PNG\r\n\x1a\nsynthetic"

    monkeypatch.setattr(cp, "admin_api", FakeAdminApi())
    response = client.get(f"/client-portal/devices/{slot_id}/qrcode/{server_id}")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
    assert seen == [peer_id]

    db = Session()
    db.query(DeviceSlot).filter(DeviceSlot.id == slot_id).update(
        {"device_id": DEV_A}, synchronize_session=False
    )
    db.commit()
    db.close()
    bound = client.get(f"/client-portal/devices/{slot_id}/qrcode/{server_id}")
    assert bound.status_code == 409
    assert bound.json()["detail"]["code"] == "device_already_bound"
    assert seen == [peer_id]

    app = client.app
    app.dependency_overrides[cp.get_current_user] = lambda: USER_ID + 1
    denied = client.get(f"/client-portal/devices/{slot_id}/qrcode/{server_id}")
    assert denied.status_code == 404
