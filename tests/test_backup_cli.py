from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from src.modules.backup_cli import create_backup_command
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


def _status(tmp_path: Path) -> SystemStatus:
    install_root = tmp_path / "install"
    install_root.mkdir(parents=True, exist_ok=True)
    return SystemStatus(
        collected_at="2026-03-27T10:00:00Z",
        result="ok",
        version="1.2.88",
        mode="normal",
        maintenance_reason=None,
        layout_mode="release-layout",
        install_root=str(install_root),
        current_release=str(install_root / "releases" / "1.2.88"),
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
        disk=DiskStatusSummary(install_root_free_mb=2048, backups_free_mb=2048, staging_free_mb=2048),
        uptime=UptimeSummary(host_seconds=100),
        db=DatabaseStatusSummary(connected=True, current_revision="020", head_revision="020", matches_head=True),
    )


@contextmanager
def _db_context():
    yield object()


def test_create_backup_command_full_uses_existing_backend(monkeypatch, tmp_path):
    called = {}
    status = _status(tmp_path)
    output_dir = tmp_path / "backups-out"

    monkeypatch.setattr("src.modules.backup_cli.collect_system_status", lambda: status)
    monkeypatch.setattr("src.modules.backup_cli.get_db_context", _db_context)

    class FakeManager:
        def __init__(self, db, backup_dir=None):
            called["backup_dir"] = backup_dir

        def create_full_backup(self, **kwargs):
            called["kwargs"] = kwargs
            return {
                "archive_path": str(output_dir / "vpnmanager-backup-20260327-100000.tar.gz"),
                "archive_size_bytes": 12345,
                "errors": [],
            }

    monkeypatch.setattr("src.modules.backup_cli.BackupManager", FakeManager)

    result = create_backup_command(backup_type="full", output=str(output_dir), name="nightly")

    assert result.success is True
    assert called["backup_dir"] == str(output_dir)
    assert called["kwargs"]["label"] == "nightly"
    assert called["kwargs"]["audit_source"] == "cli"


def test_create_backup_command_db_only_uses_existing_backend(monkeypatch, tmp_path):
    called = {}
    status = _status(tmp_path)
    output_dir = tmp_path / "backups-out"

    monkeypatch.setattr("src.modules.backup_cli.collect_system_status", lambda: status)
    monkeypatch.setattr("src.modules.backup_cli.get_db_context", _db_context)

    class FakeManager:
        def __init__(self, db, backup_dir=None):
            called["backup_dir"] = backup_dir

        def create_database_backup(self, **kwargs):
            called["kwargs"] = kwargs
            return {
                "archive_path": str(output_dir / "vpnmanager-backup-20260327-100000-db.tar.gz"),
                "archive_size_bytes": 54321,
                "errors": [],
            }

    monkeypatch.setattr("src.modules.backup_cli.BackupManager", FakeManager)

    result = create_backup_command(backup_type="db-only", output=str(output_dir))

    assert result.success is True
    assert called["backup_dir"] == str(output_dir)
    assert called["kwargs"]["audit_source"] == "cli"


def test_create_backup_command_fails_when_update_active(monkeypatch, tmp_path):
    status = _status(tmp_path)
    status.mode = "update_in_progress"
    status.update.active = True
    monkeypatch.setattr("src.modules.backup_cli.collect_system_status", lambda: status)

    result = create_backup_command(backup_type="full")

    assert result.success is False
    assert "update or rollback is active" in result.error


def test_create_backup_command_fails_when_destination_not_writable(monkeypatch, tmp_path):
    status = _status(tmp_path)
    monkeypatch.setattr("src.modules.backup_cli.collect_system_status", lambda: status)
    monkeypatch.setattr("src.modules.backup_cli.os.access", lambda path, mode: False)

    result = create_backup_command(backup_type="full", output=str(tmp_path / "blocked"))

    assert result.success is False
    assert "not writable" in result.error


def test_create_backup_command_fails_strictly_on_backend_partial_error(monkeypatch, tmp_path):
    status = _status(tmp_path)
    monkeypatch.setattr("src.modules.backup_cli.collect_system_status", lambda: status)
    monkeypatch.setattr("src.modules.backup_cli.get_db_context", _db_context)

    class FakeManager:
        def __init__(self, db, backup_dir=None):
            pass

        def create_full_backup(self, **kwargs):
            return {
                "archive_path": "/tmp/backup.tar.gz",
                "archive_size_bytes": 123,
                "errors": ["env copy failed"],
            }

    monkeypatch.setattr("src.modules.backup_cli.BackupManager", FakeManager)

    result = create_backup_command(backup_type="full")

    assert result.success is False
    assert "env copy failed" in result.error
