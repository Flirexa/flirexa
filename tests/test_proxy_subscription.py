"""Tests for GET /client-portal/sub/{token}/proxy — the base64
proxy-subscription endpoint (Task 7 of the VLESS-Reality feature).

Closes a pre-existing gap: the WireGuard subscription endpoint
(GET /sub/{token}, tested implicitly via ``get_subscription_config``)
skips proxy clients entirely (``if not c.private_key: continue``), so
Hysteria2/TUIC/VLESS-Reality devices never showed up in a subscription
link. This endpoint delivers them as a base64(newline-joined URIs) list —
the format universal proxy clients (v2rayN/sing-box/NekoBox/Hiddify)
expect when polling a subscription URL.

Two layers:
  1. Unit tests for ``_build_proxy_subscription`` — the pure encode step,
     including the "skip a client whose access lookup raises" behavior.
  2. Full endpoint tests through a real (sqlite, in-memory) DB + TestClient,
     exercising the real token -> user -> clients -> visibility resolution
     and the real per-protocol URI builders (hysteria2/tuic/vless-reality),
     no mocking of the crypto/config-generation path.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("SMTP_ENABLED", "false")
os.environ.setdefault("LICENSE_CHECK_ENABLED", "false")

import base64
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.models import Base, Server, Client
from src.database.connection import get_db
from src.api.main import create_app
from src.api.routes import client_portal as cp
from src.modules.subscription.subscription_models import (
    ClientUser,
    ClientUserClients,
    SubscriptionPlan,
    ClientPortalSubscription,
    SubscriptionStatus,
)


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: _build_proxy_subscription
# ═══════════════════════════════════════════════════════════════════════════

def test_build_proxy_subscription_returns_base64_uri_list():
    cli = [MagicMock(id=1), MagicMock(id=2)]
    with patch("src.core.client_manager.ClientManager.get_proxy_client_access",
               side_effect=[{"uri": "vless://a"}, {"uri": "tuic://b"}]):
        body = cp._build_proxy_subscription(cli, MagicMock())
    decoded = base64.b64decode(body).decode()
    assert "vless://a" in decoded and "tuic://b" in decoded
    assert decoded == "vless://a\ntuic://b"


def test_build_proxy_subscription_skips_client_whose_access_fails():
    cli = [MagicMock(id=1), MagicMock(id=2)]
    with patch("src.core.client_manager.ClientManager.get_proxy_client_access",
               side_effect=[RuntimeError("boom"), {"uri": "hysteria2://c"}]):
        body = cp._build_proxy_subscription(cli, MagicMock())
    decoded = base64.b64decode(body).decode()
    assert decoded == "hysteria2://c"        # the raising client is silently dropped


def test_build_proxy_subscription_skips_client_with_no_uri():
    cli = [MagicMock(id=1), MagicMock(id=2)]
    with patch("src.core.client_manager.ClientManager.get_proxy_client_access",
               side_effect=[None, {"uri": "tuic://ok"}]):
        body = cp._build_proxy_subscription(cli, MagicMock())
    decoded = base64.b64decode(body).decode()
    assert decoded == "tuic://ok"


def test_build_proxy_subscription_raises_404_when_no_valid_uris():
    """When every client's access lookup fails or returns no URI, the
    subscription endpoint should 404 instead of returning an empty body."""
    cli = [MagicMock(id=1), MagicMock(id=2)]
    with patch("src.core.client_manager.ClientManager.get_proxy_client_access",
               side_effect=[RuntimeError("boom"), None]):
        with pytest.raises(HTTPException) as exc_info:
            cp._build_proxy_subscription(cli, MagicMock())
        assert exc_info.value.status_code == 404
        assert "No valid proxy configs available" in exc_info.value.detail


# ═══════════════════════════════════════════════════════════════════════════
# Full endpoint tests: GET /client-portal/sub/{token}/proxy
# ═══════════════════════════════════════════════════════════════════════════

USER_ID = 1
TOKEN = "T" * 48


def _wg_server(**overrides):
    fields = dict(
        name="wg0", interface="wg0", endpoint="203.0.113.1:51820", listen_port=51820,
        public_key="S" * 43 + "=", private_key="P" * 43 + "=",
        address_pool_ipv4="10.66.66.0/24", dns="1.1.1.1", max_clients=250,
        config_path="/etc/wireguard/wg0.conf",
        server_type="wireguard", server_category="vpn",
    )
    fields.update(overrides)
    return Server(**fields)


def _hysteria2_server(**overrides):
    fields = dict(
        name="hy2-1", interface="hy0", endpoint="203.0.113.2:8443", listen_port=8443,
        public_key="H" * 43 + "=", private_key="P" * 43 + "=",
        address_pool_ipv4="10.66.67.0/24", dns="1.1.1.1", max_clients=250,
        config_path="/etc/wireguard/unused.conf",
        server_type="hysteria2", server_category="proxy",
        proxy_domain="hy2.example.com", proxy_tls_mode="self_signed",
        proxy_config_path="/etc/hysteria/config.yaml", proxy_service_name="hysteria-server",
        proxy_auth_password="serverpw",
    )
    fields.update(overrides)
    return Server(**fields)


def _tuic_server(**overrides):
    fields = dict(
        name="tuic-1", interface="tu0", endpoint="203.0.113.3:8444", listen_port=8444,
        public_key="T" * 43 + "=", private_key="P" * 43 + "=",
        address_pool_ipv4="10.66.68.0/24", dns="1.1.1.1", max_clients=250,
        config_path="/etc/wireguard/unused2.conf",
        server_type="tuic", server_category="proxy",
        proxy_domain="tuic.example.com", proxy_tls_mode="self_signed",
        proxy_config_path="/etc/tuic/config.json", proxy_service_name="tuic-server",
    )
    fields.update(overrides)
    return Server(**fields)


def _vless_server(**overrides):
    fields = dict(
        name="vless-1", interface="vl0", endpoint="203.0.113.4:443", listen_port=443,
        public_key="V" * 43 + "=", private_key="P" * 43 + "=",
        address_pool_ipv4="10.66.69.0/24", dns="1.1.1.1", max_clients=250,
        config_path="/etc/wireguard/unused3.conf",
        server_type="vless-reality", server_category="proxy",
        proxy_domain="www.microsoft.com",
        proxy_config_path="/etc/xray/config.json", proxy_service_name="xray-reality",
        proxy_reality_private_key="PRIV", proxy_reality_public_key="PUB",
        proxy_reality_short_id="deadbeefdeadbeef",
    )
    fields.update(overrides)
    return Server(**fields)


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

    db = Session()
    db.add(ClientUser(
        id=USER_ID, email="a@b.c", username="u", password_hash="x",
        is_active=True, is_banned=False, subscription_token=TOKEN,
    ))
    db.add(SubscriptionPlan(
        tier="Pro", name="Pro", description="", max_devices=5,
        traffic_limit_gb=None, bandwidth_limit_mbps=None, price_monthly_usd=9.0,
        is_active=True, is_visible=True, display_order=1, features={},
    ))
    db.add(ClientPortalSubscription(
        user_id=USER_ID, tier="Pro", status=SubscriptionStatus.ACTIVE,
        max_devices=5, expiry_date=datetime.now(timezone.utc) + timedelta(days=30),
    ))
    db.commit()
    db.close()

    yield TestClient(app), Session

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _link(db, client):
    db.add(client)
    db.flush()
    db.add(ClientUserClients(client_user_id=USER_ID, client_id=client.id))
    return client


def test_proxy_subscription_returns_all_three_protocol_uris(ctx):
    client, Session = ctx
    db = Session()
    _link(db, Client(name="phone-wg", server=_wg_server(), public_key="K" * 43 + "=",
                      private_key="k" * 43 + "="))
    _link(db, Client(name="phone-hy2", server=_hysteria2_server(), public_key=None,
                      proxy_password="clientpw"))
    _link(db, Client(name="phone-tuic", server=_tuic_server(), public_key=None,
                      proxy_uuid="11111111-1111-1111-1111-111111111111", proxy_password="clientpw2"))
    _link(db, Client(name="phone-vless", server=_vless_server(), public_key=None,
                      proxy_uuid="22222222-2222-2222-2222-222222222222"))
    db.commit()
    db.close()

    r = client.get(f"/client-portal/sub/{TOKEN}/proxy")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")

    decoded = base64.b64decode(r.text).decode()
    lines = decoded.splitlines()
    assert len(lines) == 3                              # WG client contributes no URI
    assert any(l.startswith("hysteria2://") for l in lines)
    assert any(l.startswith("tuic://") for l in lines)
    assert any(l.startswith("vless://22222222-2222-2222-2222-222222222222@") for l in lines)


def test_proxy_subscription_404_when_only_wg_devices(ctx):
    client, Session = ctx
    db = Session()
    _link(db, Client(name="phone-wg", server=_wg_server(), public_key="K" * 43 + "=",
                      private_key="k" * 43 + "="))
    db.commit()
    db.close()

    r = client.get(f"/client-portal/sub/{TOKEN}/proxy")
    assert r.status_code == 404


def test_proxy_subscription_404_for_unknown_token(ctx):
    client, _Session = ctx
    r = client.get(f"/client-portal/sub/{'X' * 48}/proxy")
    assert r.status_code == 404


def test_proxy_subscription_excludes_invisible_server(ctx):
    """A proxy client on a server with customer_visible=False must not
    leak into the subscription — same visibility rule as GET /sub/{token}."""
    client, Session = ctx
    db = Session()
    _link(db, Client(name="phone-hy2-hidden", server=_hysteria2_server(customer_visible=False),
                      public_key=None, proxy_password="clientpw"))
    db.commit()
    db.close()

    r = client.get(f"/client-portal/sub/{TOKEN}/proxy")
    assert r.status_code == 404


def test_wg_subscription_endpoint_still_returns_wg_config_not_proxy(ctx):
    """Confirm GET /sub/{token} (unmodified) still returns the WG config
    blob and is untouched by the new /proxy endpoint."""
    client, Session = ctx
    db = Session()
    _link(db, Client(name="phone-wg", server=_wg_server(), public_key="K" * 43 + "=",
                      private_key="k" * 43 + "="))
    db.commit()
    db.close()

    r = client.get(f"/client-portal/sub/{TOKEN}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")
    assert "Device: phone-wg" in r.text
    # It's a WG config blob, not base64 — decoding it as base64 would not
    # yield anything meaningful; just assert it looks like Interface/Peer text.
    assert "[Interface]" in r.text or "PrivateKey" in r.text
