#!/usr/bin/env python3
"""Finalize update history after a database-restoring manual rollback.

The rollback shell survives the API restart and may restore a database snapshot
that predates the rollback request itself.  This small, release-local helper
recreates the terminal rollback row, marks the original update rolled back, and
disables normal auto-apply so the same release is not immediately reinstalled.
It reads only DATABASE_URL from the preserved env file and never executes it.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, insert, select, text, update


def _database_url(env_file: Path) -> str:
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != "DATABASE_URL":
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if value:
            return value
    raise RuntimeError(f"DATABASE_URL is missing from {env_file}")


def _only_columns(table: Table, values: dict) -> dict:
    return {key: value for key, value in values.items() if key in table.c}


def _upsert_config(
    connection,
    config: Table,
    *,
    key: str,
    value: str,
    value_type: str,
    description: str,
    updated_at: datetime,
) -> None:
    existing = connection.execute(
        select(config.c.id).where(config.c.key == key)
    ).first()
    values = _only_columns(
        config,
        {
            "value": value,
            "value_type": value_type,
            "description": description,
            "updated_at": updated_at,
        },
    )
    if existing is None:
        connection.execute(insert(config).values(key=key, **values))
    else:
        connection.execute(update(config).where(config.c.key == key).values(**values))


def finalize_rollback(
    *,
    database_url: str,
    rollback_id: int,
    original_id: int,
    from_version: str,
    to_version: str,
    started_by: str,
    started_at: datetime,
    backup_path: str,
    log_text: str,
) -> None:
    if rollback_id <= 0 or original_id <= 0 or rollback_id == original_id:
        raise ValueError("rollback and original IDs must be distinct positive integers")

    now = datetime.now(timezone.utc)
    duration = max(0.0, (now - started_at).total_seconds())
    engine = create_engine(database_url, pool_pre_ping=True)
    metadata = MetaData()

    with engine.begin() as connection:
        history = Table("update_history", metadata, autoload_with=connection)
        config = Table("system_config", metadata, autoload_with=connection)

        original = connection.execute(
            select(history.c.id).where(history.c.id == original_id)
        ).first()
        if original is None:
            raise RuntimeError(f"original update history row {original_id} is missing")

        original_values = _only_columns(
            history,
            {
                "status": "ROLLED_BACK",
                "completed_at": now,
                "duration_seconds": duration,
                "progress_heartbeat_at": now,
                "rollback_available": False,
                "error_message": None,
                "last_step": "Rolled back",
            },
        )
        connection.execute(
            update(history).where(history.c.id == original_id).values(**original_values)
        )

        existing = connection.execute(
            select(history).where(history.c.id == rollback_id)
        ).mappings().first()
        rollback_values = _only_columns(
            history,
            {
                "id": rollback_id,
                "from_version": from_version,
                "to_version": to_version,
                "update_type": "rollback",
                "channel": None,
                "status": "ROLLED_BACK",
                "started_at": started_at,
                "completed_at": now,
                "duration_seconds": duration,
                "progress_heartbeat_at": now,
                "started_by": started_by,
                "rollback_available": False,
                "backup_path": backup_path,
                "is_rollback": True,
                "rollback_of_id": original_id,
                "error_message": None,
                "log": log_text[-1_048_576:],
                "last_step": "Rolled back",
            },
        )
        if existing is None:
            connection.execute(insert(history).values(**rollback_values))
        else:
            if existing.get("rollback_of_id") not in (None, original_id):
                raise RuntimeError(f"history row {rollback_id} belongs to another operation")
            mutable = {key: value for key, value in rollback_values.items() if key != "id"}
            connection.execute(
                update(history).where(history.c.id == rollback_id).values(**mutable)
            )

        _upsert_config(
            connection,
            config,
            key="updates_auto_apply",
            value="false",
            value_type="bool",
            description="Disabled automatically after manual rollback; re-enable after review",
            updated_at=now,
        )
        _upsert_config(
            connection,
            config,
            key="updates_rollback_suppressed_version",
            value=from_version,
            value_type="string",
            description="Do not automatically reapply the version most recently rolled back",
            updated_at=now,
        )

        if connection.dialect.name == "postgresql":
            connection.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence('update_history', 'id'), "
                    "GREATEST((SELECT COALESCE(MAX(id), 1) FROM update_history), 1), true)"
                )
            )

    engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--rollback-id", required=True, type=int)
    parser.add_argument("--original-id", required=True, type=int)
    parser.add_argument("--from-version", required=True)
    parser.add_argument("--to-version", required=True)
    parser.add_argument("--started-by", default="admin")
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--backup-path", required=True)
    parser.add_argument("--log-file", required=True, type=Path)
    args = parser.parse_args()

    started_at = datetime.fromisoformat(args.started_at)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    log_text = args.log_file.read_text(errors="replace") if args.log_file.exists() else ""
    finalize_rollback(
        database_url=_database_url(args.env_file),
        rollback_id=args.rollback_id,
        original_id=args.original_id,
        from_version=args.from_version,
        to_version=args.to_version,
        started_by=args.started_by,
        started_at=started_at,
        backup_path=args.backup_path,
        log_text=log_text,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
