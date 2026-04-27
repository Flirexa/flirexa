"""
Unit tests for SpongeBot Core modules
Tests run against SQLite in-memory DB with mocked WireGuard
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call

from src.database.models import Client, Server, ClientStatus, AuditLog, ServerStatus
from src.core.client_manager import ClientManager
from src.core.server_manager import ServerManager
from src.core.traffic_manager import TrafficManager, TrafficStats
from src.core.timer_manager import TimerManager
from src.core.management import ManagementCore
from src.modules.subscription.subscription_manager import SubscriptionManager
from src.modules.subscription.subscription_models import (
    ClientUser,
    ClientPortalPayment,
    ClientPortalSubscription,
    PaymentMethod,
    SubscriptionPlan,
    SubscriptionStatus,
)


# ============================================================================
# CLIENT MANAGER TESTS
# ============================================================================

class TestClientManager:
    """Tests for ClientManager"""

    def _make_cm(self, db_session, mock_wg_manager):
        """Create ClientManager with mocked _get_wg to return mock for all servers"""
        cm = ClientManager(db_session, mock_wg_manager)
        cm._get_wg = MagicMock(return_value=mock_wg_manager)
        return cm

    def test_create_client(self, db_session, sample_server, mock_wg_manager):
        cm = self._make_cm(db_session, mock_wg_manager)
        client = cm.create_client(name="NewPhone", server_id=sample_server.id)

        assert client is not None
        assert client.name == "NewPhone"
        assert client.server_id == sample_server.id
        assert client.enabled is True
        assert client.ipv4.startswith("10.66.66.")
        mock_wg_manager.generate_keypair.assert_called_once()
        mock_wg_manager.add_peer.assert_called_once()

    def test_create_duplicate_client(self, db_session, sample_server, sample_client, mock_wg_manager):
        cm = self._make_cm(db_session, mock_wg_manager)
        duplicate = cm.create_client(name="TestClient", server_id=sample_server.id)
        assert duplicate is None

    def test_create_client_nonexistent_server(self, db_session, mock_wg_manager):
        cm = self._make_cm(db_session, mock_wg_manager)
        client = cm.create_client(name="Test", server_id=9999)
        assert client is None

    def test_get_client(self, db_session, sample_client, mock_wg_manager):
        cm = self._make_cm(db_session, mock_wg_manager)
        client = cm.get_client(sample_client.id)
        assert client is not None
        assert client.name == "TestClient"

    def test_get_client_not_found(self, db_session, mock_wg_manager):
        cm = self._make_cm(db_session, mock_wg_manager)
        client = cm.get_client(9999)
        assert client is None

    def test_get_client_by_name(self, db_session, sample_client, mock_wg_manager):
        cm = self._make_cm(db_session, mock_wg_manager)
        client = cm.get_client_by_name("TestClient")
        assert client is not None
        assert client.id == sample_client.id

    def test_get_all_clients(self, db_session, sample_server, sample_client, mock_wg_manager):
        cm = self._make_cm(db_session, mock_wg_manager)
        clients = cm.get_all_clients()
        assert len(clients) == 1
        assert clients[0].name == "TestClient"

    def test_get_all_clients_filter_by_server(self, db_session, sample_server, sample_client, mock_wg_manager):
        cm = self._make_cm(db_session, mock_wg_manager)
        clients = cm.get_all_clients(server_id=sample_server.id)
        assert len(clients) == 1

        clients = cm.get_all_clients(server_id=9999)
        assert len(clients) == 0

    def test_disable_client(self, db_session, sample_client, mock_wg_manager):
        cm = self._make_cm(db_session, mock_wg_manager)
        result = cm.disable_client(sample_client.id)
        assert result is True

        client = cm.get_client(sample_client.id)
        assert client.enabled is False
        mock_wg_manager.remove_peer.assert_called_once()

    def test_enable_client(self, db_session, sample_client, mock_wg_manager):
        cm = self._make_cm(db_session, mock_wg_manager)
        # First disable
        cm.disable_client(sample_client.id)
        mock_wg_manager.reset_mock()

        # Then enable
        result = cm.enable_client(sample_client.id)
        assert result is True

        client = cm.get_client(sample_client.id)
        assert client.enabled is True
        mock_wg_manager.add_peer.assert_called_once()

    def test_delete_client(self, db_session, sample_client, mock_wg_manager):
        cm = self._make_cm(db_session, mock_wg_manager)
        result = cm.delete_client(sample_client.id)
        assert result is True

        client = cm.get_client(sample_client.id)
        assert client is None
        mock_wg_manager.remove_peer.assert_called_once()

    def test_delete_client_wg_first_ordering(self, db_session, sample_client, mock_wg_manager):
        """Verify delete removes WG peer BEFORE DB delete (WG-first)"""
        cm = self._make_cm(db_session, mock_wg_manager)
        call_order = []
        mock_wg_manager.remove_peer.side_effect = lambda pk: call_order.append("wg_remove") or True
        original_delete = db_session.delete
        def tracked_delete(obj):
            call_order.append("db_delete")
            return original_delete(obj)
        db_session.delete = tracked_delete

        cm.delete_client(sample_client.id)
        assert call_order == ["wg_remove", "db_delete"]

    def test_delete_client_rollback_on_db_fail(self, db_session, sample_client, mock_wg_manager):
        """If DB delete fails, WG peer should be re-added"""
        cm = self._make_cm(db_session, mock_wg_manager)
        original_commit = db_session.commit
        commit_count = [0]
        def fail_on_delete_commit():
            commit_count[0] += 1
            raise Exception("DB error")
        db_session.commit = fail_on_delete_commit

        result = cm.delete_client(sample_client.id)
        assert result is False
        # WG peer should be re-added (compensating action)
        mock_wg_manager.add_peer.assert_called_once()

    def test_enable_rollback_on_db_fail(self, db_session, sample_client, mock_wg_manager):
        """If DB commit fails after enable, WG peer should be removed"""
        cm = self._make_cm(db_session, mock_wg_manager)
        # First disable
        cm.disable_client(sample_client.id)
        mock_wg_manager.reset_mock()

        # Make commit fail
        original_commit = db_session.commit
        db_session.commit = MagicMock(side_effect=Exception("DB error"))

        result = cm.enable_client(sample_client.id)
        assert result is False
        # WG peer was added, then removed as compensation
        mock_wg_manager.add_peer.assert_called_once()
        mock_wg_manager.remove_peer.assert_called_once()

    def test_disable_rollback_on_db_fail(self, db_session, sample_client, mock_wg_manager):
        """If DB commit fails after disable, WG peer should be re-added"""
        cm = self._make_cm(db_session, mock_wg_manager)

        # Make commit fail
        original_commit = db_session.commit
        db_session.commit = MagicMock(side_effect=Exception("DB error"))

        result = cm.disable_client(sample_client.id)
        assert result is False
        # WG peer was removed, then re-added as compensation
        mock_wg_manager.remove_peer.assert_called_once()
        mock_wg_manager.add_peer.assert_called_once()

    def test_update_enabled_syncs_wg(self, db_session, sample_client, mock_wg_manager):
        """update_client with enabled=False should call disable_client (WG sync)"""
        cm = self._make_cm(db_session, mock_wg_manager)
        result = cm.update_client(sample_client.id, enabled=False)
        assert result is not None
        mock_wg_manager.remove_peer.assert_called_once()

    def test_ip_allocation_sequential(self, db_session, sample_server, mock_wg_manager):
        import base64
        # Return unique keys for each call using proper base64
        key_counter = [0]
        def unique_keypair():
            key_counter[0] += 1
            n = key_counter[0]
            priv = base64.b64encode(f"priv{n:028d}".encode()).decode()
            pub = base64.b64encode(f"pub-{n:028d}".encode()).decode()
            return (priv, pub)

        def unique_psk():
            key_counter[0] += 1
            n = key_counter[0]
            return base64.b64encode(f"psk-{n:028d}".encode()).decode()

        mock_wg_manager.generate_keypair.side_effect = unique_keypair
        mock_wg_manager.generate_preshared_key.side_effect = unique_psk

        cm = self._make_cm(db_session, mock_wg_manager)

        c1 = cm.create_client(name="Client1", server_id=sample_server.id)
        c2 = cm.create_client(name="Client2", server_id=sample_server.id)

        assert c1 is not None
        assert c2 is not None
        assert c1.ip_index != c2.ip_index


# ============================================================================
# SERVER MANAGER TESTS
# ============================================================================

class TestServerManager:
    """Tests for ServerManager"""

    def test_get_server(self, db_session, sample_server):
        sm = ServerManager(db_session)
        server = sm.get_server(sample_server.id)
        assert server is not None
        assert server.name == "wg0"

    def test_get_server_by_name(self, db_session, sample_server):
        sm = ServerManager(db_session)
        server = sm.get_server_by_name("wg0")
        assert server is not None
        assert server.id == sample_server.id

    def test_get_server_not_found(self, db_session):
        sm = ServerManager(db_session)
        server = sm.get_server(9999)
        assert server is None

    def test_get_all_servers(self, db_session, sample_server):
        sm = ServerManager(db_session)
        servers = sm.get_all_servers()
        assert len(servers) == 1

    def test_get_all_servers_filters_by_lifecycle_status(self, db_session, sample_server):
        sample_server.lifecycle_status = "failed"
        db_session.commit()

        sm = ServerManager(db_session)
        servers = sm.get_all_servers(include_offline=False)

        assert servers == []

    def test_create_server(self, db_session):
        sm = ServerManager(db_session)
        server = sm.create_server(
            name="wg1",
            endpoint="1.2.3.4:51820",
            public_key="FakeServerPubKey1234567890123456789012=",
            private_key="FakeServerPrivKey123456789012345678901=",
            interface="wg1",
            listen_port=51820,
            address_pool_ipv4="10.0.1.0/24",
            dns="1.1.1.1",
        )
        assert server is not None
        assert server.name == "wg1"
        assert server.listen_port == 51820
        assert server.lifecycle_status == "offline"
        assert server.is_active is True

    def test_transition_status_keeps_legacy_and_lifecycle_in_sync(self, db_session, sample_server):
        sm = ServerManager(db_session)
        sm._transition_status(sample_server, ServerStatus.ERROR, "test")
        db_session.commit()
        db_session.refresh(sample_server)
        assert sample_server.status == ServerStatus.ERROR
        assert sample_server.lifecycle_status == "failed"

    def test_update_server_status_uses_transition_mapping(self, db_session, sample_server):
        sm = ServerManager(db_session)
        updated = sm.update_server(sample_server.id, status=ServerStatus.MAINTENANCE)
        assert updated is not None
        assert updated.status == ServerStatus.MAINTENANCE
        assert updated.lifecycle_status == "degraded"

    @pytest.mark.skip(reason="Hysteria2 is a paid plugin (extra-protocols) extracted from open core")
    def test_create_hysteria2_server_persists_proxy_auth_password(self, db_session):
        sm = ServerManager(db_session)
        server = sm.create_server(
            name="hy2-1",
            endpoint="1.2.3.4:8443",
            public_key="0" * 44,
            private_key="0" * 44,
            interface="proxy-hys0",
            listen_port=8443,
            server_type="hysteria2",
            server_category="proxy",
            proxy_config_path="/etc/hysteria/config.yaml",
            proxy_service_name="hysteria-server",
            proxy_auth_password="server-shared-password",
        )
        assert server is not None
        assert server.server_type == "hysteria2"
        assert server.server_category == "proxy"
        assert server.proxy_auth_password == "server-shared-password"

    def test_delete_server_with_clients_requires_force(self, db_session, sample_server, sample_client):
        sm = ServerManager(db_session)
        result = sm.delete_server(sample_server.id)
        assert result is False

        server = sm.get_server(sample_server.id)
        assert server is not None

    def test_delete_server(self, db_session, sample_server):
        sm = ServerManager(db_session)
        wg = MagicMock()
        wg.is_interface_up.return_value = False
        wg.close.return_value = None

        sm._get_wg = MagicMock(return_value=wg)
        result = sm.delete_server(sample_server.id)
        assert result is True

        server = sm.get_server(sample_server.id)
        assert server is None
        wg.close.assert_called_once()

    def test_get_server_stats(self, db_session, sample_server, sample_client):
        sm = ServerManager(db_session)
        stats = sm.get_server_stats(sample_server.id)
        assert stats is not None
        assert stats["total_clients"] == 1
        assert stats["active_clients"] == 1
        assert stats["max_clients"] == 250


# ============================================================================
# TRAFFIC MANAGER TESTS
# ============================================================================

class TestTrafficManager:
    """Tests for TrafficManager"""

    def _make_tm(self, db_session, mock_wg_manager):
        # Ensure get_peer_transfer returns (rx, tx) tuple
        mock_wg_manager.get_peer_transfer.return_value = (0, 0)
        return TrafficManager(db_session, mock_wg_manager)

    def test_format_bytes(self, db_session, mock_wg_manager):
        tm = self._make_tm(db_session, mock_wg_manager)
        assert tm.format_bytes(0) == "0 B"
        assert tm.format_bytes(1024) == "1 KB"
        assert tm.format_bytes(1024 * 1024) == "1.00 MB"
        assert tm.format_bytes(1024 * 1024 * 1024) == "1.00 GB"
        assert tm.format_bytes(1024 * 1024 * 1024 * 1024) == "1.00 TB"


    def test_parse_size_to_mb(self, db_session, mock_wg_manager):
        tm = self._make_tm(db_session, mock_wg_manager)
        assert tm.parse_size_to_mb("1GB") == 1024
        assert tm.parse_size_to_mb("500MB") == 500
        assert tm.parse_size_to_mb("1TB") == 1024 * 1024

    def test_set_traffic_limit(self, db_session, sample_client, mock_wg_manager):
        tm = self._make_tm(db_session, mock_wg_manager)
        result = tm.set_traffic_limit(sample_client.id, 5120)
        assert result is True

        db_session.refresh(sample_client)
        assert sample_client.traffic_limit_mb == 5120

    def test_remove_traffic_limit(self, db_session, sample_client, mock_wg_manager):
        tm = self._make_tm(db_session, mock_wg_manager)
        tm.set_traffic_limit(sample_client.id, 5120)
        tm.set_traffic_limit(sample_client.id, 0)

        db_session.refresh(sample_client)
        assert sample_client.traffic_limit_mb is None or sample_client.traffic_limit_mb == 0

    def test_reset_traffic_counter(self, db_session, sample_client, mock_wg_manager):
        sample_client.traffic_used_rx = 1000000
        sample_client.traffic_used_tx = 500000
        db_session.commit()

        tm = self._make_tm(db_session, mock_wg_manager)
        result = tm.reset_traffic_counter(sample_client.id)
        assert result is True

    def test_restore_all_bandwidth_limits_skips_proxy_servers(self, db_session, mock_wg_manager):
        proxy = Server(
            name="ProxyServer",
            interface="proxy-hys0",
            endpoint="127.0.0.1",
            listen_port=8443,
            public_key="proxy",
            private_key="proxy",
            address_pool_ipv4="10.0.0.0/24",
            dns="1.1.1.1",
            mtu=1420,
            persistent_keepalive=25,
            config_path="/etc/hysteria/config.yaml",
            status=ServerStatus.ONLINE,
            server_type="hysteria2",
            server_category="proxy",
            proxy_service_name="hysteria-server",
        )
        db_session.add(proxy)
        db_session.commit()

        tm = self._make_tm(db_session, mock_wg_manager)
        tm._sync_bandwidth_for_server = MagicMock(side_effect=AssertionError("proxy server should be skipped"))

        assert tm.restore_all_bandwidth_limits() == 0

    def test_sync_bandwidth_for_proxy_server_returns_zero(self, db_session, mock_wg_manager):
        proxy = Server(
            name="ProxyServer",
            interface="proxy-hys0",
            endpoint="127.0.0.1",
            listen_port=8443,
            public_key="proxy",
            private_key="proxy",
            address_pool_ipv4="10.0.0.0/24",
            dns="1.1.1.1",
            mtu=1420,
            persistent_keepalive=25,
            config_path="/etc/hysteria/config.yaml",
            status=ServerStatus.ONLINE,
            server_type="hysteria2",
            server_category="proxy",
            proxy_service_name="hysteria-server",
        )
        db_session.add(proxy)
        db_session.commit()

        tm = self._make_tm(db_session, mock_wg_manager)

        assert tm._sync_bandwidth_for_server(proxy) == 0


class TestSubscriptionManager:
    def test_complete_payment_adds_referral_reward_without_trial_status(self, db_session):
        manager = SubscriptionManager(db_session)

        plan = SubscriptionPlan(
            tier="basic",
            name="Basic",
            max_devices=1,
            traffic_limit_gb=50,
            bandwidth_limit_mbps=100,
            price_monthly_usd=9.99,
            is_active=True,
            is_visible=True,
        )
        db_session.add(plan)
        db_session.commit()

        referrer = ClientUser(
            email="referrer@example.com",
            password_hash="hash",
            username="referrer",
            email_verified=True,
        )
        referred = ClientUser(
            email="referred@example.com",
            password_hash="hash",
            username="referred",
            email_verified=True,
            referred_by=referrer,
        )
        db_session.add_all([referrer, referred])
        db_session.commit()

        base_expiry = datetime.now() + timedelta(days=3)
        referrer_sub = ClientPortalSubscription(
            user_id=referrer.id,
            tier="basic",
            status=SubscriptionStatus.ACTIVE,
            max_devices=1,
            traffic_limit_gb=50,
            bandwidth_limit_mbps=100,
            price_monthly_usd=9.99,
            expiry_date=base_expiry,
        )
        db_session.add(referrer_sub)
        db_session.add(
            ClientPortalPayment(
                user_id=referred.id,
                invoice_id="inv-referral-1",
                amount_usd=9.99,
                payment_method=PaymentMethod.USDT_TRC20,
                subscription_tier="basic",
                duration_days=30,
                provider_name="test",
                status="pending",
            )
        )
        db_session.commit()

        assert manager.complete_payment("inv-referral-1", sync_wg=False) is True

        db_session.refresh(referrer_sub)
        assert referrer_sub.expiry_date > base_expiry + timedelta(days=6)


# ============================================================================
# TIMER MANAGER TESTS
# ============================================================================

class TestTimerManager:
    """Tests for TimerManager"""

    def test_set_expiry(self, db_session, sample_client, mock_wg_manager):
        tm = TimerManager(db_session, mock_wg_manager)
        result = tm.set_expiry(sample_client.id, days=30)
        assert result is True

        db_session.refresh(sample_client)
        assert sample_client.expiry_date is not None
        assert sample_client.expiry_date > datetime.now()

    def test_remove_expiry(self, db_session, sample_client, mock_wg_manager):
        tm = TimerManager(db_session, mock_wg_manager)
        tm.set_expiry(sample_client.id, days=30)
        tm.set_expiry(sample_client.id, days=0)

        db_session.refresh(sample_client)
        assert sample_client.expiry_date is None

    def test_get_expiry_info(self, db_session, sample_client, mock_wg_manager):
        tm = TimerManager(db_session, mock_wg_manager)
        tm.set_expiry(sample_client.id, days=7)

        info = tm.get_expiry_info(sample_client.id)
        assert info is not None
        assert info["days_left"] <= 7
        assert info["days_left"] >= 6
        assert info["is_expired"] is False

    def test_expired_client_detection(self, db_session, sample_client, mock_wg_manager):
        from datetime import timezone
        tm = TimerManager(db_session, mock_wg_manager)
        sample_client.expiry_date = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        info = tm.get_expiry_info(sample_client.id)
        assert info["is_expired"] is True

    def test_get_expiring_soon(self, db_session, sample_client, mock_wg_manager):
        tm = TimerManager(db_session, mock_wg_manager)
        sample_client.expiry_date = datetime.now() + timedelta(days=3)
        db_session.commit()

        # within_days is the correct parameter name
        expiring = tm.get_expiring_soon(within_days=7)
        assert len(expiring) == 1

        expiring_1d = tm.get_expiring_soon(within_days=1)
        assert len(expiring_1d) == 0

    def test_no_expiry_info(self, db_session, sample_client, mock_wg_manager):
        tm = TimerManager(db_session, mock_wg_manager)
        info = tm.get_expiry_info(sample_client.id)
        assert info is not None
        assert info["display_text"] == "No expiry"


# ============================================================================
# MANAGEMENT CORE TESTS
# ============================================================================

class TestManagementCore:
    """Tests for ManagementCore - central coordinator"""

    def _make_core(self, db_session, mock_wg_manager):
        # Ensure get_peer_transfer returns tuple not empty dict
        mock_wg_manager.get_peer_transfer.return_value = (0, 0)

        core = ManagementCore(db_session)
        core.wg_manager = mock_wg_manager
        core.clients.wg_manager = mock_wg_manager
        core.clients._get_wg = MagicMock(return_value=mock_wg_manager)
        core.traffic.wg_manager = mock_wg_manager
        core.timers.wg_manager = mock_wg_manager
        return core

    def test_create_client_via_core(self, db_session, sample_server, mock_wg_manager):
        core = self._make_core(db_session, mock_wg_manager)
        client = core.create_client(name="CorePhone", server_id=sample_server.id)
        assert client is not None
        assert client.name == "CorePhone"

    def test_get_system_status(self, db_session, sample_server, sample_client, mock_wg_manager):
        core = self._make_core(db_session, mock_wg_manager)
        status = core.get_system_status()

        assert "servers" in status
        assert "clients" in status
        assert "traffic" in status
        assert "expiry" in status
        assert status["servers"]["total"] == 1
        assert status["clients"]["total"] == 1

    def test_get_client_full_info(self, db_session, sample_server, sample_client, mock_wg_manager):
        core = self._make_core(db_session, mock_wg_manager)
        info = core.get_client_full_info(sample_client.id)
        assert info is not None
        assert info["name"] == "TestClient"
        assert info["enabled"] is True
        assert "traffic" in info
        assert "expiry" in info

    def test_audit_logging(self, db_session, sample_server, mock_wg_manager):
        core = self._make_core(db_session, mock_wg_manager)
        client = core.create_client(name="AuditTest", server_id=sample_server.id)

        logs = db_session.query(AuditLog).all()
        assert len(logs) >= 1
        # AuditLog uses target_name, not target
        assert any("AuditTest" in (log.target_name or "") for log in logs)
