"""Durable database finalization for API-launched manual rollbacks."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from update_rollback_finalize import finalize_rollback


def _database(tmp_path) -> str:
    url = f"sqlite:///{tmp_path / 'rollback.db'}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE update_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_version VARCHAR(32) NOT NULL,
                to_version VARCHAR(32) NOT NULL,
                update_type VARCHAR(16), channel VARCHAR(16),
                status VARCHAR(32) NOT NULL,
                started_at DATETIME, completed_at DATETIME,
                duration_seconds FLOAT, progress_heartbeat_at DATETIME,
                started_by VARCHAR(128), rollback_available BOOLEAN,
                backup_path TEXT, is_rollback BOOLEAN,
                rollback_of_id INTEGER, error_message TEXT,
                log TEXT, last_step VARCHAR(64)
            )
        """))
        connection.execute(text("""
            CREATE TABLE system_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(100) UNIQUE NOT NULL, value TEXT,
                value_type VARCHAR(20), description TEXT, updated_at DATETIME
            )
        """))
        connection.execute(
            text("""
                INSERT INTO update_history
                    (id, from_version, to_version, update_type, status,
                     started_at, started_by, rollback_available, backup_path,
                     is_rollback)
                VALUES
                    (7, '2.2.72', '2.2.75', 'patch', 'APPLYING',
                     :started_at, 'admin', 1, '/backup/pre-2.2.75', 0)
            """),
            {"started_at": datetime.now(timezone.utc) - timedelta(minutes=2)},
        )
        connection.execute(text("""
            INSERT INTO system_config
                (key, value, value_type, description)
            VALUES
                ('updates_auto_apply', 'true', 'bool', 'old description')
        """))
    engine.dispose()
    return url


def _finalize(url: str, **overrides) -> None:
    values = {
        "database_url": url,
        "rollback_id": 8,
        "original_id": 7,
        "from_version": "2.2.75",
        "to_version": "2.2.72",
        "started_by": "admin",
        "started_at": datetime.now(timezone.utc) - timedelta(seconds=5),
        "backup_path": "/backup/pre-2.2.75",
        "log_text": "rollback completed",
    }
    values.update(overrides)
    finalize_rollback(**values)


def test_finalize_recreates_terminal_history_and_suppresses_reapply(tmp_path):
    url = _database(tmp_path)
    _finalize(url)

    engine = create_engine(url)
    with engine.connect() as connection:
        original = connection.execute(
            text("SELECT * FROM update_history WHERE id = 7")
        ).mappings().one()
        rollback = connection.execute(
            text("SELECT * FROM update_history WHERE id = 8")
        ).mappings().one()
        config = dict(connection.execute(
            text("SELECT key, value FROM system_config")
        ).all())

    assert original["status"] == "ROLLED_BACK"
    assert original["rollback_available"] == 0
    assert rollback["status"] == "ROLLED_BACK"
    assert rollback["is_rollback"] == 1
    assert rollback["rollback_of_id"] == 7
    assert rollback["from_version"] == "2.2.75"
    assert rollback["to_version"] == "2.2.72"
    assert rollback["log"] == "rollback completed"
    assert config["updates_auto_apply"] == "false"
    assert config["updates_rollback_suppressed_version"] == "2.2.75"


def test_finalize_is_idempotent(tmp_path):
    url = _database(tmp_path)
    _finalize(url)
    _finalize(url, log_text="second pass")

    engine = create_engine(url)
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM update_history WHERE id = 8")
        ).scalar_one()
        log = connection.execute(
            text("SELECT log FROM update_history WHERE id = 8")
        ).scalar_one()

    assert count == 1
    assert log == "second pass"


def test_finalize_rejects_history_id_collision(tmp_path):
    url = _database(tmp_path)
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO update_history
                (id, from_version, to_version, status, started_by,
                 rollback_available, is_rollback, rollback_of_id)
            VALUES
                (8, '8.0.0', '7.0.0', 'ROLLED_BACK', 'admin', 0, 1, 999)
        """))

    with pytest.raises(RuntimeError, match="belongs to another operation"):
        _finalize(url)

    with engine.connect() as connection:
        status = connection.execute(
            text("SELECT status FROM update_history WHERE id = 7")
        ).scalar_one()
    assert status == "APPLYING"
