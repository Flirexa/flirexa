from src.modules.service_cli import _restartable_units, create_services_restart_command
from src.modules.system_status.models import (
    BackupStatusSummary,
    ComponentHealth,
    DatabaseStatusSummary,
    DiskStatusSummary,
    HealthStatusSummary,
    LicenseStatusSummary,
    ServiceStatus,
    SystemStatus,
    UpdateStatusSummary,
    UptimeSummary,
)


def _status(mode: str = "normal") -> SystemStatus:
    return SystemStatus(
        collected_at="2026-03-28T12:00:00Z",
        result="ok",
        version="1.2.90",
        mode=mode,
        maintenance_reason=None,
        layout_mode="release-layout",
        install_root="/opt/vpnmanager",
        current_release="/opt/vpnmanager/releases/1.2.90",
        services=[
            ServiceStatus(name="vpnmanager-api", unit="vpnmanager-api", enabled=True, active=True),
            ServiceStatus(name="vpnmanager-worker", unit="vpnmanager-worker", enabled=True, active=True),
            ServiceStatus(name="vpnmanager-admin-bot", unit="vpnmanager-admin-bot", enabled=False, active=False),
            ServiceStatus(name="vpnmanager-client-bot", unit="vpnmanager-client-bot", enabled=True, active=True),
            ServiceStatus(name="vpnmanager-client-portal", unit="vpnmanager-client-portal", enabled=True, active=True),
        ],
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
        uptime=UptimeSummary(host_seconds=10),
        db=DatabaseStatusSummary(connected=True),
    )


def test_restartable_units_filters_disabled_admin_bot():
    units = _restartable_units(_status(), "all")
    assert "vpnmanager-api" in units
    assert "vpnmanager-client-bot" in units
    assert "vpnmanager-client-portal" in units
    assert "vpnmanager-admin-bot" not in units


def test_create_services_restart_blocks_in_update_mode(monkeypatch):
    monkeypatch.setattr("src.modules.service_cli.collect_system_status", lambda: _status("update_in_progress"))
    result = create_services_restart_command(scope="api")
    assert result.success is False
    assert "blocked" in (result.error or "")


def test_create_services_restart_executes_and_audits(monkeypatch):
    statuses = [_status(), _status()]
    monkeypatch.setattr("src.modules.service_cli.collect_system_status", lambda: statuses.pop(0))
    monkeypatch.setattr("src.modules.service_cli.shutil.which", lambda name: "/bin/systemctl")

    calls = []

    def fake_run(cmd, check=False, capture_output=False, text=False, timeout=None):
        calls.append(cmd)
        class R:
            stdout = ""
            stderr = ""
        return R()

    class DummyDB:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def add(self, obj):
            self.audit = obj

    db = DummyDB()
    monkeypatch.setattr("src.modules.service_cli.subprocess.run", fake_run)
    monkeypatch.setattr("src.modules.service_cli.get_db_context", lambda: db)
    monkeypatch.setattr("src.modules.service_cli.time.sleep", lambda _: None)

    result = create_services_restart_command(scope="api")
    assert result.success is True
    assert result.restarted_units == ["vpnmanager-api"]
    assert calls[0] == ["systemctl", "restart", "vpnmanager-api"]
    assert db.audit.details["source"] == "cli"


def test_create_services_restart_uses_extended_timeout(monkeypatch):
    statuses = [_status(), _status()]
    monkeypatch.setattr("src.modules.service_cli.collect_system_status", lambda: statuses.pop(0))
    monkeypatch.setattr("src.modules.service_cli.shutil.which", lambda name: "/bin/systemctl")
    monkeypatch.setattr("src.modules.service_cli.time.sleep", lambda _: None)

    timeouts = []

    def fake_run(cmd, check=False, capture_output=False, text=False, timeout=None):
        timeouts.append(timeout)
        class R:
            stdout = ""
            stderr = ""
        return R()

    class DummyDB:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def add(self, obj):
            self.audit = obj

    monkeypatch.setattr("src.modules.service_cli.subprocess.run", fake_run)
    monkeypatch.setattr("src.modules.service_cli.get_db_context", lambda: DummyDB())

    result = create_services_restart_command(scope="worker")
    assert result.success is True
    assert timeouts == [90]
