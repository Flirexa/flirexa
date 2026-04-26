"""
Centralized JSON logging for VPN Management Studio.

Writes structured JSON logs to /var/log/vpnmanager/{component}.log
Each line: {timestamp, hostname, version, component, level, message, request_id?, method?, path?, status_code?, duration_ms?, error?}

Usage:
    from src.modules.log_config import setup_logging
    setup_logging("api")   # or "worker"
"""

import json
import os
import socket
import sys
import logging
from pathlib import Path
from typing import Optional
from loguru import logger
from src.utils.runtime_paths import get_version_file

LOG_DIR = Path(os.getenv("LOG_DIR", "/var/log/vpnmanager"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_ROTATION = "50 MB"
LOG_RETENTION = "30 days"

# Hard limit per log line to prevent runaway messages from filling disk
MAX_LINE_BYTES = 10_000
MAX_ERROR_BYTES = 2_000

# Fields that must never appear in logs
_SECRET_KEYS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "authorization", "auth", "private_key", "ssh_key", "key",
    "access_token", "refresh_token", "jwt", "credential", "credentials",
})

# Resolved once at import time — stable for the lifetime of the process
_HOSTNAME: str = socket.gethostname()

def _get_version() -> str:
    """Read VERSION file. Falls back to '0.0.0' if unavailable."""
    version_file = Path(os.getenv("VERSION_FILE", str(get_version_file())))
    try:
        return version_file.read_text().strip()
    except OSError:
        return "0.0.0"

_VERSION: str = _get_version()


def _json_serializer(record: dict, component: str) -> str:
    """Format a loguru record as a single-line JSON entry."""
    msg = record["message"]
    if len(msg) > MAX_LINE_BYTES:
        msg = msg[:MAX_LINE_BYTES] + " [truncated]"

    entry: dict = {
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hostname": _HOSTNAME,
        "version": _VERSION,
        "component": component,
        "level": record["level"].name,
        "message": msg,
    }

    # Contextual request fields — present only when set via logger.contextualize()
    extra = record.get("extra", {})
    for key in ("request_id", "method", "path", "status_code", "duration_ms"):
        if key in extra:
            entry[key] = extra[key]

    # Exception — cap length, never expose raw stack frames in the "error" key
    exc = record.get("exception")
    if exc is not None and exc.value is not None:
        err_str = str(exc.value)
        if len(err_str) > MAX_ERROR_BYTES:
            err_str = err_str[:MAX_ERROR_BYTES] + " [truncated]"
        entry["error"] = err_str

    return json.dumps(entry, ensure_ascii=False) + "\n"


def _make_file_sink(path: str, component: str):
    """Return a callable loguru sink that appends JSON Lines to *path*."""
    import threading
    _lock = threading.Lock()

    def sink(message):
        line = _json_serializer(message.record, component)
        with _lock:
            try:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(line)
            except OSError:
                pass  # Ignore write errors (disk full, etc.)

    return sink


class InterceptHandler(logging.Handler):
    """Bridge standard logging → loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(component: str, level: Optional[str] = None) -> None:
    """
    Configure loguru for the given component.

    - Stderr sink: human-readable colored output
    - File sink:   /var/log/vpnmanager/{component}.log in JSON Lines format
                   Falls back silently if directory is not writable.
    - Intercepts standard `logging` module so third-party libs use loguru.

    Args:
        component: "api", "worker", or "agent"
        level:     override LOG_LEVEL env var
    """
    log_level = level or LOG_LEVEL

    logger.remove()

    # --- Stderr (human-readable) ---
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            f"<cyan>{component}</cyan> | "
            "<level>{message}</level>"
        ),
        level=log_level,
        backtrace=False,
        diagnose=False,
    )

    # --- File (JSON Lines) ---
    # Use a callable sink so loguru never tries to format_map our JSON string.
    log_file = LOG_DIR / f"{component}.log"
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logger.add(
            _make_file_sink(str(log_file), component),
            level=log_level,
            backtrace=False,
            diagnose=False,
        )
        logger.debug(f"JSON log: {log_file}")
    except (PermissionError, OSError) as exc:
        logger.warning(f"Cannot write to {log_file}: {exc} — file logging disabled")

    # --- Intercept stdlib logging ---
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "sqlalchemy"):
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False


def get_recent_logs(component: str = "api", lines: int = 100,
                    errors_only: bool = False) -> list:
    """
    Read the last *lines* entries from /var/log/vpnmanager/{component}.log.

    Args:
        component:   "api", "worker", or "agent"
        lines:       max entries to return
        errors_only: if True, return only ERROR and CRITICAL entries

    Returns a list of parsed JSON dicts (newest last).
    Returns an empty list if the file does not exist or is unreadable.
    """
    log_file = LOG_DIR / f"{component}.log"
    if not log_file.exists():
        return []

    try:
        # Efficient tail: read at most 4 MB from the end
        with open(log_file, "rb") as fh:
            fh.seek(0, 2)
            file_size = fh.tell()
            chunk_size = min(file_size, 4 * 1024 * 1024)
            fh.seek(-chunk_size, 2)
            raw = fh.read(chunk_size).decode("utf-8", errors="replace")

        raw_lines = raw.splitlines()

        result = []
        for line in reversed(raw_lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if errors_only and entry.get("level") not in ("ERROR", "CRITICAL"):
                continue
            result.append(entry)
            if len(result) >= lines:
                break

        result.reverse()  # return oldest-first
        return result
    except OSError:
        return []
