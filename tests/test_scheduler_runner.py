from src.api.scheduler_runner import validate_scheduler_standalone_mode


def test_scheduler_runner_refuses_when_worker_enabled(monkeypatch):
    monkeypatch.setenv("WORKER_ENABLED", "true")
    monkeypatch.setenv("SCHEDULER_IN_API", "false")
    monkeypatch.setenv("SCHEDULER_STANDALONE_ENABLED", "true")

    ok, reason = validate_scheduler_standalone_mode()

    assert ok is False
    assert "WORKER_ENABLED=true" in reason


def test_scheduler_runner_refuses_when_api_scheduler_still_enabled(monkeypatch):
    monkeypatch.setenv("WORKER_ENABLED", "false")
    monkeypatch.setenv("SCHEDULER_IN_API", "true")
    monkeypatch.setenv("SCHEDULER_STANDALONE_ENABLED", "true")

    ok, reason = validate_scheduler_standalone_mode()

    assert ok is False
    assert "SCHEDULER_IN_API=true" in reason


def test_scheduler_runner_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("WORKER_ENABLED", "false")
    monkeypatch.setenv("SCHEDULER_IN_API", "false")
    monkeypatch.setenv("SCHEDULER_STANDALONE_ENABLED", "false")

    ok, reason = validate_scheduler_standalone_mode()

    assert ok is False
    assert "SCHEDULER_STANDALONE_ENABLED=true" in reason


def test_scheduler_runner_allows_only_explicit_standalone_mode(monkeypatch):
    monkeypatch.setenv("WORKER_ENABLED", "false")
    monkeypatch.setenv("SCHEDULER_IN_API", "false")
    monkeypatch.setenv("SCHEDULER_STANDALONE_ENABLED", "true")

    ok, reason = validate_scheduler_standalone_mode()

    assert ok is True
    assert "validated" in reason
