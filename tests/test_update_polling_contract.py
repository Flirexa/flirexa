"""Regression contracts for quiet, authoritative update polling."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_admin_shell_update_badges_are_explicitly_silent():
    design2 = _read("src/web/frontend/src/design2/shell/D2Shell.vue")

    assert "api.get('/updates/status', { timeout: 10000, silent: true })" in design2


def test_expected_restart_probe_is_silent():
    updates = _read("src/web/frontend/src/design2/screens/D2Updates.vue")
    assert "api.get('/updates/status', { timeout: 4000, silent: true })" in updates


def test_online_users_poll_is_silent_hidden_aware_and_has_narrow_fallback():
    online = _read("src/web/frontend/src/design2/screens/D2OnlineUsers.vue")

    assert "setInterval(() => silentPoll(refresh)" in online
    assert "document.hidden" in online
    assert "document.addEventListener('visibilitychange', onVisibilityChange)" in online
    assert "error?.response?.status === 404" in online
    assert "clientsApi.getOnline().catch(() => clientsApi.getAll())" not in online


@pytest.mark.asyncio
async def test_normal_autocheck_still_forces_network_and_applies():
    from src.modules.updates import auto_check

    manifest = {"version": "9.9.9"}
    checker = AsyncMock(return_value=(manifest, None))
    apply_update = AsyncMock()

    with patch("src.modules.updates.checker.check_for_update", new=checker), patch(
        "src.modules.updates.manager.get_current_version", return_value="1.0.0"
    ), patch.object(auto_check, "_get_channel", return_value="stable"), patch.object(
        auto_check, "_try_auto_apply", new=apply_update
    ):
        had_failure = await auto_check._run_one_check()

    assert had_failure is False
    checker.assert_awaited_once_with("1.0.0", "stable", force=True)
    apply_update.assert_awaited_once_with(manifest, "1.0.0", "stable")


@pytest.mark.asyncio
async def test_mandatory_watcher_still_forces_network_and_applies():
    from src.modules.updates import auto_check

    manifest = {"version": "9.9.9", "mandatory": True}
    checker = AsyncMock(return_value=(manifest, None))
    apply_update = AsyncMock()

    with patch("src.modules.updates.checker.check_for_update", new=checker), patch(
        "src.modules.updates.manager.get_current_version", return_value="1.0.0"
    ), patch.object(auto_check, "_get_channel", return_value="test"), patch.object(
        auto_check, "_try_auto_apply", new=apply_update
    ):
        await auto_check._run_one_mandatory_check()

    checker.assert_awaited_once_with("1.0.0", "test", force=True)
    apply_update.assert_awaited_once_with(manifest, "1.0.0", "test")
