"""
Tests for src/modules/state_reconciler.py

Covers:
  - clean server (no drift)
  - missing peer → auto-reconcile (safe drift)
  - failed reconcile → DRIFTED
  - interface down → DRIFTED
  - connection error → DRIFTED
  - agent unreachable → DRIFTED
  - agent mode with all peers present
  - run_reconciliation skips non-ONLINE servers
  - drift cleared on subsequent clean check
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_server(
    id=1,
    name="test",
    status="online",
    server_type="wireguard",
    agent_mode="ssh",
    agent_url=None,
    agent_api_key=None,
    interface="wg0",
    config_path="/etc/wireguard/wg0.conf",
    address_pool_ipv4="10.66.66.0/24",
    ssh_host="1.2.3.4",
    ssh_port=22,
    ssh_user="root",
    ssh_password=None,
    drift_detected=False,
    drift_details=None,
    drift_detected_at=None,
    last_reconcile_at=None,
    awg_jc=4, awg_jmin=50, awg_jmax=100,
    awg_s1=80, awg_s2=40,
    awg_h1=0, awg_h2=0, awg_h3=0, awg_h4=0,
):
    from src.database.models import ServerStatus
    srv = MagicMock()
    srv.id = id
    srv.name = name
    srv.status = ServerStatus.ONLINE if status == "online" else status
    srv.server_type = server_type
    srv.agent_mode = agent_mode
    srv.agent_url = agent_url
    srv.agent_api_key = agent_api_key
    srv.interface = interface
    srv.config_path = config_path
    srv.address_pool_ipv4 = address_pool_ipv4
    srv.ssh_host = ssh_host
    srv.ssh_port = ssh_port
    srv.ssh_user = ssh_user
    srv.ssh_password = ssh_password
    srv.drift_detected = drift_detected
    srv.drift_details = drift_details
    srv.drift_detected_at = drift_detected_at
    srv.last_reconcile_at = last_reconcile_at
    srv.awg_jc = awg_jc; srv.awg_jmin = awg_jmin; srv.awg_jmax = awg_jmax
    srv.awg_s1 = awg_s1; srv.awg_s2 = awg_s2
    srv.awg_h1 = awg_h1; srv.awg_h2 = awg_h2; srv.awg_h3 = awg_h3; srv.awg_h4 = awg_h4
    return srv


def _make_client(id=1, name="cli1", public_key="PK1", ipv4="10.66.66.2", ipv6=None,
                 preshared_key=None, enabled=True, server_id=1):
    cli = MagicMock()
    cli.id = id
    cli.name = name
    cli.public_key = public_key
    cli.ipv4 = ipv4
    cli.ipv6 = ipv6
    cli.preshared_key = preshared_key
    cli.enabled = enabled
    cli.server_id = server_id
    return cli


def _make_peer(public_key):
    from src.core.wireguard import PeerInfo
    return PeerInfo(public_key=public_key, allowed_ips=[])


def _mock_db(clients=None, disabled_clients=None):
    db = MagicMock()
    q = MagicMock()
    enabled_filter = MagicMock()
    enabled_filter.all.return_value = clients or []
    disabled_filter = MagicMock()
    disabled_filter.all.return_value = disabled_clients or []
    q.filter.side_effect = [enabled_filter, disabled_filter]
    db.query.return_value = q
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReconcileServerClean:
    """Server has all DB peers present — no drift."""

    def test_no_drift_when_all_peers_present(self):
        from src.modules.state_reconciler import reconcile_server

        client = _make_client(public_key="PUBKEY1")
        server = _make_server()
        db = _mock_db(clients=[client])

        mock_wgm = MagicMock()
        mock_wgm.is_interface_up.return_value = True
        mock_wgm.get_all_peers.return_value = [_make_peer("PUBKEY1")]
        mock_wgm.get_interface_info.return_value = {}

        with patch("src.modules.state_reconciler._wg_manager", return_value=mock_wgm):
            result = reconcile_server(server, db)

        assert result["drift_detected"] is False
        assert result["issues"] == []
        assert result["reconciled"] == []
        assert server.drift_detected is False
        assert server.last_reconcile_at is not None


class TestReconcileMissingPeer:
    """A DB peer is missing from live interface — safe drift."""

    def test_missing_peer_is_reconciled(self):
        from src.modules.state_reconciler import reconcile_server

        client = _make_client(public_key="PUBKEY1")
        server = _make_server()
        db = _mock_db(clients=[client])

        mock_wgm = MagicMock()
        mock_wgm.is_interface_up.return_value = True
        mock_wgm.get_all_peers.return_value = []  # peer missing
        mock_wgm.get_interface_info.return_value = {}
        mock_wgm.add_peer.return_value = True

        with patch("src.modules.state_reconciler._wg_manager", return_value=mock_wgm):
            result = reconcile_server(server, db)

        assert result["drift_detected"] is False  # reconcile succeeded → clear drift
        assert len(result["reconciled"]) == 1
        assert "cli1" in result["reconciled"][0]
        mock_wgm.add_peer.assert_called_once()

    def test_failed_reconcile_sets_drifted(self):
        from src.modules.state_reconciler import reconcile_server

        client = _make_client(public_key="PUBKEY1")
        server = _make_server()
        db = _mock_db(clients=[client])

        mock_wgm = MagicMock()
        mock_wgm.is_interface_up.return_value = True
        mock_wgm.get_all_peers.return_value = []  # peer missing
        mock_wgm.get_interface_info.return_value = {}
        mock_wgm.add_peer.return_value = False  # reconcile fails

        with patch("src.modules.state_reconciler._wg_manager", return_value=mock_wgm):
            result = reconcile_server(server, db)

        assert result["drift_detected"] is True
        assert any("reconcile_failed" in i for i in result["issues"])
        assert server.drift_detected is True

    def test_reconcile_adds_ipv6_allowed_ip(self):
        """When client has ipv6, add_peer should include both /32 and /128."""
        from src.modules.state_reconciler import reconcile_server

        client = _make_client(public_key="PK1", ipv4="10.66.66.2", ipv6="fd42::2")
        server = _make_server()
        db = _mock_db(clients=[client])

        mock_wgm = MagicMock()
        mock_wgm.is_interface_up.return_value = True
        mock_wgm.get_all_peers.return_value = []
        mock_wgm.get_interface_info.return_value = {}
        mock_wgm.add_peer.return_value = True

        with patch("src.modules.state_reconciler._wg_manager", return_value=mock_wgm):
            reconcile_server(server, db)

        call_kwargs = mock_wgm.add_peer.call_args
        allowed = call_kwargs.kwargs.get("allowed_ips") or call_kwargs.args[1]
        assert "10.66.66.2/32" in allowed
        assert "fd42::2/128" in allowed


class TestReconcileInterfaceDown:
    """Interface is down — unsafe drift."""

    def test_interface_down_sets_drifted(self):
        from src.modules.state_reconciler import reconcile_server

        server = _make_server()
        db = _mock_db(clients=[])

        mock_wgm = MagicMock()
        mock_wgm.is_interface_up.return_value = False

        with patch("src.modules.state_reconciler._wg_manager", return_value=mock_wgm):
            result = reconcile_server(server, db)

        assert result["drift_detected"] is True
        assert "interface_down" in result["issues"]
        assert server.drift_detected is True
        assert server.drift_detected_at is not None


class TestReconcileConnectionError:
    """SSH connection error — unsafe drift."""

    def test_connection_error_sets_drifted(self):
        from src.modules.state_reconciler import reconcile_server

        server = _make_server()
        db = _mock_db(clients=[])

        with patch("src.modules.state_reconciler._wg_manager",
                   side_effect=Exception("Connection refused")):
            result = reconcile_server(server, db)

        assert result["drift_detected"] is True
        assert any("connection_error" in i for i in result["issues"])


class TestReconcileAgentMode:
    """Agent mode servers."""

    def test_agent_reachable_all_peers_present(self):
        from src.modules.state_reconciler import reconcile_server

        client = _make_client(public_key="PK1")
        server = _make_server(agent_mode="agent", agent_url="http://10.0.0.1:8001")
        db = _mock_db(clients=[client])

        with patch("src.modules.state_reconciler._agent_is_up", return_value=True), \
             patch("src.modules.state_reconciler._agent_get_peers",
                   return_value=[{"public_key": "PK1", "allowed_ips": ["10.66.66.2/32"]}]):
            result = reconcile_server(server, db)

        assert result["drift_detected"] is False

    def test_agent_unreachable_sets_drifted(self):
        from src.modules.state_reconciler import reconcile_server

        server = _make_server(agent_mode="agent", agent_url="http://10.0.0.1:8001")
        db = _mock_db(clients=[])

        with patch("src.modules.state_reconciler._agent_is_up", return_value=False):
            result = reconcile_server(server, db)

        assert result["drift_detected"] is True
        assert "agent_unreachable" in result["issues"]


class TestDriftCleared:
    """Drift is cleared when a subsequent check is clean."""

    def test_drift_cleared_on_clean_check(self):
        from src.modules.state_reconciler import reconcile_server

        client = _make_client(public_key="PK1")
        server = _make_server(drift_detected=True,
                              drift_details='{"issues":["interface_down"]}',
                              drift_detected_at=datetime.now(timezone.utc))
        db = _mock_db(clients=[client])

        mock_wgm = MagicMock()
        mock_wgm.is_interface_up.return_value = True
        mock_wgm.get_all_peers.return_value = [_make_peer("PK1")]
        mock_wgm.get_interface_info.return_value = {}

        with patch("src.modules.state_reconciler._wg_manager", return_value=mock_wgm):
            result = reconcile_server(server, db)

        assert result["drift_detected"] is False
        assert server.drift_detected is False
        assert server.drift_details is None
        assert server.drift_detected_at is None


class TestRunReconciliation:
    """run_reconciliation() batch function."""

    def test_skips_offline_servers(self):
        from src.modules.state_reconciler import run_reconciliation
        from src.database.models import ServerStatus

        offline_server = _make_server(status="offline")
        offline_server.status = ServerStatus.OFFLINE

        mock_db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = []  # no ONLINE servers
        mock_db.query.return_value = q

        with patch("src.modules.state_reconciler.SessionLocal", return_value=mock_db):
            results = run_reconciliation()

        assert results == []

    def test_returns_results_for_online_servers(self):
        from src.modules.state_reconciler import run_reconciliation
        from src.database.models import ServerStatus

        server = _make_server()

        mock_db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [server]
        mock_db.query.return_value = q

        # reconcile_server internals: no clients, interface up, no peers
        mock_wgm = MagicMock()
        mock_wgm.is_interface_up.return_value = True
        mock_wgm.get_all_peers.return_value = []
        mock_wgm.get_interface_info.return_value = {}

        # Second query for clients returns empty
        cli_q = MagicMock()
        cli_enabled = MagicMock()
        cli_enabled.all.return_value = []
        cli_disabled = MagicMock()
        cli_disabled.all.return_value = []
        cli_q.filter.side_effect = [cli_enabled, cli_disabled]
        mock_db.query.side_effect = [
            q,        # outer: select ONLINE servers
            cli_q,    # inner: select clients
            cli_q,    # inner: select disabled clients
        ]

        with patch("src.modules.state_reconciler.SessionLocal", return_value=mock_db), \
             patch("src.modules.state_reconciler._wg_manager", return_value=mock_wgm):
            results = run_reconciliation()

        assert len(results) == 1
        assert results[0]["server_id"] == 1
