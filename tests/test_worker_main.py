from unittest.mock import MagicMock


def test_worker_monitoring_delegates_to_shared_scheduler(monkeypatch):
    import worker_main
    import src.api.scheduler as scheduler

    called = {"ok": False}

    def fake_cycle():
        called["ok"] = True

    monkeypatch.setattr(scheduler, "monitoring_cycle", fake_cycle)

    worker_main.run_monitoring_cycle()

    assert called["ok"] is True


def test_worker_backup_delegates_to_shared_scheduler(monkeypatch):
    import worker_main
    import src.api.scheduler as scheduler

    called = {"ok": False}

    def fake_cycle():
        called["ok"] = True

    monkeypatch.setattr(scheduler, "backup_cycle", fake_cycle)

    worker_main.run_backup_cycle()

    assert called["ok"] is True


def test_worker_sleep_until_next_cycle_exits_early_on_shutdown(monkeypatch):
    import worker_main

    worker_main._shutdown = False
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        worker_main._shutdown = True

    monotonic_values = iter([0.0, 0.1, 0.2])
    monkeypatch.setattr(worker_main.time, "sleep", fake_sleep)
    monkeypatch.setattr(worker_main.time, "monotonic", lambda: next(monotonic_values))

    worker_main._sleep_until_next_cycle(60)

    assert sleeps == [1.0]


def test_write_worker_heartbeat_updates_existing_row(monkeypatch):
    import worker_main

    class Row:
        def __init__(self):
            self.value = None

    row = Row()

    class Query:
        def filter(self, *_args, **_kwargs):
            return self
        def first(self):
            return row

    class DummyDB:
        def query(self, *_args, **_kwargs):
            return Query()
        def add(self, _obj):
            raise AssertionError("existing row should be updated, not inserted")
        def commit(self):
            self.committed = True
        def close(self):
            pass

    monkeypatch.setattr("src.database.connection.SessionLocal", lambda: DummyDB())

    now = worker_main.datetime(2026, 3, 28, 21, 0, 0, tzinfo=worker_main.timezone.utc)
    worker_main._write_worker_heartbeat(now)

    assert row.value == now.isoformat()
