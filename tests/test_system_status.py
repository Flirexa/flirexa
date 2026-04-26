from pathlib import Path

from sqlalchemy.exc import ProgrammingError

from src.modules.system_status.collector import collect_system_status, _service_prefix


def _fake_service(unit: str, active: bool = True, enabled: bool = True):
    from src.modules.system_status.models import ServiceStatus
    return ServiceStatus(
        name=unit,
        unit=unit,
        enabled=enabled,
        active=active,
        substate="running" if active else "dead",
        status_text="active" if active else "inactive",
    )


def test_collect_system_status_release_layout(monkeypatch, tmp_path):
    install_root = tmp_path / "install"
    releases = install_root / "releases" / "1.2.88"
    releases.mkdir(parents=True)
    (releases / "VERSION").write_text("1.2.88\n")
    current = install_root / "current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.symlink_to(releases)

    monkeypatch.setenv("INSTALL_DIR", str(install_root))
    monkeypatch.setattr(
        "src.modules.system_status.collector._collect_services",
        lambda prefix: [
            _fake_service(f"{prefix}-api"),
            _fake_service("postgresql"),
        ],
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._collect_db_status",
        lambda: __import__("src.modules.system_status.models", fromlist=["DatabaseStatusSummary"]).DatabaseStatusSummary(
            connected=True, current_revision="020", head_revision="020", matches_head=True
        ),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._collect_update_summary",
        lambda db_ok, db_session=None: __import__("src.modules.system_status.models", fromlist=["UpdateStatusSummary"]).UpdateStatusSummary(active=False),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._collect_backup_summary",
        lambda: __import__("src.modules.system_status.models", fromlist=["BackupStatusSummary"]).BackupStatusSummary(),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._license_summary",
        lambda api_active: __import__("src.modules.system_status.models", fromlist=["LicenseStatusSummary"]).LicenseStatusSummary(
            mode="normal", status="ok", validator_running=api_active
        ),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._component_from_http",
        lambda url: __import__("src.modules.system_status.models", fromlist=["ComponentHealth"]).ComponentHealth(status="ok", message="ok"),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector.get_explicit_maintenance_state",
        lambda db: __import__("src.modules.operational_mode", fromlist=["ExplicitMaintenanceState"]).ExplicitMaintenanceState(),
    )
    monkeypatch.setattr("src.modules.system_status.collector._worker_heartbeat", lambda db_ok, db_session=None: ("2026-03-27T10:00:00+00:00", 1))

    status = collect_system_status()
    assert status.layout_mode == "release-layout"
    assert status.current_release == str(releases)
    assert status.result == "ok"
    assert status.maintenance_reason is None


def test_collect_system_status_failed_on_broken_current(monkeypatch, tmp_path):
    install_root = tmp_path / "install"
    install_root.mkdir()
    current = install_root / "current"
    current.symlink_to(install_root / "releases" / "missing")
    (install_root / "VERSION").write_text("1.2.88\n")

    monkeypatch.setenv("INSTALL_DIR", str(install_root))
    monkeypatch.setattr(
        "src.modules.system_status.collector._collect_services",
        lambda prefix: [
            _fake_service(f"{prefix}-api"),
            _fake_service("postgresql"),
        ],
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._collect_db_status",
        lambda: __import__("src.modules.system_status.models", fromlist=["DatabaseStatusSummary"]).DatabaseStatusSummary(
            connected=True, current_revision="020", head_revision="020", matches_head=True
        ),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._collect_update_summary",
        lambda db_ok, db_session=None: __import__("src.modules.system_status.models", fromlist=["UpdateStatusSummary"]).UpdateStatusSummary(active=False),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._collect_backup_summary",
        lambda: __import__("src.modules.system_status.models", fromlist=["BackupStatusSummary"]).BackupStatusSummary(),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._license_summary",
        lambda api_active: __import__("src.modules.system_status.models", fromlist=["LicenseStatusSummary"]).LicenseStatusSummary(
            mode="normal", status="ok", validator_running=api_active
        ),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._component_from_http",
        lambda url: __import__("src.modules.system_status.models", fromlist=["ComponentHealth"]).ComponentHealth(status="ok", message="ok"),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector.get_explicit_maintenance_state",
        lambda db: __import__("src.modules.operational_mode", fromlist=["ExplicitMaintenanceState"]).ExplicitMaintenanceState(),
    )
    monkeypatch.setattr("src.modules.system_status.collector._worker_heartbeat", lambda db_ok, db_session=None: ("2026-03-27T10:00:00+00:00", 1))

    status = collect_system_status()
    assert status.result == "failed"
    assert any("current runtime path is invalid" in reason for reason in status.failed_reasons)


def test_collect_update_summary_schema_drift_falls_back():
    from src.modules.system_status.collector import _collect_update_summary

    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise ProgrammingError("select 1", {}, Exception("missing column"))

    summary = _collect_update_summary(True, db_session=BrokenSession())
    assert summary.active is False
    assert summary.consistency_ok is True
    assert "schema drift" in (summary.consistency_message or "")


def test_collect_system_status_does_not_require_worker_heartbeat_when_worker_disabled(monkeypatch, tmp_path):
    install_root = tmp_path / "install"
    install_root.mkdir()
    (install_root / "VERSION").write_text("1.2.92\n")

    monkeypatch.setenv("INSTALL_DIR", str(install_root))
    monkeypatch.setattr(
        "src.modules.system_status.collector._collect_services",
        lambda prefix: [
            _fake_service(f"{prefix}-api"),
            _fake_service("postgresql"),
            _fake_service(f"{prefix}-worker", active=False, enabled=False),
        ],
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._collect_db_status",
        lambda: __import__("src.modules.system_status.models", fromlist=["DatabaseStatusSummary"]).DatabaseStatusSummary(
            connected=True, current_revision="020", head_revision="020", matches_head=True
        ),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._collect_update_summary",
        lambda db_ok, db_session=None: __import__("src.modules.system_status.models", fromlist=["UpdateStatusSummary"]).UpdateStatusSummary(active=False),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._collect_backup_summary",
        lambda: __import__("src.modules.system_status.models", fromlist=["BackupStatusSummary"]).BackupStatusSummary(),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._license_summary",
        lambda api_active: __import__("src.modules.system_status.models", fromlist=["LicenseStatusSummary"]).LicenseStatusSummary(
            mode="normal", status="ok", validator_running=api_active
        ),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector._component_from_http",
        lambda url: __import__("src.modules.system_status.models", fromlist=["ComponentHealth"]).ComponentHealth(status="ok", message="ok"),
    )
    monkeypatch.setattr(
        "src.modules.system_status.collector.get_explicit_maintenance_state",
        lambda db: __import__("src.modules.operational_mode", fromlist=["ExplicitMaintenanceState"]).ExplicitMaintenanceState(),
    )
    monkeypatch.setattr("src.modules.system_status.collector._worker_heartbeat", lambda db_ok, db_session=None: (None, None))

    status = collect_system_status()
    assert status.result == "ok"
    assert "Worker heartbeat unknown" not in status.degraded_reasons


def test_service_prefix_prefers_active_legacy_units(monkeypatch, tmp_path):
    install_root = tmp_path / "spongebot"
    install_root.mkdir()
    monkeypatch.setenv("INSTALL_DIR", str(install_root))

    def fake_run(cmd, capture_output=False, text=False, timeout=None, stderr=None):
        class R:
            def __init__(self, rc):
                self.returncode = rc
                self.stdout = ""
        if cmd == ["systemctl", "is-active", "spongebot-api"]:
            return R(0)
        if cmd == ["systemctl", "is-active", "vpnmanager-api"]:
            return R(3)
        return R(3)

    monkeypatch.setattr("src.modules.system_status.collector.subprocess.run", fake_run)
    assert _service_prefix() == "spongebot"
