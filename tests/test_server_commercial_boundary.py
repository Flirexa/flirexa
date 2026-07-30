"""Regression tests for the ServerManager commercial-runtime extraction."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from src.modules import server_commercial_adapter, server_proxy_adapter


def test_shared_server_manager_does_not_import_protected_runtime_classes():
    source = Path("src/core/server_manager.py").read_text(encoding="utf-8")

    protected_symbols = (
        "AgentBootstrap",
        "RemoteServerAdapter",
        "Hysteria2Manager",
        "TUICManager",
        "VlessRealityManager",
        ".agent_bootstrap",
        ".remote_adapter",
        ".hysteria2",
        ".tuic",
        ".vless_reality",
    )
    assert all(symbol not in source for symbol in protected_symbols)


def test_proxy_defaults_preserve_local_wireguard_and_amnezia_paths():
    assert server_proxy_adapter.normalize_create_options(
        server_type="wireguard",
        server_category=None,
        config_path=None,
        proxy_config_path=None,
        interface="wg7",
    ) == (False, "vpn", "/etc/wireguard/wg7.conf")

    assert server_proxy_adapter.normalize_create_options(
        server_type="amneziawg",
        server_category=None,
        config_path=None,
        proxy_config_path=None,
        interface="awg3",
    ) == (False, "vpn", "/etc/amnezia/amneziawg/awg3.conf")


def test_proxy_cleanup_keeps_historical_best_effort_delete(monkeypatch):
    runtime = Mock()
    runtime.purge_service.side_effect = RuntimeError("remote unavailable")
    monkeypatch.setattr(server_proxy_adapter, "get_proxy_manager", lambda server: runtime)

    server = SimpleNamespace(name="remote-proxy")
    assert server_proxy_adapter.cleanup_server_runtime(server, force=False) is True
    runtime.close.assert_called_once_with()


def test_remote_classifier_covers_ssh_agent_and_mikrotik_modes():
    assert not server_commercial_adapter.is_remote_server(
        SimpleNamespace(ssh_host=None, agent_mode="local")
    )
    assert server_commercial_adapter.is_remote_server(
        SimpleNamespace(ssh_host="203.0.113.10", agent_mode="ssh")
    )
    assert server_commercial_adapter.is_remote_server(
        SimpleNamespace(ssh_host=None, agent_mode="agent")
    )
    assert server_commercial_adapter.is_remote_server(
        SimpleNamespace(ssh_host=None, agent_mode="mikrotik")
    )
