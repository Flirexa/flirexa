"""
Request ID + Access Log Middleware.

Every HTTP request gets a unique request_id (X-Request-ID header or UUID[:8]).
  - Echoed back in X-Request-ID response header
  - Bound into loguru context so all log entries for the request carry it
  - One access log entry per request (INFO/WARNING/ERROR by status code)

Secrets protection:
  - Authorization header value is never logged
  - Query strings are stripped before logging (may contain tokens)
"""

import time
import uuid
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Paths logged at DEBUG to reduce noise
_QUIET_PREFIXES = ("/health", "/assets/", "/favicon")


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """Attaches request_id to every request and writes a single access log entry."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        method = request.method
        path = request.url.path   # query string intentionally excluded

        start = time.monotonic()

        # Bind request_id + path into loguru context for the duration of this request.
        # All logger.* calls inside route handlers will carry these fields in JSON logs.
        with logger.contextualize(request_id=request_id, method=method, path=path):
            response = await call_next(request)

        duration_ms = round((time.monotonic() - start) * 1000)
        status_code = response.status_code

        if status_code >= 500:
            log_level = "ERROR"
        elif status_code >= 400:
            log_level = "WARNING"
        elif any(path.startswith(p) for p in _QUIET_PREFIXES):
            log_level = "DEBUG"
        else:
            log_level = "INFO"

        # One access log entry that carries all request metadata
        with logger.contextualize(
            request_id=request_id, method=method, path=path,
            status_code=status_code, duration_ms=duration_ms,
        ):
            logger.opt(depth=0).log(
                log_level,
                f"{method} {path} → {status_code} ({duration_ms}ms)",
            )

        response.headers["X-Request-ID"] = request_id
        return response
