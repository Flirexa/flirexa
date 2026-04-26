from src.database.models import AuditAction
from src.modules.backup_manager import BackupManager


class _DummyDB:
    def __init__(self):
        self.calls = 0
        self.added = []
        self.rollbacks = 0
        self.commits = 0

    def add(self, obj):
        self.calls += 1
        self.added.append(obj)

    def commit(self):
        self.commits += 1
        if self.commits == 1:
            raise RuntimeError("enum mismatch")

    def rollback(self):
        self.rollbacks += 1


def test_write_audit_log_safe_falls_back_to_config_change():
    db = _DummyDB()
    mgr = BackupManager(db, backup_dir="/tmp")

    mgr._write_audit_log_safe(
        user_type="admin",
        action=AuditAction.BACKUP_CREATE,
        target_type="backup",
        target_name="vpnmanager-backup-1.tar.gz",
        details={"backup_type": "full"},
    )

    assert db.rollbacks == 1
    assert db.commits == 2
    assert db.added[-1].action == AuditAction.CONFIG_CHANGE
    assert db.added[-1].details["original_action"] == "backup_create"
    assert db.added[-1].details["audit_fallback"] is True
