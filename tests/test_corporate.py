import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_ENABLED"] = "false"

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.modules.corporate import models as _corporate_models  # noqa: F401
from src.modules.corporate.manager import CorporateManager
from src.modules.subscription.subscription_models import (
    ClientUser,
    ClientPortalSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
)


def _create_corporate_user_with_plan(db_session, *, tier="Corporation", features=None):
    user = ClientUser(email=f"{tier.lower()}@example.com", username=f"{tier.lower()}user", password_hash="x")
    db_session.add(user)
    db_session.flush()

    db_session.add(
        SubscriptionPlan(
            tier=tier,
            name=tier,
            description="corp",
            max_devices=10,
            traffic_limit_gb=None,
            bandwidth_limit_mbps=None,
            price_monthly_usd=99.0,
            is_active=True,
            is_visible=True,
            display_order=1,
            features=features or {"corp_networks": 5, "corp_sites": 30},
        )
    )
    db_session.add(
        ClientPortalSubscription(
            user_id=user.id,
            tier=tier,
            status=SubscriptionStatus.ACTIVE,
            expiry_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    db_session.commit()
    return user


def test_get_corp_limits_uses_legacy_site_defaults_when_features_missing_corp_sites(db_session):
    user = ClientUser(email="corp@example.com", username="corpuser", password_hash="x")
    db_session.add(user)
    db_session.flush()

    db_session.add(
        SubscriptionPlan(
            tier="Corporation",
            name="Corporation",
            description="corp",
            max_devices=10,
            traffic_limit_gb=None,
            bandwidth_limit_mbps=None,
            price_monthly_usd=99.0,
            is_active=True,
            is_visible=True,
            display_order=1,
            features={"corp_networks": 5},
        )
    )
    db_session.add(
        ClientPortalSubscription(
            user_id=user.id,
            tier="Corporation",
            status=SubscriptionStatus.ACTIVE,
            expiry_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    db_session.commit()

    mgr = CorporateManager(db_session)
    assert mgr._get_corp_limits(user.id) == (5, 30)


def test_get_corp_limits_returns_zero_for_expired_subscription(db_session):
    user = ClientUser(email="expired@example.com", username="expireduser", password_hash="x")
    db_session.add(user)
    db_session.flush()

    db_session.add(
        SubscriptionPlan(
            tier="Standard",
            name="Standard",
            description="std",
            max_devices=5,
            traffic_limit_gb=100,
            bandwidth_limit_mbps=100,
            price_monthly_usd=10.0,
            is_active=True,
            is_visible=True,
            display_order=1,
            features={"corp_networks": 1, "corp_sites": 5},
        )
    )
    db_session.add(
        ClientPortalSubscription(
            user_id=user.id,
            tier="Standard",
            status=SubscriptionStatus.ACTIVE,
            expiry_date=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    db_session.commit()

    mgr = CorporateManager(db_session)
    assert mgr._get_corp_limits(user.id) == (0, 0)


@patch("src.modules.corporate.manager.subprocess.run")
def test_add_site_uses_endpoint_port_as_listen_port_when_listen_port_missing(mock_run, db_session):
    mock_run.side_effect = [
        type("R", (), {"stdout": "privkey\n"})(),
        type("R", (), {"stdout": "pubkey\n"})(),
    ]
    user = _create_corporate_user_with_plan(db_session)
    mgr = CorporateManager(db_session)
    network = mgr.create_network(user.id, "Corp Net")
    db_session.flush()

    site = mgr.add_site(
        network=network,
        name="Shop",
        local_subnets=["192.168.10.0/24"],
        endpoint="198.51.100.10:51831",
    )

    assert site.listen_port == 51831
    assert site.endpoint == "198.51.100.10:51831"


@patch("src.modules.corporate.manager.subprocess.run")
def test_add_site_rejects_endpoint_and_listen_port_mismatch(mock_run, db_session):
    mock_run.side_effect = [
        type("R", (), {"stdout": "privkey\n"})(),
        type("R", (), {"stdout": "pubkey\n"})(),
    ]
    user = _create_corporate_user_with_plan(db_session)
    mgr = CorporateManager(db_session)
    network = mgr.create_network(user.id, "Corp Net")
    db_session.flush()

    try:
        mgr.add_site(
            network=network,
            name="Shop",
            local_subnets=["192.168.10.0/24"],
            endpoint="198.51.100.10:51831",
            listen_port=51820,
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Listen port must match" in str(exc)


@patch("src.modules.corporate.manager.subprocess.run")
def test_update_site_allows_clearing_endpoint_when_demoting_relay(mock_run, db_session):
    mock_run.side_effect = [
        type("R", (), {"stdout": "privkey-1\n"})(),
        type("R", (), {"stdout": "pubkey-1\n"})(),
    ]
    user = _create_corporate_user_with_plan(db_session)
    mgr = CorporateManager(db_session)
    network = mgr.create_network(user.id, "Corp Net")
    db_session.flush()

    relay = mgr.add_site(
        network=network,
        name="Relay",
        local_subnets=["192.168.10.0/24"],
        endpoint="198.51.100.20:51820",
        is_relay=True,
    )

    mgr.update_site(relay, endpoint="", is_relay=False, routing_mode="auto")

    assert relay.is_relay is False
    assert relay.endpoint is None


@patch("src.modules.corporate.manager.subprocess.run")
def test_update_site_rejects_via_relay_when_network_has_no_relay(mock_run, db_session):
    mock_run.side_effect = [
        type("R", (), {"stdout": "privkey-1\n"})(),
        type("R", (), {"stdout": "pubkey-1\n"})(),
    ]
    user = _create_corporate_user_with_plan(db_session)
    mgr = CorporateManager(db_session)
    network = mgr.create_network(user.id, "Corp Net")
    db_session.flush()
    site = mgr.add_site(
        network=network,
        name="Shop",
        local_subnets=["192.168.10.0/24"],
        endpoint="198.51.100.21:51821",
    )

    try:
        mgr.update_site(site, routing_mode="via_relay")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "requires an active relay site" in str(exc)


@patch("src.modules.corporate.manager.subprocess.run")
def test_generate_site_config_includes_router_deployment_hints_and_routes(mock_run, db_session):
    mock_run.side_effect = [
        type("R", (), {"stdout": "privkey-1\n"})(),
        type("R", (), {"stdout": "pubkey-1\n"})(),
        type("R", (), {"stdout": "privkey-2\n"})(),
        type("R", (), {"stdout": "pubkey-2\n"})(),
    ]
    user = _create_corporate_user_with_plan(db_session)
    mgr = CorporateManager(db_session)
    network = mgr.create_network(user.id, "Corp Net")
    db_session.flush()

    shop = mgr.add_site(
        network=network,
        name="Shop",
        local_subnets=["192.168.10.0/24"],
        endpoint="198.51.100.10:51831",
    )
    warehouse = mgr.add_site(
        network=network,
        name="Warehouse",
        local_subnets=["192.168.20.0/24"],
        endpoint="198.51.100.11:51832",
    )

    config = mgr.generate_site_config(shop)

    assert "Deploy this config on your router/firewall" in config
    assert "This site advertises these local networks" in config
    assert "192.168.10.0/24" in config
    assert "Reach via direct peer 'Warehouse': 192.168.20.0/24" in config
    assert "ListenPort = 51831" in config
