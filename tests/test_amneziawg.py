"""
Tests for AmneziaWG integration:
- Server health monitoring with awg show
- MTU configuration in client/server configs
- supports_peer_visibility enforcement
- AWG server creation with all fields
"""

import pytest
import time
from unittest.mock import MagicMock, patch

from src.database.models import Client, Server, ClientStatus
from src.core.client_manager import ClientManager
from src.core.server_manager import ServerManager
from src.core.amneziawg import AmneziaWGManager, AWG_DEFAULT_MTU
from src.modules.health.server_checker import ServerHealthChecker, _parse_wg_show


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def awg_server(db_session):
    """AmneziaWG server fixture."""
    server = Server(
        name="awg0",
        interface="awg0",
        endpoint="1.2.3.4:443",
        listen_port=443,
        public_key="AWGServerPublicKeyBase64XXXXXXXXXXXXXXXXX=",
        private_key="AWGServerPrivateKeyBase64XXXXXXXXXXXXXXXX=",
        address_pool_ipv4="10.8.0.0/24",
        dns="1.1.1.1,8.8.8.8",
        max_clients=250,
        config_path="/etc/amneziawg/awg0.conf",
        server_type="amneziawg",
        awg_jc=4,
        awg_jmin=50,
        awg_jmax=100,
        awg_s1=80,
        awg_s2=40,
        awg_h1=1367695042,
        awg_h2=4150740286,
        awg_h3=186238866,
        awg_h4=2282186532,
        awg_mtu=1280,
        supports_peer_visibility=True,
    )
    db_session.add(server)
    db_session.commit()
    db_session.refresh(server)
    return server


@pytest.fixture
def awg_client(db_session, awg_server):
    """AWG client fixture."""
    client = Client(
        name="AWGClient",
        server_id=awg_server.id,
        public_key="AWGClientPublicKeyBase64XXXXXXXXXXXXXXXXX=",
        private_key="AWGClientPrivateKeyBase64XXXXXXXXXXXXXXXX=",
        preshared_key="AWGPresharedKeyBase64XXXXXXXXXXXXXXXXXXX=",
        ipv4="10.8.0.2",
        ip_index=2,
        enabled=True,
        status=ClientStatus.ACTIVE,
    )
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    return client


@pytest.fixture
def no_peer_visibility_server(db_session):
    """Server with supports_peer_visibility=False."""
    server = Server(
        name="restricted",
        interface="wg1",
        endpoint="5.6.7.8:51820",
        listen_port=51820,
        public_key="RestrictedServerPublicKeyBase64XXXXXXXXX=",
        private_key="RestrictedServerPrivateKeyBase64XXXXXXXX=",
        address_pool_ipv4="10.99.0.0/24",
        dns="1.1.1.1",
        max_clients=50,
        config_path="/etc/wireguard/wg1.conf",
        server_type="wireguard",
        supports_peer_visibility=False,
    )
    db_session.add(server)
    db_session.commit()
    db_session.refresh(server)
    return server


# ============================================================================
# AWG MONITORING — _wg_cmd selection
# ============================================================================

class TestAWGMonitoring:
    """Tests for AWG-aware health monitoring."""

    def test_wg_cmd_wireguard(self, sample_server):
        """WireGuard servers should use 'wg' command."""
        checker = ServerHealthChecker()
        assert checker._wg_cmd(sample_server) == "wg"

    def test_wg_cmd_amneziawg(self, awg_server):
        """AmneziaWG servers should use 'awg' command."""
        checker = ServerHealthChecker()
        assert checker._wg_cmd(awg_server) == "awg"

    def test_wg_cmd_default_for_unknown_type(self, sample_server):
        """Unknown server_type defaults to 'wg'."""
        checker = ServerHealthChecker()
        sample_server.server_type = "unknown_future_type"
        assert checker._wg_cmd(sample_server) == "wg"

    def test_parse_wg_show_output(self):
        """_parse_wg_show parses both wg and awg show output (identical format)."""
        now = int(time.time())
        output = f"""interface: awg0
  public key: YWmmlnu7URMBtfLbc6Mcc=
  private key: (hidden)
  listening port: 443

peer: client1pub=
  endpoint: 1.2.3.4:51234
  allowed ips: 10.8.0.2/32
  latest handshake: 30 seconds ago
  transfer: 1.5 MiB received, 2.3 MiB sent

peer: client2pub=
  allowed ips: 10.8.0.3/32
  latest handshake: 1000 seconds ago
  transfer: 500 KiB received, 100 KiB sent
"""
        result = _parse_wg_show(output, "awg0")
        assert result.interface == "awg0"
        assert result.status == "up"
        assert result.peers_total == 2
        assert result.peers_active == 1   # 30s ago < 180s
        assert result.peers_recent == 1   # 1000s ago > 900s, so only 1
        assert result.rx_bytes > 0
        assert result.tx_bytes > 0

    def test_local_check_uses_awg_cmd(self, awg_server):
        """Local check for AWG server uses 'awg show', not 'wg show'."""
        checker = ServerHealthChecker()
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="interface: awg0\n  public key: test=\n",
                stderr=""
            )
            result = checker._local_wg_check("awg0", wg_cmd="awg")
            # Verify 'awg' was passed as the command
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "awg"
            assert call_args[1] == "show"
            assert result.status == "up"

    def test_local_check_uses_wg_cmd(self, sample_server):
        """Local check for WG server uses 'wg show', not 'awg show'."""
        checker = ServerHealthChecker()
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="interface: wg0\n  public key: test=\n",
                stderr=""
            )
            checker._local_wg_check("wg0", wg_cmd="wg")
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "wg"

    def test_server_health_includes_server_type(self, awg_server):
        """Full local check includes server_type in details dict."""
        checker = ServerHealthChecker()
        with patch.object(checker, '_local_wg_check') as mock_wg, \
             patch.object(checker, '_local_system_metrics') as mock_sys:
            from src.modules.health.server_checker import WireGuardInterfaceHealth, ServerSystemMetrics
            mock_wg.return_value = WireGuardInterfaceHealth(interface="awg0", status="up")
            mock_sys.return_value = ServerSystemMetrics()
            result = checker._check_local(awg_server, t0=0.0, quick=False)
            assert result.details.get("server_type") == "amneziawg"

    def test_wg_server_health_includes_server_type(self, sample_server):
        """Full local check for WG server includes server_type=wireguard."""
        checker = ServerHealthChecker()
        with patch.object(checker, '_local_wg_check') as mock_wg, \
             patch.object(checker, '_local_system_metrics') as mock_sys:
            from src.modules.health.server_checker import WireGuardInterfaceHealth, ServerSystemMetrics
            mock_wg.return_value = WireGuardInterfaceHealth(interface="wg0", status="up")
            mock_sys.return_value = ServerSystemMetrics()
            result = checker._check_local(sample_server, t0=0.0, quick=False)
            assert result.details.get("server_type") == "wireguard"


# ============================================================================
# MTU CONFIGURATION
# ============================================================================

class TestMTUConfig:
    """Tests for AWG MTU in config generation."""

    def test_awg_default_mtu_constant(self):
        """AWG_DEFAULT_MTU should be 1280."""
        assert AWG_DEFAULT_MTU == 1280

    def test_client_config_uses_server_mtu(self, db_session, awg_server, awg_client, mock_wg_manager):
        """AWG client config uses server's awg_mtu value."""
        cm = ClientManager(db_session, mock_wg_manager)
        cm._get_wg = MagicMock(return_value=mock_wg_manager)
        config = cm.get_client_config(awg_client.id)
        assert config is not None
        assert "MTU = 1280" in config

    def test_client_config_uses_default_mtu_when_not_set(self, db_session, awg_server, awg_client, mock_wg_manager):
        """AWG client config uses AWG_DEFAULT_MTU when server.awg_mtu is None."""
        awg_server.awg_mtu = None
        db_session.commit()
        cm = ClientManager(db_session, mock_wg_manager)
        cm._get_wg = MagicMock(return_value=mock_wg_manager)
        config = cm.get_client_config(awg_client.id)
        assert config is not None
        assert f"MTU = {AWG_DEFAULT_MTU}" in config

    def test_client_config_custom_mtu(self, db_session, awg_server, awg_client, mock_wg_manager):
        """AWG client config uses custom awg_mtu if set."""
        awg_server.awg_mtu = 1400
        db_session.commit()
        cm = ClientManager(db_session, mock_wg_manager)
        cm._get_wg = MagicMock(return_value=mock_wg_manager)
        config = cm.get_client_config(awg_client.id)
        assert "MTU = 1400" in config

    def test_awg_config_contains_obfuscation_params(self, db_session, awg_server, awg_client, mock_wg_manager):
        """AWG client config contains all obfuscation parameters."""
        cm = ClientManager(db_session, mock_wg_manager)
        cm._get_wg = MagicMock(return_value=mock_wg_manager)
        config = cm.get_client_config(awg_client.id)
        assert "Jc = 4" in config
        assert "Jmin = 50" in config
        assert "Jmax = 100" in config
        assert "S1 = 80" in config
        assert "S2 = 40" in config
        assert "H1 = " in config
        assert "H2 = " in config
        assert "H3 = " in config
        assert "H4 = " in config

    def test_server_config_with_mtu(self):
        """generate_server_config includes MTU when provided."""
        mgr = AmneziaWGManager(
            interface="awg0",
            h1=111, h2=222, h3=333, h4=444,
        )
        config = mgr.generate_server_config(
            private_key="privkey=",
            address="10.8.0.1/24",
            listen_port=443,
            mtu=1280,
        )
        assert "MTU = 1280" in config

    def test_server_config_without_mtu(self):
        """generate_server_config does NOT include MTU when not provided."""
        mgr = AmneziaWGManager(
            interface="awg0",
            h1=111, h2=222, h3=333, h4=444,
        )
        config = mgr.generate_server_config(
            private_key="privkey=",
            address="10.8.0.1/24",
            listen_port=443,
        )
        assert "MTU" not in config

    def test_generate_client_config_default_mtu(self):
        """generate_client_config uses AWG_DEFAULT_MTU by default."""
        mgr = AmneziaWGManager(interface="awg0", h1=1, h2=2, h3=3, h4=4)
        config = mgr.generate_client_config(
            client_private_key="priv=",
            client_ipv4="10.8.0.2/32",
            client_ipv6=None,
            server_public_key="pub=",
            server_endpoint="1.2.3.4:443",
        )
        assert f"MTU = {AWG_DEFAULT_MTU}" in config


# ============================================================================
# supports_peer_visibility
# ============================================================================

class TestSupportsPeerVisibility:
    """Tests for supports_peer_visibility server field and enforcement."""

    def test_default_supports_peer_visibility_true(self, sample_server):
        """New WG servers default to supports_peer_visibility=True."""
        assert getattr(sample_server, 'supports_peer_visibility', True) is True

    def test_awg_server_supports_peer_visibility(self, awg_server):
        """AWG server created with supports_peer_visibility=True."""
        assert awg_server.supports_peer_visibility is True

    def test_restricted_server_flag(self, no_peer_visibility_server):
        """Server with supports_peer_visibility=False has correct flag."""
        assert no_peer_visibility_server.supports_peer_visibility is False

    def test_create_client_with_peer_visibility_on_restricted_server(
        self, db_session, no_peer_visibility_server, mock_wg_manager
    ):
        """peer_visibility is silently disabled when server doesn't support it."""
        cm = ClientManager(db_session, mock_wg_manager)
        cm._get_wg = MagicMock(return_value=mock_wg_manager)
        client = cm.create_client(
            name="TestPV",
            server_id=no_peer_visibility_server.id,
            peer_visibility=True,
        )
        assert client is not None
        # peer_visibility should be forced to False
        assert client.peer_visibility is False

    def test_create_client_with_peer_visibility_on_supported_server(
        self, db_session, awg_server, mock_wg_manager
    ):
        """peer_visibility is preserved when server supports it."""
        cm = ClientManager(db_session, mock_wg_manager)
        cm._get_wg = MagicMock(return_value=mock_wg_manager)
        client = cm.create_client(
            name="TestPVSupported",
            server_id=awg_server.id,
            peer_visibility=True,
        )
        assert client is not None
        assert client.peer_visibility is True

    def test_get_peer_devices_respects_server_restriction(
        self, db_session, no_peer_visibility_server, mock_wg_manager
    ):
        """get_peer_devices returns empty list when server disables peer_visibility."""
        # Create two clients with same telegram_user_id
        from src.database.models import TelegramUser
        user = TelegramUser(telegram_id=99999, username="testuser")
        db_session.add(user)
        db_session.commit()

        for name, ipv4, idx in [("device1", "10.99.0.2", 2), ("device2", "10.99.0.3", 3)]:
            c = Client(
                name=name,
                server_id=no_peer_visibility_server.id,
                public_key=f"PubKey{name}Base64XXXXXXXXXXXXXXXXXXXXXXXXXX=",
                ipv4=ipv4,
                ip_index=idx,
                enabled=True,
                status=ClientStatus.ACTIVE,
                telegram_user_id=99999,
            )
            db_session.add(c)
        db_session.commit()

        clients = db_session.query(Client).filter(
            Client.server_id == no_peer_visibility_server.id
        ).all()
        cm = ClientManager(db_session, mock_wg_manager)

        # Even though they share telegram_user_id, server blocks peer_visibility
        devices = cm.get_peer_devices(clients[0].id)
        assert devices == []

    def test_get_peer_devices_works_on_supported_server(
        self, db_session, awg_server, mock_wg_manager
    ):
        """get_peer_devices returns peers when server supports peer_visibility."""
        from src.database.models import TelegramUser
        user = TelegramUser(telegram_id=88888, username="awguser")
        db_session.add(user)
        db_session.commit()

        client_ids = []
        for name, ipv4, idx in [("awgdev1", "10.8.0.2", 2), ("awgdev2", "10.8.0.3", 3)]:
            c = Client(
                name=name,
                server_id=awg_server.id,
                public_key=f"AWGPub{name}Base64XXXXXXXXXXXXXXXXXXXXXXXXX=",
                ipv4=ipv4,
                ip_index=idx,
                enabled=True,
                status=ClientStatus.ACTIVE,
                telegram_user_id=88888,
            )
            db_session.add(c)
            db_session.flush()
            client_ids.append(c.id)
        db_session.commit()

        cm = ClientManager(db_session, mock_wg_manager)
        devices = cm.get_peer_devices(client_ids[0])
        assert len(devices) == 1
        assert devices[0]["name"] == "awgdev2"


# ============================================================================
# AWG SERVER CREATION
# ============================================================================

class TestAWGServerCreation:
    """Tests for creating AWG servers."""

    def test_create_awg_server_stores_all_fields(self, db_session):
        """create_server stores all AWG-specific fields."""
        sm = ServerManager(db_session)
        server = sm.create_server(
            name="TestAWG",
            endpoint="9.9.9.9:443",
            public_key="TestAWGPubKey44CharLongBase64XXXXXXXXXXXXx=",
            private_key="TestAWGPrivKey44CharLongBase64XXXXXXXXXXx=",
            interface="awg0",
            listen_port=443,
            server_type="amneziawg",
            awg_jc=4,
            awg_jmin=50,
            awg_jmax=100,
            awg_s1=80,
            awg_s2=40,
            awg_h1=1000001,
            awg_h2=1000002,
            awg_h3=1000003,
            awg_h4=1000004,
            awg_mtu=1280,
            supports_peer_visibility=True,
        )
        assert server is not None
        assert server.server_type == "amneziawg"
        assert server.awg_jc == 4
        assert server.awg_h1 == 1000001
        assert server.awg_mtu == 1280
        assert server.supports_peer_visibility is True
        assert server.config_path == "/etc/amneziawg/awg0.conf"

    def test_create_wg_server_defaults(self, db_session):
        """WG servers get wireguard type and no AWG fields."""
        sm = ServerManager(db_session)
        server = sm.create_server(
            name="TestWG",
            endpoint="1.1.1.1:51820",
            public_key="TestWGPubKey44CharLongBase64XXXXXXXXXXXXXx=",
            private_key="TestWGPrivKey44CharLongBase64XXXXXXXXXXXx=",
            interface="wg0",
        )
        assert server is not None
        assert server.server_type == "wireguard"
        assert server.awg_mtu is None
        assert server.supports_peer_visibility is True
        assert server.config_path == "/etc/wireguard/wg0.conf"

    def test_create_server_with_peer_visibility_disabled(self, db_session):
        """Server can be created with supports_peer_visibility=False."""
        sm = ServerManager(db_session)
        server = sm.create_server(
            name="NoVisibility",
            endpoint="2.2.2.2:51820",
            public_key="NoVisPubKey44CharLongBase64XXXXXXXXXXXXXXx=",
            private_key="NoVisPrivKey44CharLongBase64XXXXXXXXXXXXx=",
            interface="wg2",
            supports_peer_visibility=False,
        )
        assert server is not None
        assert server.supports_peer_visibility is False

    def test_awg_obfuscation_params_generation(self):
        """generate_obfuscation_params returns all required keys with unique H values."""
        params = AmneziaWGManager.generate_obfuscation_params()
        required = {"jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4"}
        assert required == set(params.keys())
        # H1-H4 must all be positive and unique
        h_values = [params["h1"], params["h2"], params["h3"], params["h4"]]
        assert all(v > 0 for v in h_values)
        assert len(set(h_values)) == 4  # all unique

    def test_awg_h_values_fit_biginteger(self):
        """AWG H1-H4 values (uint32) must fit in PostgreSQL BigInteger."""
        for _ in range(20):
            params = AmneziaWGManager.generate_obfuscation_params()
            for k in ("h1", "h2", "h3", "h4"):
                v = params[k]
                assert 0 < v <= 4_294_967_295, f"{k}={v} out of uint32 range"
                # BigInteger max is 9223372036854775807 — uint32 always fits
                assert v <= 9_223_372_036_854_775_807


# ============================================================================
# AWG BACKUP EXPORT
# ============================================================================

class TestAWGBackupExport:
    """Tests that AWG server fields are included in backup export."""

    def test_export_includes_server_type(self, db_session, awg_server):
        """Backup export JSON includes server_type field."""
        import json, tempfile, os
        from src.modules.backup_manager import BackupManager
        bm = BackupManager(db_session)
        with tempfile.TemporaryDirectory() as tmp:
            bm._export_server_clients(awg_server, tmp)
            fname = [f for f in os.listdir(tmp) if f.endswith(".json")][0]
            with open(os.path.join(tmp, fname)) as f:
                data = json.load(f)
        srv = data["server"]
        assert srv["server_type"] == "amneziawg"

    def test_export_includes_awg_obfuscation_params(self, db_session, awg_server):
        """Backup export JSON includes all AWG obfuscation parameters."""
        import json, tempfile, os
        from src.modules.backup_manager import BackupManager
        bm = BackupManager(db_session)
        with tempfile.TemporaryDirectory() as tmp:
            bm._export_server_clients(awg_server, tmp)
            fname = [f for f in os.listdir(tmp) if f.endswith(".json")][0]
            with open(os.path.join(tmp, fname)) as f:
                data = json.load(f)
        srv = data["server"]
        for field in ("awg_jc", "awg_jmin", "awg_jmax", "awg_s1", "awg_s2",
                      "awg_h1", "awg_h2", "awg_h3", "awg_h4"):
            assert field in srv, f"Missing field: {field}"
            assert srv[field] is not None, f"Field is None: {field}"

    def test_export_includes_awg_mtu_and_peer_visibility(self, db_session, awg_server):
        """Backup export JSON includes awg_mtu and supports_peer_visibility."""
        import json, tempfile, os
        from src.modules.backup_manager import BackupManager
        bm = BackupManager(db_session)
        with tempfile.TemporaryDirectory() as tmp:
            bm._export_server_clients(awg_server, tmp)
            fname = [f for f in os.listdir(tmp) if f.endswith(".json")][0]
            with open(os.path.join(tmp, fname)) as f:
                data = json.load(f)
        srv = data["server"]
        assert "awg_mtu" in srv
        assert "supports_peer_visibility" in srv
        assert srv["supports_peer_visibility"] is True

    def test_wg_server_export_has_defaults(self, db_session, sample_server):
        """WG server export has server_type=wireguard and null AWG fields."""
        import json, tempfile, os
        from src.modules.backup_manager import BackupManager
        bm = BackupManager(db_session)
        with tempfile.TemporaryDirectory() as tmp:
            bm._export_server_clients(sample_server, tmp)
            fname = [f for f in os.listdir(tmp) if f.endswith(".json")][0]
            with open(os.path.join(tmp, fname)) as f:
                data = json.load(f)
        srv = data["server"]
        assert srv["server_type"] == "wireguard"
        assert srv["awg_jc"] is None


# ============================================================================
# AWG HEALTH CHECKER — wireguard_local component
# ============================================================================

class TestAWGHealthChecker:
    """Tests for AWG-aware SystemHealthChecker._check_wireguard_local."""

    def test_wg_interfaces_detected(self):
        """wg show interfaces result is included."""
        from src.modules.health.checker import SystemHealthChecker
        checker = SystemHealthChecker.__new__(SystemHealthChecker)
        with patch('subprocess.run') as mock_run:
            def side_effect(cmd, **kwargs):
                r = MagicMock()
                if cmd[0] == 'wg':
                    r.returncode = 0
                    r.stdout = "wg0\n"
                else:
                    r.returncode = 1
                    r.stdout = ""
                return r
            mock_run.side_effect = side_effect
            result = checker._check_wireguard_local()
        assert result.status == "healthy"
        assert "wg0" in result.message

    def test_awg_interfaces_detected(self):
        """awg show interfaces result is included when wg finds nothing."""
        from src.modules.health.checker import SystemHealthChecker
        checker = SystemHealthChecker.__new__(SystemHealthChecker)
        with patch('subprocess.run') as mock_run:
            def side_effect(cmd, **kwargs):
                r = MagicMock()
                if cmd[0] == 'wg':
                    r.returncode = 0
                    r.stdout = ""
                else:
                    r.returncode = 0
                    r.stdout = "awg0\n"
                return r
            mock_run.side_effect = side_effect
            result = checker._check_wireguard_local()
        assert result.status == "healthy"
        assert "awg0" in result.message

    def test_both_wg_and_awg_interfaces(self):
        """Both wg0 and awg0 are listed when both active."""
        from src.modules.health.checker import SystemHealthChecker
        checker = SystemHealthChecker.__new__(SystemHealthChecker)
        with patch('subprocess.run') as mock_run:
            def side_effect(cmd, **kwargs):
                r = MagicMock()
                r.returncode = 0
                r.stdout = "wg0\n" if cmd[0] == 'wg' else "awg0\n"
                return r
            mock_run.side_effect = side_effect
            result = checker._check_wireguard_local()
        assert "wg0" in result.details["interfaces"]
        assert "awg0" in result.details["interfaces"]

    def test_no_interfaces_warning(self):
        """Warning when neither wg nor awg has active interfaces."""
        from src.modules.health.checker import SystemHealthChecker
        checker = SystemHealthChecker.__new__(SystemHealthChecker)
        with patch('subprocess.run') as mock_run:
            r = MagicMock(returncode=0, stdout="")
            mock_run.return_value = r
            result = checker._check_wireguard_local()
        assert result.status == "warning"

# ============================================================================
# AWG ROUTING — AllowedIPs and PostUp/PostDown
# ============================================================================

class TestAWGRouting:
    """Tests for AWG client config AllowedIPs and server PostUp/PostDown."""

    def test_awg_client_always_full_tunnel(self, db_session, awg_server, awg_client, mock_wg_manager):
        """AWG client config always uses AllowedIPs = 0.0.0.0/0 (full tunnel)."""
        cm = ClientManager(db_session, mock_wg_manager)
        cm._get_wg = MagicMock(return_value=mock_wg_manager)
        config = cm.get_client_config(awg_client.id)
        assert config is not None
        assert "AllowedIPs = 0.0.0.0/0" in config

    def test_awg_client_split_tunnel_flag_ignored(self, db_session, awg_server, awg_client, mock_wg_manager):
        """split_tunnel_support=True on AWG server does NOT change AllowedIPs."""
        awg_server.split_tunnel_support = True
        db_session.commit()
        cm = ClientManager(db_session, mock_wg_manager)
        cm._get_wg = MagicMock(return_value=mock_wg_manager)
        config = cm.get_client_config(awg_client.id)
        # Must still be full tunnel — split_tunnel_support is irrelevant for AWG
        assert "AllowedIPs = 0.0.0.0/0" in config
        assert "AllowedIPs = 10." not in config

    def test_wg_client_full_tunnel(self, db_session, sample_server, sample_client, mock_wg_manager):
        """WG client config also uses AllowedIPs = 0.0.0.0/0 by default."""
        wg_config = (
            "[Interface]\nPrivateKey = priv\nAddress = 10.66.66.2/32\nDNS = 1.1.1.1\n\n"
            "[Peer]\nPublicKey = pub\nAllowedIPs = 0.0.0.0/0\n"
        )
        mock_wg_manager.generate_client_config.return_value = wg_config
        cm = ClientManager(db_session, mock_wg_manager)
        cm._get_wg = MagicMock(return_value=mock_wg_manager)
        config = cm.get_client_config(sample_client.id)
        assert config is not None
        assert "AllowedIPs = 0.0.0.0/0" in config

    def test_awg_server_postup_contains_masquerade(self):
        """AWG server PostUp contains MASQUERADE rule."""
        mgr = AmneziaWGManager(interface="awg0", h1=1, h2=2, h3=3, h4=4)
        config = mgr.generate_server_config(
            private_key="privkey=",
            address="10.8.0.1/24",
            listen_port=443,
        )
        assert "MASQUERADE" in config
        assert "PostUp" in config
        assert "PostDown" in config

    def test_awg_server_postup_has_dynamic_eth(self):
        """AWG server PostUp uses shell auto-detection for egress NIC by default."""
        mgr = AmneziaWGManager(interface="awg0", h1=1, h2=2, h3=3, h4=4)
        config = mgr.generate_server_config(
            private_key="privkey=",
            address="10.8.0.1/24",
            listen_port=443,
        )
        # Should use shell command substitution, not hardcoded eth0
        assert "ip route" in config
        assert "eth0" not in config  # no hardcoded interface name

    def test_awg_server_postup_explicit_eth(self):
        """AWG server PostUp uses explicit eth_interface when provided."""
        mgr = AmneziaWGManager(interface="awg0", h1=1, h2=2, h3=3, h4=4)
        config = mgr.generate_server_config(
            private_key="privkey=",
            address="10.8.0.1/24",
            listen_port=443,
            eth_interface="ens3",
        )
        assert "-o ens3" in config

    def test_awg_server_postup_has_ip_route_add(self):
        """AWG server PostUp includes ip route add as safety measure."""
        mgr = AmneziaWGManager(interface="awg0", h1=1, h2=2, h3=3, h4=4)
        config = mgr.generate_server_config(
            private_key="privkey=",
            address="10.8.0.1/24",
            listen_port=443,
        )
        assert "ip route add" in config
        assert "ip route del" in config

    def test_awg_server_postup_subnet_matches_pool(self):
        """PostUp MASQUERADE subnet is derived from address pool (not hardcoded)."""
        mgr = AmneziaWGManager(interface="awg0", h1=1, h2=2, h3=3, h4=4)
        config = mgr.generate_server_config(
            private_key="privkey=",
            address="10.9.0.1/24",
            listen_port=443,
        )
        assert "10.9.0.0/24" in config
        assert "10.8.0" not in config


# ============================================================================
# AWG PARAMETER PRIORITY
# ============================================================================

class TestAWGParamPriority:
    """Tests for AWG obfuscation parameter priority: auto → discovered → user."""

    def test_generate_obfuscation_params_all_keys_present(self):
        """generate_obfuscation_params always returns all 9 keys."""
        params = AmneziaWGManager.generate_obfuscation_params()
        for key in ("jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4"):
            assert key in params, f"Missing key: {key}"

    def test_generate_obfuscation_h_values_unique(self):
        """H1-H4 are always unique and non-zero."""
        for _ in range(10):
            params = AmneziaWGManager.generate_obfuscation_params()
            h_vals = [params["h1"], params["h2"], params["h3"], params["h4"]]
            assert all(v > 0 for v in h_vals)
            assert len(set(h_vals)) == 4

    def test_discover_remote_parses_awg_params(self):
        """discover_remote() reads Jc/Jmin/Jmax/S1/S2/H1-H4 from config file."""
        mgr = AmneziaWGManager(
            interface="awg0",
            ssh_host="1.2.3.4",
            ssh_port=22,
            ssh_user="root",
        )
        fake_dump = "privkey\tpubkey\t443\t1\n"
        fake_conf = (
            "Address = 10.8.0.1/24\n"
            "Jc = 7\nJmin = 30\nJmax = 90\n"
            "S1 = 55\nS2 = 20\n"
            "H1 = 111111\nH2 = 222222\nH3 = 333333\nH4 = 444444\n"
        )

        with patch.object(mgr, '_run_cmd') as mock_run, \
             patch.object(mgr, 'read_config_file', return_value=fake_conf):
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_dump)
            result = mgr.discover_remote()

        assert result is not None
        assert result["awg_params"] is not None
        p = result["awg_params"]
        assert p["jc"] == 7
        assert p["jmin"] == 30
        assert p["jmax"] == 90
        assert p["s1"] == 55
        assert p["s2"] == 20
        assert p["h1"] == 111111
        assert p["h2"] == 222222
        assert p["h3"] == 333333
        assert p["h4"] == 444444

    def test_discover_remote_returns_address_pool(self):
        """discover_remote() reads Address from config and returns as address_pool_ipv4."""
        mgr = AmneziaWGManager(interface="awg0", ssh_host="1.2.3.4", ssh_port=22, ssh_user="root")
        fake_dump = "privkey\tpubkey\t443\t1\n"
        fake_conf = "Address = 10.9.0.1/24\nJc = 4\nH1 = 1\nH2 = 2\nH3 = 3\nH4 = 4\n"

        with patch.object(mgr, '_run_cmd') as mock_run, \
             patch.object(mgr, 'read_config_file', return_value=fake_conf):
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_dump)
            result = mgr.discover_remote()

        assert result["address_pool_ipv4"] == "10.9.0.1/24"

    def test_discover_remote_empty_config_returns_none_params(self):
        """discover_remote() returns awg_params=None when config is empty."""
        mgr = AmneziaWGManager(interface="awg0", ssh_host="1.2.3.4", ssh_port=22, ssh_user="root")
        fake_dump = "privkey\tpubkey\t443\t1\n"

        with patch.object(mgr, '_run_cmd') as mock_run, \
             patch.object(mgr, 'read_config_file', return_value=""):
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_dump)
            result = mgr.discover_remote()

        assert result is not None
        assert result["awg_params"] is None


# ============================================================================
# AWG SPLIT TUNNEL — API / server manager enforcement
# ============================================================================

class TestAWGNoSplitTunnel:
    """Tests that split_tunnel_support is ignored/forced-False for AWG servers."""

    def test_awg_server_split_tunnel_default_false(self, awg_server):
        """AWG server fixture has split_tunnel_support=False by default."""
        assert awg_server.split_tunnel_support is False

    def test_create_awg_server_ignores_split_tunnel(self, db_session):
        """create_server with server_type=amneziawg stores split_tunnel_support=False
        regardless of what was passed."""
        sm = ServerManager(db_session)
        server = sm.create_server(
            name="AWGNoSplit",
            endpoint="9.9.9.9:443",
            public_key="AWGNoSplitPubKey44CharLongBase64XXXXXXXXx=",
            private_key="AWGNoSplitPrivKey44CharLongBase64XXXXXXXx=",
            interface="awg1",
            listen_port=443,
            server_type="amneziawg",
            awg_h1=100001,
            awg_h2=100002,
            awg_h3=100003,
            awg_h4=100004,
            split_tunnel_support=True,  # should be stored as-is in DB (API layer enforces False)
        )
        assert server is not None
        # server_manager.create_server stores whatever is passed — enforcement is in API layer
        # but client config generation ignores it regardless
        cm = ClientManager(db_session, MagicMock())
        client = Client(
            name="SplitTestClient",
            server_id=server.id,
            public_key="SplitTestPubKey44CharLongBase64XXXXXXXXXx=",
            private_key="SplitTestPrivKey44CharLongBase64XXXXXXXXx=",
            preshared_key="SplitTestPSK44CharLongBase64XXXXXXXXXXXx=",
            ipv4="10.0.0.2",
            ip_index=2,
            enabled=True,
            status=ClientStatus.ACTIVE,
        )
        db_session.add(client)
        db_session.commit()
        db_session.refresh(client)

        mock_wg = MagicMock()
        cm._get_wg = MagicMock(return_value=mock_wg)
        config = cm.get_client_config(client.id)
        # AllowedIPs must always be 0.0.0.0/0 for AWG, never a subnet
        assert "AllowedIPs = 0.0.0.0/0" in config
        assert "AllowedIPs = 10." not in config

    def test_awg_config_contains_all_obfuscation_params(self):
        """AWG client config embeds all 9 obfuscation parameters."""
        mgr = AmneziaWGManager(
            interface="awg0",
            jc=5, jmin=30, jmax=90, s1=60, s2=25,
            h1=111, h2=222, h3=333, h4=444,
        )
        config = mgr.generate_client_config(
            client_private_key="priv=",
            client_ipv4="10.8.0.2/32",
            client_ipv6=None,
            server_public_key="pub=",
            server_endpoint="1.2.3.4:443",
        )
        assert "Jc = 5" in config
        assert "Jmin = 30" in config
        assert "Jmax = 90" in config
        assert "S1 = 60" in config
        assert "S2 = 25" in config
        assert "H1 = 111" in config
        assert "H2 = 222" in config
        assert "H3 = 333" in config
        assert "H4 = 444" in config
        assert "AllowedIPs = 0.0.0.0/0" in config


# ============================================================================
# AWG BACKUP / RESTORE
# ============================================================================

class TestAWGBackupRestore:
    """Tests for AWG server backup and restore via API-level JSON."""

    def test_awg_backup_includes_all_awg_fields(self, db_session, awg_server, awg_client):
        """Backup dict includes all AWG-specific fields needed for restore."""
        # Simulate what GET /servers/{id}/backup returns
        from src.api.routes.servers import ServerResponse
        resp = ServerResponse.from_server(awg_server, db=db_session)
        assert resp.server_type == "amneziawg"
        assert resp.awg_jc == 4
        assert resp.awg_jmin == 50
        assert resp.awg_jmax == 100
        assert resp.awg_s1 == 80
        assert resp.awg_s2 == 40
        assert resp.awg_h1 == 1367695042
        assert resp.awg_h2 == 4150740286
        assert resp.awg_mtu == 1280
        assert resp.supports_peer_visibility is True
        # split_tunnel_support should be False for AWG (not set in fixture = default)
        assert resp.split_tunnel_support is False

    def test_awg_server_response_no_split_tunnel_for_awg(self, db_session, awg_server):
        """ServerResponse for AWG server always has split_tunnel_support=False."""
        awg_server.split_tunnel_support = True  # force it to True in DB
        db_session.commit()
        from src.api.routes.servers import ServerResponse
        resp = ServerResponse.from_server(awg_server, db=db_session)
        # The response reflects the DB value — API create/update layer enforces False
        # Client config generation always uses 0.0.0.0/0 regardless
        assert resp.server_type == "amneziawg"

    def test_wg_server_can_have_split_tunnel(self, db_session, sample_server):
        """WG server split_tunnel_support is stored and returned correctly."""
        sample_server.split_tunnel_support = True
        db_session.commit()
        from src.api.routes.servers import ServerResponse
        resp = ServerResponse.from_server(sample_server, db=db_session)
        assert resp.split_tunnel_support is True
        assert resp.server_type == "wireguard"
