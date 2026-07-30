from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

from src.modules import backup_manager
from src.modules.backup_manager import BackupManager, _is_new_format
from src.utils.runtime_paths import get_app_version


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_full_archive(
    root: Path,
    *,
    env_contents: str | None,
    include_db_checksum: bool = True,
    version: str | None = None,
) -> tuple[BackupManager, str]:
    backup_id = "20260730-010203"
    payload = root / "payload" / "backup"
    payload.mkdir(parents=True)
    database = payload / "database.sql.gz"
    database.write_bytes(b"database-dump" * 20)
    checksums = {}
    if include_db_checksum:
        checksums["database.sql.gz"] = _sha256(database)

    if env_contents is not None:
        env_file = payload / "env.env"
        env_file.write_text(env_contents, encoding="utf-8")
        checksums["env.env"] = _sha256(env_file)

    metadata = {
        "version": version or backup_manager.CURRENT_VERSION,
        "backup_type": "full",
        "database_dump": True,
        "env_backed_up": env_contents is not None,
        "checksums": checksums,
    }
    (payload / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    archive = root / f"vpnmanager-backup-{backup_id}.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(payload, arcname="backup")
    return BackupManager(object(), backup_dir=str(root)), backup_id


def test_full_backup_verification_requires_portable_encryption_key(tmp_path):
    manager, backup_id = _write_full_archive(
        tmp_path, env_contents="DATABASE_URL=postgresql://local\nVMS_ENCRYPTION_KEY=\n"
    )

    result = manager.verify_backup(backup_id)

    assert result["ok"] is False
    assert "VMS_ENCRYPTION_KEY" in " ".join(result["errors"])


def test_full_backup_verification_accepts_complete_core_payload(tmp_path):
    manager, backup_id = _write_full_archive(
        tmp_path,
        env_contents=(
            "DATABASE_URL=postgresql://local\n"
            "VMS_ENCRYPTION_KEY=portable-test-key\n"
        ),
    )

    result = manager.verify_backup(backup_id)

    assert result["ok"] is True, result
    assert result["metadata"]["backup_type"] == "full"
    assert result["files_checked"] == 2


def test_labeled_v2_backup_id_is_not_misclassified_as_legacy():
    assert _is_new_format("20260730-010203-nightly") is True
    assert _is_new_format("20260730-010203-customer_dr.1") is True
    assert _is_new_format("20260730_010203") is False


def test_backup_metadata_version_tracks_runtime_version():
    assert backup_manager.CURRENT_VERSION == get_app_version()


def test_full_backup_verification_requires_core_checksums(tmp_path):
    manager, backup_id = _write_full_archive(
        tmp_path,
        env_contents="VMS_ENCRYPTION_KEY=portable-test-key\n",
        include_db_checksum=False,
    )

    result = manager.verify_backup(backup_id)

    assert result["ok"] is False
    assert "Required checksum missing: database.sql.gz" in result["errors"]


def test_incompatible_major_version_is_rejected_during_preflight(tmp_path):
    manager, backup_id = _write_full_archive(
        tmp_path,
        env_contents="VMS_ENCRYPTION_KEY=portable-test-key\n",
        version="999.0.0",
    )

    result = manager.verify_backup(backup_id)

    assert result["ok"] is False
    assert "Incompatible backup version" in " ".join(result["errors"])
