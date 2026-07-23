"""Regression coverage for CLI-driven fresh database initialization."""

import os
import subprocess
import sys
from pathlib import Path


def test_connection_registers_cross_module_foreign_keys_in_clean_process():
    """The init-db CLI must resolve models without FastAPI import side effects."""
    project_root = Path(__file__).resolve().parents[1]
    code = """
from src.database.connection import _register_all_model_metadata
from src.database.models import Base, FcmToken

_register_all_model_metadata()
assert "client_users" in Base.metadata.tables
assert "fcm_tokens" in Base.metadata.tables
user_fk = next(iter(FcmToken.__table__.c.user_id.foreign_keys))
assert user_fk.column.table.name == "client_users"
"""
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite://"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=project_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
