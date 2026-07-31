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


@pytest.mark.asyncio
async def test_online_check_reports_runtime_version_without_env_override(monkeypatch):
    seen = {}

    monkeypatch.setenv("LICENSE_KEY", "payload.signature")
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setattr(ov, "_SERVER_URL", "https://example.com")
    monkeypatch.setattr(ov, "_SERVER_URL_BACKUP", "")
    monkeypatch.setattr(ov, "_get_hardware_id", lambda: "test-hardware")
    monkeypatch.setattr(ov, "get_app_version", lambda: "2.2.82")

    async def fake_try_server(url, payload, *, accept_negative_status):
        seen["url"] = url
        seen["payload"] = payload
        seen["accept_negative_status"] = accept_negative_status
        return True

    monkeypatch.setattr(ov, "_try_server", fake_try_server)

    await ov._do_check()

    assert seen["url"] == "https://example.com"
    assert seen["payload"]["client_version"] == "2.2.82"
    assert seen["accept_negative_status"] is True
