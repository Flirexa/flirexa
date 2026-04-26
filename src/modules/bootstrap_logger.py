"""
VPN Management Studio — Bootstrap Progress Logger

Provides a thread-safe task registry for tracking proxy server bootstrap
progress (binary install, cert generation, service start).

Tasks are stored both in-memory (for low-latency polling) AND in the
server_bootstrap_logs table so they survive API restarts.

On API startup, any tasks still in "running" state are marked "interrupted"
so the frontend receives an honest status rather than a stale spinner.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List


@dataclass
class BootstrapTask:
    task_id: str
    _logs: List[str] = field(default_factory=list)
    _complete: bool = False
    _error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def log(self, message: str) -> None:
        """Append a log line (called from bootstrap thread)."""
        with self._lock:
            self._logs.append(message)
        _db_append_log(self.task_id, message)

    def get_logs_since(self, index: int) -> List[str]:
        """Return log lines from index onward (thread-safe snapshot)."""
        with self._lock:
            return list(self._logs[index:])

    @property
    def complete(self) -> bool:
        with self._lock:
            return self._complete

    @property
    def error(self) -> Optional[str]:
        with self._lock:
            return self._error

    def finish(self, error: Optional[str] = None) -> None:
        """Mark task complete (success or failure)."""
        with self._lock:
            self._complete = True
            self._error = error
        _db_finish(self.task_id, error)


# ─── Global registry ──────────────────────────────────────────────────────────

_tasks: dict = {}
_registry_lock = threading.Lock()
_TASK_TTL = 1800  # 30 minutes


def create_task(task_id: str, server_id: Optional[int] = None) -> BootstrapTask:
    """Register a new bootstrap task and persist it to DB."""
    task = BootstrapTask(task_id=task_id)
    with _registry_lock:
        _tasks[task_id] = task
        _cleanup_expired()
    _db_create(task_id, server_id)
    return task


def attach_task_server(task_id: str, server_id: int) -> None:
    """Bind an existing bootstrap task to a server once the DB record exists."""
    try:
        from src.database.connection import SessionLocal
        from src.database.models import ServerBootstrapLog
        db = SessionLocal()
        try:
            rec = db.query(ServerBootstrapLog).filter_by(task_id=task_id).first()
            if rec and rec.server_id != server_id:
                rec.server_id = server_id
                db.commit()
        finally:
            db.close()
    except Exception:
        pass


def get_task(task_id: str) -> Optional[BootstrapTask]:
    """Return task by ID. Checks memory first, then DB for post-restart recovery."""
    with _registry_lock:
        t = _tasks.get(task_id)
    if t is not None:
        return t
    # Not in memory — try to reconstruct from DB (API may have restarted)
    return _db_load(task_id)


def _cleanup_expired() -> None:
    """Remove tasks older than TTL. Must be called with _registry_lock held."""
    now = time.time()
    expired = [k for k, v in _tasks.items() if now - v.created_at > _TASK_TTL]
    for k in expired:
        del _tasks[k]


# ─── DB helpers (best-effort, never raise) ────────────────────────────────────

def _db_create(task_id: str, server_id: Optional[int]) -> None:
    try:
        from src.database.connection import SessionLocal
        from src.database.models import ServerBootstrapLog
        db = SessionLocal()
        try:
            rec = ServerBootstrapLog(task_id=task_id, server_id=server_id, status="running")
            db.add(rec)
            db.commit()
        finally:
            db.close()
    except Exception:
        pass  # DB not available yet during tests / first boot


def _db_append_log(task_id: str, message: str) -> None:
    try:
        from src.database.connection import SessionLocal
        from src.database.models import ServerBootstrapLog
        db = SessionLocal()
        try:
            rec = db.query(ServerBootstrapLog).filter_by(task_id=task_id).first()
            if rec:
                rec.logs = (rec.logs or "") + message + "\n"
                db.commit()
        finally:
            db.close()
    except Exception:
        pass


def _db_finish(task_id: str, error: Optional[str]) -> None:
    try:
        from src.database.connection import SessionLocal
        from src.database.models import ServerBootstrapLog
        db = SessionLocal()
        try:
            rec = db.query(ServerBootstrapLog).filter_by(task_id=task_id).first()
            if rec:
                rec.status = "failed" if error else "complete"
                rec.error = error
                rec.completed_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()
    except Exception:
        pass


def _db_load(task_id: str) -> Optional[BootstrapTask]:
    """Reconstruct a BootstrapTask from DB record (read-only, not added to registry)."""
    try:
        from src.database.connection import SessionLocal
        from src.database.models import ServerBootstrapLog
        db = SessionLocal()
        try:
            rec = db.query(ServerBootstrapLog).filter_by(task_id=task_id).first()
            if not rec:
                return None
            task = BootstrapTask(task_id=task_id)
            task._logs = (rec.logs or "").splitlines() if rec.logs else []
            task._complete = rec.status in ("complete", "failed", "interrupted")
            task._error = rec.error
            return task
        finally:
            db.close()
    except Exception:
        return None


def mark_interrupted_tasks() -> None:
    """
    On API startup: mark any 'running' bootstrap tasks as 'interrupted'.
    The bootstrap thread is gone after restart — it's honest to say so.
    """
    try:
        from src.database.connection import SessionLocal
        from src.database.models import (
            ServerBootstrapLog,
            Server,
            ServerStatus,
            ServerLifecycleStatus,
            AuditLog,
            AuditAction,
        )
        db = SessionLocal()
        try:
            running = db.query(ServerBootstrapLog).filter_by(status="running").all()
            now = datetime.now(timezone.utc)
            for rec in running:
                rec.status = "interrupted"
                rec.error = "Bootstrap interrupted: API was restarted"
                rec.completed_at = now
                if rec.server_id:
                    server = db.get(Server, rec.server_id)
                    if server and server.status not in (ServerStatus.ONLINE, ServerStatus.ERROR):
                        old_status = server.status
                        old_lifecycle_status = server.effective_lifecycle_status
                        server.status = ServerStatus.ERROR
                        server.lifecycle_status = ServerLifecycleStatus.FAILED.value
                        db.add(AuditLog(
                            user_type="system",
                            action=AuditAction.SERVER_STATUS_CHANGE,
                            target_type="server",
                            target_id=server.id,
                            target_name=server.name,
                            details={
                                "old_status": old_status.value if old_status else None,
                                "new_status": ServerStatus.ERROR.value,
                                "old_lifecycle_status": old_lifecycle_status,
                                "new_lifecycle_status": ServerLifecycleStatus.FAILED.value,
                                "reason": "bootstrap_interrupted_on_api_restart",
                            },
                        ))
            if running:
                db.commit()
        finally:
            db.close()
    except Exception:
        pass
