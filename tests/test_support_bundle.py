from __future__ import annotations

import tarfile
from contextlib import contextmanager
from pathlib import Path

from src.modules.support_bundle import SupportBundleResult, create_support_bundle
from src.modules.system_status.models import (
    BackupStatusSummary,
    ComponentHealth,
    DatabaseStatusSummary,
    DiskStatusSummary,
    HealthStatusSummary,
    LicenseStatusSummary,
    ServiceStatus,
    SystemStatus,
    UpdateRecordSummary,
    UpdateStatusSummary,
    UptimeSummary,
)
from src.modules.support_bundle_sanitizer import sanitize_env_text


def _status(tmp_path: Path) -> SystemStatus:
    return SystemStatus(
        collected_at="2026-03-27T10:00:00Z",
        result="ok",
        version="1.2.88",
        mode="normal",
        maintenance_reason=None,
        layout_mode="release-layout",
        install_root=str(tmp_path),
        current_release=str(tmp_path / "releases" / "1.2.88"),
        services=[
            ServiceStatus(name="api", unit="vpnmanager-api", enabled=True, active=True, substate="running", status_text="active")
        ],
        license=LicenseStatusSummary(mode="normal", status="ok", plan="pro", validator_running=True),
        update=UpdateStatusSummary(
            active=False,
            last_update=UpdateRecordSummary(id=1, from_version="1.2.87", to_version="1.2.88", status="success"),
        ),
        backup=BackupStatusSummary(last_backup_path=str(tmp_path / "backups" / "update_backups" / "pre_1.2.88")),
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


def test_sanitize_env_text_masks_sensitive_keys():
    text = "DB_PASSWORD=supersecret\nLICENSE_KEY=abcdef123456\nNORMAL=value\n"
    sanitized = sanitize_env_text(text, strict=True)
    assert "supersecret" not in sanitized
    assert "abcdef123456" not in sanitized
    assert "NORMAL=value" in sanitized


def test_create_support_bundle_builds_archive_and_redacts_env(monkeypatch, tmp_path):
    install_root = tmp_path / "install"
    (install_root / "backups" / "update_backups" / "pre_1.2.88").mkdir(parents=True)
    (install_root / "staging" / "update_1").mkdir(parents=True)
    (install_root / "releases" / "1.2.88").mkdir(parents=True)
    (install_root / ".env").write_text("DB_PASSWORD=supersecret\nAPP_NAME=test\n", encoding="utf-8")
    (install_root / "backups" / "update_backups" / "pre_1.2.88" / "apply.log").write_text("apply ok\n", encoding="utf-8")

    status = _status(install_root)

    @contextmanager
    def fake_db_context():
        yield object()

    monkeypatch.setattr("src.modules.support_bundle.get_install_root", lambda _default="/opt/vpnmanager": install_root)
    monkeypatch.setattr("src.modules.support_bundle.collect_system_status", lambda: status)
    monkeypatch.setattr("src.modules.support_bundle.get_db_context", fake_db_context)
    monkeypatch.setattr("src.modules.support_bundle._query_update_rows", lambda db, limit: [{"id": 1, "status": "success"}])
    monkeypatch.setattr(
        "src.modules.support_bundle._query_system_config",
        lambda db, strict: [{"key": "maintenance_reason", "value": "upgrade", "value_type": "string"}],
    )

    result = create_support_bundle(
        output_dir=str(tmp_path),
        include_update_logs=True,
        redact_strict=True,
    )

    assert isinstance(result, SupportBundleResult)
    assert result.success is True
    archive_path = Path(result.archive_path)
    assert archive_path.exists()

    with tarfile.open(archive_path, "r:gz") as tar:
        names = tar.getnames()
        dotenv_member = next(name for name in names if name.endswith("config/dotenv.sanitized"))
        manifest_member = next(name for name in names if name.endswith("manifest.json"))
        dotenv_text = tar.extractfile(dotenv_member).read().decode("utf-8")
        manifest_text = tar.extractfile(manifest_member).read().decode("utf-8")

    assert "supersecret" not in dotenv_text
    assert "APP_NAME=test" in dotenv_text
    assert '"name": "config"' in manifest_text


def test_create_support_bundle_is_best_effort_when_config_section_fails(monkeypatch, tmp_path):
    install_root = tmp_path / "install"
    install_root.mkdir(parents=True)
    (install_root / ".env").write_text("APP_NAME=test\n", encoding="utf-8")
    status = _status(install_root)

    @contextmanager
    def fake_db_context():
        yield object()

    monkeypatch.setattr("src.modules.support_bundle.get_install_root", lambda _default="/opt/vpnmanager": install_root)
    monkeypatch.setattr("src.modules.support_bundle.collect_system_status", lambda: status)
    monkeypatch.setattr("src.modules.support_bundle.get_db_context", fake_db_context)
    monkeypatch.setattr("src.modules.support_bundle._query_update_rows", lambda db, limit: [])
    monkeypatch.setattr("src.modules.support_bundle._query_system_config", lambda db, strict: (_ for _ in ()).throw(RuntimeError("config failed")))

    result = create_support_bundle(output_dir=str(tmp_path))

    assert result.success is True
    assert any(item["section"] == "config" for item in result.sections_failed)
