import pytest

from src.modules.license import online_validator as ov


@pytest.mark.asyncio
async def test_run_single_check_warms_cache_and_runs_check(monkeypatch):
    payload = {"status": "ok", "tier": "pro"}
    seen = {"apply": 0, "check": 0}

    monkeypatch.setattr(ov, "_SERVER_URL", "https://example.com")
    monkeypatch.setattr(ov, "_SERVER_URL_BACKUP", "")
    monkeypatch.setattr(ov, "_load_cache", lambda: payload)

    def fake_apply(p):
        seen["apply"] += 1
        assert p == payload

    async def fake_do_check():
        seen["check"] += 1

    monkeypatch.setattr(ov, "_apply_payload", fake_apply)
    monkeypatch.setattr(ov, "_do_check", fake_do_check)

    result = await ov.run_single_check(warm_cache=True)

    assert result is True
    assert seen == {"apply": 1, "check": 1}
