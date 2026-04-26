from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from src.modules.restore_cli import create_restore_command
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


def _status(tmp_path: Path, *, mode: str = "normal", result: str = "ok") -> SystemStatus:
    install_root = tmp_path / "install"
    install_root.mkdir(parents=True, exist_ok=True)
    return SystemStatus(
        collected_at="2026-03-27T10:00:00Z",
        result=result,  # type: ignore[arg-type]
        version="1.2.89",
        mode=mode,
        maintenance_reason="planned work" if mode == "maintenance" else None,
        layout_mode="release-layout",
        install_root=str(install_root),
        current_release=str(install_root / "releases" / "1.2.89"),
        services=[],
        license=LicenseStatusSummary(mode="normal", status="ok"),
        update=UpdateStatusSummary(active=mode in {"update_in_progress", "rollback_in_progress"}),
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
        disk=DiskStatusSummary(install_root_free_mb=4096, backups_free_mb=4096, staging_free_mb=4096),
        uptime=UptimeSummary(host_seconds=100),
        db=DatabaseStatusSummary(connected=True, current_revision="020", head_revision="020", matches_head=True),
    )


@contextmanager
def _db_context():
    yield object()


def test_restore_command_success(monkeypatch, tmp_path):
    archive = tmp_path / "vpnmanager-backup-20260327-100000.tar.gz"
    archive.write_bytes(b"test")
    statuses = iter([_status(tmp_path), _status(tmp_path)])
    monkeypatch.setattr("src.modules.restore_cli.collect_system_status", lambda: next(statuses))
    monkeypatch.setattr("src.modules.restore_cli.get_db_context", _db_context)
    monkeypatch.setattr("src.modules.restore_cli.os.geteuid", lambda: 0)
    monkeypatch.setattr("src.modules.restore_cli.os.access", lambda path, mode: True)
    monkeypatch.setattr("src.modules.restore_cli.shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr("src.modules.restore_cli.shutil.disk_usage", lambda path: type("DU", (), {"free": 1024 * 1024 * 1024})())

    maintenance_calls = []
    monkeypatch.setattr(
        "src.modules.restore_cli.get_explicit_maintenance_state",
        lambda db: type("State", (), {"enabled": False, "reason": None})(),
    )
    monkeypatch.setattr(
        "src.modules.restore_cli.set_maintenance_mode",
        lambda enabled, reason, source, actor: maintenance_calls.append((enabled, reason, source, actor)) or type("Mode", (), {"mode": "maintenance" if enabled else "normal", "maintenance_reason": reason if enabled else None})(),
    )

    class FakeManager:
        def __init__(self, db, backup_dir=None):
            self.backup_dir = backup_dir

        def verify_backup(self, backup_id):
            assert backup_id == "20260327-100000"
            return {"ok": True, "errors": []}

        def restore_full_system(self, backup_id, **kwargs):
            return {
                "backup_id": backup_id,
                "database_restored": True,
                "env_restored": True,
                "wireguard_restored": ["wg0.conf"],
                "services_restarted": True,
                "errors": [],
            }

    monkeypatch.setattr("src.modules.restore_cli.BackupManager", FakeManager)

    result = create_restore_command(archive=str(archive))

    assert result.success is True
    assert result.backup_id == "20260327-100000"
    assert result.restored_sections == ["db", "env", "wireguard", "services"]
    assert maintenance_calls[0][0] is True
    assert maintenance_calls[-1][0] is False


def test_restore_command_fails_when_update_active(monkeypatch, tmp_path):
    status = _status(tmp_path, mode="update_in_progress")
    monkeypatch.setattr("src.modules.restore_cli.collect_system_status", lambda: status)
    monkeypatch.setattr("src.modules.restore_cli.os.geteuid", lambda: 0)

    archive = tmp_path / "vpnmanager-backup-20260327-100000.tar.gz"
    archive.write_bytes(b"test")
    result = create_restore_command(archive=str(archive))

    assert result.success is False
    assert "update or rollback is active" in result.error


def test_restore_command_fails_when_archive_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("src.modules.restore_cli.collect_system_status", lambda: _status(tmp_path))
    monkeypatch.setattr("src.modules.restore_cli.os.geteuid", lambda: 0)

    result = create_restore_command(archive=str(tmp_path / "missing.tar.gz"))

    assert result.success is False
    assert "not found" in result.error


def test_restore_command_fails_when_backend_reports_error(monkeypatch, tmp_path):
    archive = tmp_path / "vpnmanager-backup-20260327-100000.tar.gz"
    archive.write_bytes(b"test")
    monkeypatch.setattr("src.modules.restore_cli.collect_system_status", lambda: _status(tmp_path))
    monkeypatch.setattr("src.modules.restore_cli.get_db_context", _db_context)
    monkeypatch.setattr("src.modules.restore_cli.os.geteuid", lambda: 0)
    monkeypatch.setattr("src.modules.restore_cli.os.access", lambda path, mode: True)
    monkeypatch.setattr("src.modules.restore_cli.shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr("src.modules.restore_cli.shutil.disk_usage", lambda path: type("DU", (), {"free": 1024 * 1024 * 1024})())
    monkeypatch.setattr(
        "src.modules.restore_cli.get_explicit_maintenance_state",
        lambda db: type("State", (), {"enabled": False, "reason": None})(),
    )
    monkeypatch.setattr(
        "src.modules.restore_cli.set_maintenance_mode",
        lambda enabled, reason, source, actor: type("Mode", (), {"mode": "maintenance", "maintenance_reason": reason})(),
    )

    class FakeManager:
        def __init__(self, db, backup_dir=None):
            pass

        def verify_backup(self, backup_id):
            return {"ok": True, "errors": []}

        def restore_full_system(self, backup_id, **kwargs):
            return {
                "backup_id": backup_id,
                "database_restored": True,
                "env_restored": False,
                "wireguard_restored": [],
                "services_restarted": False,
                "errors": ["env restore failed"],
            }

    monkeypatch.setattr("src.modules.restore_cli.BackupManager", FakeManager)

    result = create_restore_command(archive=str(archive))

    assert result.success is False
    assert "env restore failed" in result.error


def test_restore_command_honors_existing_maintenance(monkeypatch, tmp_path):
    archive = tmp_path / "vpnmanager-backup-20260327-100000.tar.gz"
    archive.write_bytes(b"test")
    statuses = iter([_status(tmp_path, mode="maintenance"), _status(tmp_path, mode="maintenance")])
    monkeypatch.setattr("src.modules.restore_cli.collect_system_status", lambda: next(statuses))
    monkeypatch.setattr("src.modules.restore_cli.get_db_context", _db_context)
    monkeypatch.setattr("src.modules.restore_cli.os.geteuid", lambda: 0)
    monkeypatch.setattr("src.modules.restore_cli.os.access", lambda path, mode: True)
    monkeypatch.setattr("src.modules.restore_cli.shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr("src.modules.restore_cli.shutil.disk_usage", lambda path: type("DU", (), {"free": 1024 * 1024 * 1024})())
    monkeypatch.setattr(
        "src.modules.restore_cli.get_explicit_maintenance_state",
        lambda db: type("State", (), {"enabled": True, "reason": "planned work"})(),
    )
    calls = []
    monkeypatch.setattr("src.modules.restore_cli.set_maintenance_mode", lambda *args, **kwargs: calls.append((args, kwargs)))

    class FakeManager:
        def __init__(self, db, backup_dir=None):
            pass

        def verify_backup(self, backup_id):
            return {"ok": True, "errors": []}

        def restore_full_system(self, backup_id, **kwargs):
            return {
                "backup_id": backup_id,
                "database_restored": True,
                "env_restored": True,
                "wireguard_restored": [],
                "services_restarted": True,
                "errors": [],
            }

    monkeypatch.setattr("src.modules.restore_cli.BackupManager", FakeManager)

    result = create_restore_command(archive=str(archive))

    assert result.success is True
    assert calls == []
    assert any("Maintenance mode already enabled" in warning for warning in result.warnings)
