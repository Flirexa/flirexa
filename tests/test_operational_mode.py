import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"

from src.database.models import AuditLog, Base, SystemConfig
from src.modules.operational_mode import (
    ExplicitMaintenanceState,
    classify_api_request,
    derive_license_mode,
    is_request_allowed,
    resolve_operational_mode,
    set_maintenance_mode,
)


def test_operational_mode_priority():
    mode = resolve_operational_mode(
        maintenance=ExplicitMaintenanceState(enabled=True, reason="ops"),
        update_active=True,
        update_kind="rollback",
        license_mode="license_expired_readonly",
        degraded=True,
    )
    assert mode.mode == "rollback_in_progress"


def test_set_maintenance_mode_writes_state_and_audit(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    @__import__("contextlib").contextmanager
    def fake_db_context():
        db = TestSession()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    monkeypatch.setattr("src.modules.operational_mode.get_db_context", fake_db_context)
    monkeypatch.setattr("src.modules.operational_mode.derive_license_mode", lambda: "normal")

    mode = set_maintenance_mode(True, reason="planned work", source="cli", actor="test")
    assert mode.mode == "maintenance"

    db = TestSession()
    try:
        cfg = {row.key: row.value for row in db.query(SystemConfig).all()}
        assert cfg["maintenance_mode"] == "true"
        assert cfg["maintenance_reason"] == "planned work"
        audit = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert audit is not None
        assert audit.target_type == "operational_mode"
        assert audit.details["new_mode"] == "maintenance"
    finally:
        db.close()


def test_request_policy_maintenance_vs_recovery():
    assert classify_api_request("/api/v1/updates/apply", "POST") == "recovery"
    assert classify_api_request("/api/v1/clients", "POST") == "business_mutation"
    allowed, _ = is_request_allowed("maintenance", "/api/v1/updates/apply", "POST")
    assert allowed is True
    allowed, reason = is_request_allowed("maintenance", "/api/v1/clients", "POST")
    assert allowed is False
    assert reason is not None


def test_request_policy_license_expired_readonly_allows_restore_but_blocks_business_mutation():
    allowed, _ = is_request_allowed("license_expired_readonly", "/api/v1/backup/restore/full/demo", "POST")
    assert allowed is True
    allowed, _ = is_request_allowed("license_expired_readonly", "/api/v1/updates/restart", "POST")
    assert allowed is True
    allowed, _ = is_request_allowed("license_expired_readonly", "/api/v1/clients", "POST")
    assert allowed is False


def test_license_grace_status_does_not_replay_cache_on_each_request(monkeypatch):
    """A cached lease must not overwrite a freshly observed network outage."""
    from src.modules import operational_mode as module
    from src.modules.license import manager as license_manager

    class PaidManager:
        @staticmethod
        def is_free():
            return False

    replay_calls = []
    monkeypatch.setenv("LICENSE_KEY", "signed-paid-license")
    monkeypatch.setattr(license_manager, "get_license_manager", lambda: PaidManager())
    monkeypatch.setattr(
        module,
        "get_online_status",
        lambda: {"status": "ok", "server_reachable": False},
    )
    monkeypatch.setattr(module, "is_license_blocked", lambda: (False, ""))
    # Kept as a regression sentinel: the old implementation called this on
    # every request and reset server_reachable to True from the cache payload.
    monkeypatch.setattr(
        module,
        "_license_warmup_from_cache",
        lambda: replay_calls.append(True),
        raising=False,
    )

    assert derive_license_mode() == "license_grace"
    assert replay_calls == []
