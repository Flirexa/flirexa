"""Regression coverage for the design2 backup/storage API contract."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.modules.auto_backup_admin import (
    get_backup_settings,
    get_storage_status,
    update_backup_settings,
)
from src.modules.backup_manager import BackupManager


def test_local_storage_reports_ready_without_calling_it_a_mount(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    usage = SimpleNamespace(total=10_000, used=2_500, free=7_500)

    with (
        patch.object(
            BackupManager,
            "_get_storage_config",
            return_value={"backup_storage_type": "local", "backup_mount_address": ""},
        ),
        patch.object(BackupManager, "_get_backup_dir", return_value=str(backup_dir)),
        patch.object(BackupManager, "is_path_mounted") as mounted_check,
        patch("src.modules.auto_backup_admin.shutil.disk_usage", return_value=usage),
    ):
        result = get_storage_status(object())

    assert result["storage_type"] == "local"
    assert result["mounted"] is None
    assert result["ready"] is True
    assert result["writable"] is True
    assert result["target_exists"] is True
    assert result["usage"]["used_bytes"] == 2_500
    assert result["usage"]["total_bytes"] == 10_000
    mounted_check.assert_not_called()


def test_local_storage_uses_writable_parent_before_first_backup(tmp_path):
    backup_dir = tmp_path / "not-created-yet" / "backups"
    usage = SimpleNamespace(total=20_000, used=5_000, free=15_000)

    with (
        patch.object(
            BackupManager,
            "_get_storage_config",
            return_value={"backup_storage_type": "local", "backup_mount_address": ""},
        ),
        patch.object(BackupManager, "_get_backup_dir", return_value=str(backup_dir)),
        patch("src.modules.auto_backup_admin.shutil.disk_usage", return_value=usage) as disk_usage,
    ):
        result = get_storage_status(object())

    assert result["ready"] is True
    assert result["target_exists"] is False
    assert result["usage"]["free_bytes"] == 15_000
    disk_usage.assert_called_once_with(str(tmp_path))


def test_unmounted_network_storage_never_reports_local_backing_disk_usage(tmp_path):
    mount_point = tmp_path / "network"
    mount_point.mkdir()

    with (
        patch.object(
            BackupManager,
            "_get_storage_config",
            return_value={
                "backup_storage_type": "network",
                "backup_mount_address": "//192.0.2.10/backups",
            },
        ),
        patch.object(BackupManager, "_get_backup_dir", return_value=str(mount_point)),
        patch.object(BackupManager, "is_path_mounted", return_value=False),
        patch("src.modules.auto_backup_admin.shutil.disk_usage") as disk_usage,
    ):
        result = get_storage_status(object())

    assert result["mounted"] is False
    assert result["ready"] is False
    assert result["writable"] is False
    assert result["usage"] is None
    disk_usage.assert_not_called()


def test_backup_settings_round_trip_uses_canonical_backend_keys(db_session):
    payload = {
        "backup_enabled": "true",
        "backup_interval_hours": 48,
        "backup_hour_utc": 7,
        "backup_retention_count": 12,
        "backup_storage_type": "network",
        "backup_mount_type": "nfs",
        "backup_mount_address": "192.0.2.10:/exports/backups",
        "backup_mount_point": "/mnt/flirexa-backups",
        "backup_mount_options": "vers=4.2",
    }

    result = update_backup_settings(payload, db_session)
    saved = get_backup_settings(db_session)

    assert result["updated"] == len(payload)
    for key, value in payload.items():
        assert saved[key] == str(value)


def test_design2_consumes_nested_usage_and_sends_canonical_settings():
    source = Path(
        "src/web/frontend/src/design2/screens/D2Backup.vue"
    ).read_text(encoding="utf-8")

    assert "storage.value.usage?.used_bytes" in source
    assert "storage.value.usage?.total_bytes" in source
    assert "storage.value.storage_type === 'network'" in source
    assert "storage.value.ready ?" in source
    assert "backupSettings.backup_storage_type = 'network'" in source
    assert "payload.backup_retention_count" in source
    assert "payload.backup_hour_utc" in source
    assert "payload.backup_interval_hours" in source
    assert "data?.updated === 0" in source
    assert "async function fmtBackupSize" not in source
    assert "backupSettings.schedule" not in source
    assert "backupSettings.net_host" not in source

