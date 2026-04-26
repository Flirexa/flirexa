import os

from src.api.main import _should_run_in_process_background_tasks


def test_scheduler_runs_in_process_by_default(monkeypatch):
    monkeypatch.delenv("WORKER_ENABLED", raising=False)
    monkeypatch.delenv("SCHEDULER_IN_API", raising=False)

    enabled, reason = _should_run_in_process_background_tasks()

    assert enabled is True
    assert "Starting in-process" in reason


def test_worker_disables_in_process_scheduler(monkeypatch):
    monkeypatch.setenv("WORKER_ENABLED", "true")
    monkeypatch.delenv("SCHEDULER_IN_API", raising=False)

    enabled, reason = _should_run_in_process_background_tasks()

    assert enabled is False
    assert "WORKER_ENABLED=true" in reason


def test_scheduler_can_be_disabled_without_worker(monkeypatch):
    monkeypatch.setenv("WORKER_ENABLED", "false")
    monkeypatch.setenv("SCHEDULER_IN_API", "false")

    enabled, reason = _should_run_in_process_background_tasks()

    assert enabled is False
    assert "SCHEDULER_IN_API=false" in reason
