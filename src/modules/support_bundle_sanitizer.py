from __future__ import annotations

import re
from typing import Any


_SENSITIVE_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "token",
    "license_key",
    "private_key",
    "api_key",
    "bot_token",
    "telegram",
    "payment",
    "webhook",
    "encryption_key",
    "preshared_key",
    "ssh_private_key",
    "ssh_password",
    "agent_api_key",
    "database_url",
    "dsn",
)

_STRICT_KEY_RE = re.compile(r"(^|_)(key|secret|token|password)(_|$)")
_PEM_RE = re.compile(r"-----BEGIN [A-Z0-9 ]+-----")
# Redact credentials embedded in connection URLs (postgres/redis/amqp/mongodb/…):
# scheme://user:password@host → scheme://***:***@host — catches DATABASE_URL and
# friends regardless of the key name. (security: support-bundle URL-cred leak 2026-07)
_URL_CREDS_RE = re.compile(r"([a-zA-Z][\w+.\-]*://)[^/@\s:]*:[^/@\s]+@")


def redact_url_creds(text: str) -> str:
    if not text or "://" not in text:
        return text
    return _URL_CREDS_RE.sub(r"\1***:***@", text)


def is_sensitive_key(key: str, *, strict: bool = False) -> bool:
    lowered = (key or "").strip().lower()
    if not lowered:
        return False
    if any(part in lowered for part in _SENSITIVE_SUBSTRINGS):
        return True
    if strict and _STRICT_KEY_RE.search(lowered):
        return True
    return False


def mask_secret(value: str | None) -> str:
    if not value:
        return "[REDACTED]"
    value = str(value)
    if len(value) <= 8:
        return "[REDACTED]"
    return f"{value[:2]}***{value[-2:]}"


def sanitize_value(key: str, value: Any, *, strict: bool = False) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return sanitize_mapping(value, strict=strict)
    if isinstance(value, list):
        return [sanitize_value(key, item, strict=strict) for item in value]
    if isinstance(value, tuple):
        return [sanitize_value(key, item, strict=strict) for item in value]

    text = str(value)
    if is_sensitive_key(key, strict=strict):
        return mask_secret(text)
    if _PEM_RE.search(text):
        return "[REDACTED_PEM]"
    redacted = redact_url_creds(text)
    if redacted != text:
        return redacted
    return value


def sanitize_mapping(data: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            sanitized[key] = sanitize_mapping(value, strict=strict)
        elif isinstance(value, list):
            sanitized[key] = [sanitize_value(key, item, strict=strict) for item in value]
        else:
            sanitized[key] = sanitize_value(key, value, strict=strict)
    return sanitized


def sanitize_env_text(text: str, *, strict: bool = False) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            lines.append(raw_line)
            continue
        key, value = raw_line.split("=", 1)
        if is_sensitive_key(key, strict=strict):
            lines.append(f"{key}={mask_secret(value)}")
        elif _PEM_RE.search(value):
            lines.append(f"{key}=[REDACTED_PEM]")
        else:
            lines.append(f"{key}={redact_url_creds(value)}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
