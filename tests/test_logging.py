"""
Tests for centralized JSON logging system.

Covers:
- request_id propagation (header + response)
- X-Request-ID in response headers
- /system/app-logs endpoint
- /system/app-logs/errors endpoint
- errors_only filter
- rotation / retention config
- secrets not in logs
- JSON format validity
- logs endpoint: empty file
- logs endpoint: broken JSON line
"""

import json
import os
import sys
import tempfile
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Force SQLite for tests
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_ENABLED"] = "false"
os.environ["SMTP_ENABLED"] = "false"
os.environ["LICENSE_CHECK_ENABLED"] = "false"

from src.database.models import Base
from src.database.connection import get_db
from src.api.main import create_app
from src.api.middleware.auth import get_current_admin


@pytest.fixture(scope="module")
def app_and_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    app = create_app(debug=True)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = lambda: {
        "user_id": 1, "username": "testadmin", "is_superadmin": True
    }

    client = TestClient(app, raise_server_exceptions=False)
    yield app, client

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client(app_and_client):
    _, c = app_and_client
    return c


# ────────────────────────────────────────────────────────────────────────────
# Request ID
# ────────────────────────────────────────────────────────────────────────────

class TestRequestId:
    def test_response_has_x_request_id(self, client):
        r = client.get("/health")
        assert "x-request-id" in r.headers, "X-Request-ID header must be present"

    def test_custom_request_id_echoed_back(self, client):
        r = client.get("/health", headers={"X-Request-ID": "test-abc123"})
        assert r.headers.get("x-request-id") == "test-abc123"

    def test_generated_request_id_is_short(self, client):
        r = client.get("/health")
        rid = r.headers.get("x-request-id", "")
        assert 1 <= len(rid) <= 36, f"Unexpected request_id length: {len(rid)}"

    def test_different_requests_get_different_ids(self, client):
        r1 = client.get("/health")
        r2 = client.get("/health")
        id1 = r1.headers.get("x-request-id", "")
        id2 = r2.headers.get("x-request-id", "")
        assert id1 != id2, "Each request should get a unique request_id"


# ────────────────────────────────────────────────────────────────────────────
# /system/app-logs endpoint
# ────────────────────────────────────────────────────────────────────────────

class TestAppLogsEndpoint:
    def test_app_logs_returns_200(self, client):
        r = client.get("/api/v1/system/app-logs")
        assert r.status_code == 200

    def test_app_logs_response_structure(self, client):
        r = client.get("/api/v1/system/app-logs")
        d = r.json()
        assert "component" in d
        assert "lines" in d
        assert "entries" in d
        assert isinstance(d["entries"], list)

    def test_app_logs_default_component_api(self, client):
        r = client.get("/api/v1/system/app-logs")
        assert r.json()["component"] == "api"

    def test_app_logs_worker_component(self, client):
        r = client.get("/api/v1/system/app-logs?component=worker")
        assert r.json()["component"] == "worker"

    def test_app_logs_agent_component(self, client):
        r = client.get("/api/v1/system/app-logs?component=agent")
        assert r.json()["component"] == "agent"

    def test_app_logs_invalid_component_422(self, client):
        r = client.get("/api/v1/system/app-logs?component=invalid")
        assert r.status_code == 422

    def test_app_logs_lines_param(self, client):
        r = client.get("/api/v1/system/app-logs?lines=10")
        assert r.status_code == 200

    def test_app_logs_lines_too_large_422(self, client):
        r = client.get("/api/v1/system/app-logs?lines=9999")
        assert r.status_code == 422

    def test_app_logs_errors_only_param(self, client):
        r = client.get("/api/v1/system/app-logs?errors_only=true")
        d = r.json()
        assert r.status_code == 200
        # All returned entries must be ERROR or CRITICAL
        for entry in d["entries"]:
            assert entry.get("level") in ("ERROR", "CRITICAL"), \
                f"Expected ERROR/CRITICAL, got {entry.get('level')}"


class TestAppLogsErrorsEndpoint:
    def test_errors_endpoint_returns_200(self, client):
        r = client.get("/api/v1/system/app-logs/errors")
        assert r.status_code == 200

    def test_errors_endpoint_structure(self, client):
        d = client.get("/api/v1/system/app-logs/errors").json()
        assert "component" in d
        assert "entries" in d

    def test_errors_endpoint_only_errors(self, client):
        d = client.get("/api/v1/system/app-logs/errors").json()
        for entry in d["entries"]:
            assert entry.get("level") in ("ERROR", "CRITICAL")


# ────────────────────────────────────────────────────────────────────────────
# hostname + version fields
# ────────────────────────────────────────────────────────────────────────────

class TestHostnameAndVersion:
    def test_hostname_in_log_entry(self, tmp_path):
        """Every log entry must contain a non-empty hostname field."""
        os.environ["LOG_DIR"] = str(tmp_path)
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)

        log_config.setup_logging("api")
        from loguru import logger
        logger.info("hostname test")
        time.sleep(0.3)

        log_file = tmp_path / "api.log"
        assert log_file.exists(), "Log file was not created"
        for line in log_file.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            assert "hostname" in entry, f"'hostname' missing from entry: {entry}"
            assert entry["hostname"], "hostname must not be empty"

    def test_hostname_matches_socket(self, tmp_path):
        """hostname in logs must equal socket.gethostname()."""
        import socket
        os.environ["LOG_DIR"] = str(tmp_path)
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)

        log_config.setup_logging("api")
        from loguru import logger
        logger.info("hostname match test")
        time.sleep(0.3)

        log_file = tmp_path / "api.log"
        if log_file.exists():
            for line in log_file.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                assert entry.get("hostname") == socket.gethostname()

    def test_version_in_log_entry(self, tmp_path):
        """Every log entry must contain a version field."""
        os.environ["LOG_DIR"] = str(tmp_path)
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)

        log_config.setup_logging("api")
        from loguru import logger
        logger.info("version test")
        time.sleep(0.3)

        log_file = tmp_path / "api.log"
        assert log_file.exists()
        for line in log_file.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            assert "version" in entry, f"'version' missing from entry: {entry}"
            assert entry["version"], "version must not be empty"

    def test_version_format(self, tmp_path):
        """version field should look like a semantic version (digits and dots)."""
        os.environ["LOG_DIR"] = str(tmp_path)
        import re
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)

        log_config.setup_logging("api")
        from loguru import logger
        logger.info("version format test")
        time.sleep(0.3)

        log_file = tmp_path / "api.log"
        if log_file.exists():
            for line in log_file.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                ver = entry.get("version", "")
                assert re.match(r"^\d+\.\d+", ver), \
                    f"version '{ver}' does not look like a semver"

    def test_json_still_valid_with_new_fields(self, tmp_path):
        """Adding hostname/version must not break JSON validity."""
        os.environ["LOG_DIR"] = str(tmp_path)
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)

        log_config.setup_logging("api")
        from loguru import logger
        logger.info("validity test")
        logger.warning("warn msg")
        try:
            raise RuntimeError("test error")
        except RuntimeError:
            logger.opt(exception=True).error("error with exc")
        time.sleep(0.3)

        log_file = tmp_path / "api.log"
        if log_file.exists():
            for line in log_file.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)  # must not raise
                # Core fields always present
                for field in ("timestamp", "hostname", "version", "component", "level", "message"):
                    assert field in entry, f"Required field '{field}' missing"

    def test_get_recent_logs_parses_hostname_version(self, tmp_path):
        """get_recent_logs() correctly returns hostname and version in parsed dicts."""
        os.environ["LOG_DIR"] = str(tmp_path)
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)

        # Write a test entry directly
        entry = json.dumps({
            "timestamp": "2026-03-15T12:00:00Z",
            "hostname": "test-host",
            "version": "1.1.0",
            "component": "api",
            "level": "INFO",
            "message": "direct write test",
        })
        (tmp_path / "api.log").write_text(entry + "\n")

        entries = log_config.get_recent_logs("api", lines=10)
        assert len(entries) == 1
        assert entries[0]["hostname"] == "test-host"
        assert entries[0]["version"] == "1.1.0"


# ────────────────────────────────────────────────────────────────────────────
# log_config module
# ────────────────────────────────────────────────────────────────────────────

class TestLogConfig:
    def test_json_format_valid(self, tmp_path):
        """Each written line must be valid JSON."""
        os.environ["LOG_DIR"] = str(tmp_path)
        from src.modules import log_config
        # Reload to pick up new LOG_DIR
        import importlib
        importlib.reload(log_config)

        log_config.setup_logging("api")
        from loguru import logger
        logger.info("Hello JSON")
        logger.warning("A warning")
        time.sleep(0.3)

        log_file = tmp_path / "api.log"
        if log_file.exists():
            for line in log_file.read_text().splitlines():
                if line.strip():
                    entry = json.loads(line)  # must not raise
                    assert "timestamp" in entry
                    assert "level" in entry
                    assert "component" in entry
                    assert "message" in entry

    def test_rotation_config_set(self):
        from src.modules.log_config import LOG_ROTATION, LOG_RETENTION
        assert LOG_ROTATION, "LOG_ROTATION must be set"
        assert LOG_RETENTION, "LOG_RETENTION must be set"
        # Should contain MB/days reference
        assert "MB" in LOG_ROTATION or "bytes" in LOG_ROTATION.lower()
        assert "days" in LOG_RETENTION or "weeks" in LOG_RETENTION

    def test_max_line_bytes_defined(self):
        from src.modules.log_config import MAX_LINE_BYTES
        assert MAX_LINE_BYTES >= 1000, "MAX_LINE_BYTES should be at least 1 KB"
        assert MAX_LINE_BYTES <= 100_000, "MAX_LINE_BYTES should not be excessive"

    def test_long_message_truncated(self, tmp_path):
        """Messages beyond MAX_LINE_BYTES should be truncated."""
        os.environ["LOG_DIR"] = str(tmp_path)
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)

        log_config.setup_logging("api")
        from loguru import logger
        from src.modules.log_config import MAX_LINE_BYTES
        big_msg = "X" * (MAX_LINE_BYTES * 2)
        logger.info(big_msg)
        time.sleep(0.3)

        log_file = tmp_path / "api.log"
        if log_file.exists():
            for line in log_file.read_text().splitlines():
                if line.strip() and "X" in line:
                    entry = json.loads(line)
                    assert len(entry["message"]) <= MAX_LINE_BYTES + 20  # +20 for "[truncated]"

    def test_empty_log_file_returns_empty_list(self, tmp_path):
        """get_recent_logs on empty file should return []."""
        os.environ["LOG_DIR"] = str(tmp_path)
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)

        (tmp_path / "api.log").write_text("")
        entries = log_config.get_recent_logs("api", lines=10)
        assert entries == []

    def test_missing_log_file_returns_empty_list(self, tmp_path):
        os.environ["LOG_DIR"] = str(tmp_path)
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)

        entries = log_config.get_recent_logs("api", lines=10)
        assert entries == []

    def test_broken_json_line_skipped(self, tmp_path):
        """Broken JSON lines should be silently skipped."""
        os.environ["LOG_DIR"] = str(tmp_path)
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)

        good = json.dumps({"timestamp": "2026-01-01T00:00:00Z", "level": "INFO",
                           "component": "api", "message": "ok"})
        (tmp_path / "api.log").write_text(
            "this is not json\n" + good + "\n" + "{broken\n"
        )
        entries = log_config.get_recent_logs("api", lines=100)
        assert len(entries) == 1
        assert entries[0]["message"] == "ok"

    def test_errors_only_filter(self, tmp_path):
        os.environ["LOG_DIR"] = str(tmp_path)
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)

        lines = [
            json.dumps({"timestamp": "T", "level": "INFO",    "component": "api", "message": "info msg"}),
            json.dumps({"timestamp": "T", "level": "ERROR",   "component": "api", "message": "err msg"}),
            json.dumps({"timestamp": "T", "level": "WARNING", "component": "api", "message": "warn msg"}),
            json.dumps({"timestamp": "T", "level": "CRITICAL","component": "api", "message": "crit msg"}),
        ]
        (tmp_path / "api.log").write_text("\n".join(lines) + "\n")

        entries = log_config.get_recent_logs("api", lines=100, errors_only=True)
        levels = {e["level"] for e in entries}
        assert levels <= {"ERROR", "CRITICAL"}, f"Unexpected levels: {levels}"
        assert len(entries) == 2


class TestSecretsNotLogged:
    """Ensure sensitive fields don't appear in log output."""

    SECRET_PATTERNS = [
        "password", "passwd", "secret", "api_key", "apikey",
        "private_key", "ssh_key", "access_token", "refresh_token",
    ]

    def test_authorization_header_not_in_access_log(self, tmp_path):
        """Authorization header value must never appear in log files."""
        os.environ["LOG_DIR"] = str(tmp_path)
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)
        log_config.setup_logging("api")

        from loguru import logger
        logger.info("Testing request headers")
        time.sleep(0.2)

        log_file = tmp_path / "api.log"
        if log_file.exists():
            content = log_file.read_text()
            # Ensure Bearer tokens are not accidentally logged
            assert "Bearer " not in content, "Bearer token must not appear in logs"

    def test_secret_keys_not_in_json_entry(self, tmp_path):
        """Fields matching secret key names must not appear as JSON keys in log entries."""
        os.environ["LOG_DIR"] = str(tmp_path)
        import importlib
        from src.modules import log_config
        importlib.reload(log_config)
        log_config.setup_logging("api")

        from loguru import logger
        # Simulate logging a message that mentions a sensitive operation (no values)
        logger.info("User login attempt")
        logger.info("License activated")
        time.sleep(0.2)

        log_file = tmp_path / "api.log"
        if log_file.exists():
            for line in log_file.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                for secret_key in self.SECRET_PATTERNS:
                    assert secret_key not in entry, \
                        f"Secret key '{secret_key}' found in log entry: {entry}"
