from pathlib import Path


def test_stage1_update_migration_down_revision_targets_018():
    migration = Path("alembic/versions/019_stage1_update_hardening.py").read_text(encoding="utf-8")
    assert 'down_revision = "018"' in migration


def test_update_status_enum_expansion_migration_exists_and_targets_019():
    migration = Path("alembic/versions/020_expand_update_status_enum.py").read_text(encoding="utf-8")
    assert 'down_revision = "019_stage1_update_hardening"' in migration
    assert "DOWNLOADED" in migration
    assert "VERIFIED" in migration
    assert "READY_TO_APPLY" in migration
    assert "ROLLBACK_REQUIRED" in migration
