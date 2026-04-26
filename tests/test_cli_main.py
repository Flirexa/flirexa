import json
import importlib
from src.cli.main import main
from src.modules.system_status.models import (
    BackupStatusSummary,
    ComponentHealth,
    DatabaseStatusSummary,
    DiskStatusSummary,
    HealthStatusSummary,
    LicenseStatusSummary,
    SystemStatus,
    UpdateStatusSummary,
    UptimeSummary,
)


def _status(result: str = "ok") -> SystemStatus:
    return SystemStatus(
        collected_at="2026-03-27T10:00:00Z",
        result=result,  # type: ignore[arg-type]
        version="1.2.88",
        mode="normal" if result == "ok" else "degraded",
        maintenance_reason=None,
        layout_mode="release-layout",
        install_root="/opt/spongebot",
        current_release="/opt/spongebot/releases/1.2.88",
        services=[],
        license=LicenseStatusSummary(mode="normal", status="ok"),
        update=UpdateStatusSummary(active=False),
        backup=BackupStatusSummary(),
        health=HealthStatusSummary(
            api=ComponentHealth(status="ok"),
            portal=ComponentHealth(status="ok"),
            db=ComponentHealth(status="ok"),
            alembic=ComponentHealth(status="ok"),
            services=ComponentHealth(status="ok"),
            disk=ComponentHealth(status="ok"),
            update_system=ComponentHealth(status="ok"),
            license=ComponentHealth(status="ok"),
        ),
        disk=DiskStatusSummary(),
        uptime=UptimeSummary(host_seconds=100),
        db=DatabaseStatusSummary(connected=True),
    )


def test_cli_status_json(monkeypatch, capsys):
    monkeypatch.setattr("src.cli.main.collect_system_status", lambda: _status())
    rc = main(["--json", "status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"version": "1.2.88"' in out


def test_cli_health_failed_exit_code(monkeypatch, capsys):
    monkeypatch.setattr("src.cli.main.collect_system_status", lambda: _status("failed"))
    rc = main(["health"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "RESULT: FAILED" in out


def test_cli_maintenance_on_json(monkeypatch, capsys):
    class Mode:
        mode = "maintenance"
        maintenance_reason = "upgrade window"

    monkeypatch.setattr("src.cli.main.set_maintenance_mode", lambda enabled, reason, source, actor: Mode())
    rc = main(["maintenance", "on", "--reason", "upgrade window", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"mode": "maintenance"' in out


def test_cli_license_status(monkeypatch, capsys):
    monkeypatch.setattr("src.cli.main.collect_system_status", lambda: _status())
    rc = main(["license", "status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Status: ok" in out
    assert "Mode: normal" in out


def test_cli_license_status_readonly_still_returns_zero(monkeypatch, capsys):
    status = _status()
    status.license.readonly = True
    status.license.mode = "license_expired_readonly"
    monkeypatch.setattr("src.cli.main.collect_system_status", lambda: status)
    rc = main(["license", "status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Readonly: yes" in out


def test_cli_services_status(monkeypatch, capsys):
    status = _status()
    status.services = []
    monkeypatch.setattr("src.cli.main.collect_system_status", lambda: status)
    rc = main(["services", "status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Services: 0/0 active" in out


def test_cli_services_restart_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "src.cli.main.create_services_restart_command",
        lambda **kwargs: type(
            "ServiceRestartResult",
            (),
            {
                "success": True,
                "action": "services_restart",
                "requested_scope": "api",
                "restarted_units": ["vpnmanager-api"],
                "version": "1.2.90",
                "mode": "normal",
                "health_summary": {"api": "ok", "services": "ok", "result": "ok"},
                "warnings": [],
                "error": None,
                "to_dict": lambda self: {
                    "success": True,
                    "action": "services_restart",
                    "requested_scope": "api",
                    "restarted_units": ["vpnmanager-api"],
                    "version": "1.2.90",
                    "mode": "normal",
                    "health_summary": {"api": "ok", "services": "ok", "result": "ok"},
                    "warnings": [],
                    "error": None,
                },
            },
        )()
    )
    rc = main(["services", "restart", "--api", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"requested_scope": "api"' in out


def test_cli_services_restart_requires_yes_for_all(capsys):
    rc = main(["services", "restart", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 1
    assert payload["error"] == "Full service restart requires confirmation; rerun with --yes"


def test_cli_support_bundle_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "src.cli.main.create_support_bundle",
        lambda **kwargs: type(
            "BundleResult",
            (),
            {
                "success": True,
                "archive_path": "/tmp/vpnmanager-support-bundle-1.tar.gz",
                "bundle_size_bytes": 1234,
                "sections_included": ["status", "config"],
                "sections_failed": [],
                "manifest_path": "manifest.json",
                "to_dict": lambda self: {
                    "success": True,
                    "archive_path": "/tmp/vpnmanager-support-bundle-1.tar.gz",
                    "bundle_size_bytes": 1234,
                    "sections_included": ["status", "config"],
                    "sections_failed": [],
                    "manifest_path": "manifest.json",
                },
            },
        )()
    )
    rc = main(["support-bundle", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"archive_path": "/tmp/vpnmanager-support-bundle-1.tar.gz"' in out


def test_cli_backup_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "src.cli.main.create_backup_command",
        lambda **kwargs: type(
            "BackupResult",
            (),
            {
                "success": True,
                "action": "backup_create",
                "backup_type": "full",
                "archive_path": "/tmp/vpnmanager-backup.tar.gz",
                "size_bytes": 1234,
                "version": "1.2.88",
                "mode": "normal",
                "included_sections": ["db", "env"],
                "warnings": [],
                "error": None,
                "to_dict": lambda self: {
                    "success": True,
                    "action": "backup_create",
                    "backup_type": "full",
                    "archive_path": "/tmp/vpnmanager-backup.tar.gz",
                    "size_bytes": 1234,
                    "version": "1.2.88",
                    "mode": "normal",
                    "included_sections": ["db", "env"],
                    "warnings": [],
                    "error": None,
                },
            },
        )()
    )
    rc = main(["backup", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"archive_path": "/tmp/vpnmanager-backup.tar.gz"' in out



def test_cli_restore_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "src.cli.main.create_restore_command",
        lambda **kwargs: type(
            "RestoreResult",
            (),
            {
                "success": True,
                "action": "restore_full",
                "archive_path": "/tmp/vpnmanager-backup-1.tar.gz",
                "backup_id": "20260327-100000",
                "version": "1.2.89",
                "mode": "normal",
                "restored_sections": ["db", "env"],
                "warnings": [],
                "error": None,
                "maintenance_reason": None,
                "health_summary": {"api": "ok", "db": "ok"},
                "log_hint": None,
                "to_dict": lambda self: {
                    "success": True,
                    "action": "restore_full",
                    "archive_path": "/tmp/vpnmanager-backup-1.tar.gz",
                    "backup_id": "20260327-100000",
                    "version": "1.2.89",
                    "mode": "normal",
                    "restored_sections": ["db", "env"],
                    "warnings": [],
                    "error": None,
                    "maintenance_reason": None,
                    "health_summary": {"api": "ok", "db": "ok"},
                    "log_hint": None,
                },
            },
        )()
    )
    rc = main(["restore", "--archive", "/tmp/vpnmanager-backup-1.tar.gz", "--yes", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"backup_id": "20260327-100000"' in out


def test_cli_restore_requires_yes_in_json_mode(capsys):
    rc = main(["restore", "--archive", "/tmp/vpnmanager-backup-1.tar.gz", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 1
    assert payload["error"] == "Restore requires confirmation; rerun with --yes"


def test_cli_returns_friendly_error_when_env_unreadable(monkeypatch, capsys):
    import src.cli.main as cli_main

    monkeypatch.setattr(cli_main, "CLI_ENV_ERROR", "Cannot read /opt/vpnmanager/.env. Run vpnmanager with sudo or as root.")
    monkeypatch.setattr(cli_main.os, "geteuid", lambda: 1000)
    rc = cli_main.main(["status", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 1
    assert payload["error"] == "Cannot read /opt/vpnmanager/.env. Run vpnmanager with sudo or as root."
