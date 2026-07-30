"""Tests for mandatory (forced) updates.

Covers:
  - the signed `mandatory` field survives signature verification and is tamper-evident
  - `_try_auto_apply` bypasses ONLY the auto-apply-off gate when mandatory
  - every other safety gate (in-flight, maintenance, 24h cooldown) still holds for mandatory
  - the fast watcher acts on mandatory manifests only
  - `_mandatory_interval()` default + env + floor
"""
import pytest
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

from tests.test_updates import _make_key_pair, _sign, _make_manifest


def _apply_env(auto_apply=False, is_newer=True, active=False, maintenance=False, recent_failed=False):
    """Patch every dependency of `_try_auto_apply` and return (ExitStack, apply_mock).

    The apply is an AsyncMock; assert on whether it was awaited to know if the
    gates let the update through.
    """
    from src.modules.updates import auto_check

    stack = ExitStack()
    apply_mock = AsyncMock(return_value=999)
    db = MagicMock()
    # cooldown query: db.query(...).filter(...).order_by(...).first()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        MagicMock() if recent_failed else None
    )
    stack.enter_context(patch.object(auto_check, "_auto_apply_enabled", return_value=auto_apply))
    stack.enter_context(patch.object(auto_check, "_rollback_suppressed_version", return_value=None))
    stack.enter_context(patch("src.modules.updates.manager.apply_update", apply_mock))
    stack.enter_context(patch("src.modules.updates.checker.is_newer", return_value=is_newer))
    stack.enter_context(patch("src.modules.operational_mode.get_active_update_state",
                              return_value=(active, None, 7 if active else None)))
    stack.enter_context(patch("src.modules.operational_mode.get_explicit_maintenance_state",
                              return_value=MagicMock(enabled=maintenance)))
    stack.enter_context(patch("src.database.connection.SessionLocal", return_value=db))
    return stack, apply_mock


class TestMandatoryGate:

    @pytest.mark.asyncio
    async def test_manual_rollback_suppresses_same_version_even_if_mandatory(self):
        from src.modules.updates import auto_check
        from src.modules.updates.auto_check import _try_auto_apply

        stack, apply_mock = _apply_env(auto_apply=False)
        stack.enter_context(
            patch.object(auto_check, "_rollback_suppressed_version", return_value="9.9.9")
        )
        with stack:
            await _try_auto_apply(
                {"version": "9.9.9", "mandatory": True}, "1.0.0", "stable"
            )
        apply_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mandatory_forces_when_autoapply_off(self):
        from src.modules.updates.auto_check import _try_auto_apply
        stack, apply_mock = _apply_env(auto_apply=False)
        with stack:
            await _try_auto_apply({"version": "9.9.9", "mandatory": True}, "1.0.0", "stable")
        apply_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_nonmandatory_skips_when_autoapply_off(self):
        from src.modules.updates.auto_check import _try_auto_apply
        stack, apply_mock = _apply_env(auto_apply=False)
        with stack:
            await _try_auto_apply({"version": "9.9.9"}, "1.0.0", "stable")
        apply_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_normal_autoapply_still_works(self):
        # regression: non-mandatory + auto-apply ON must still apply
        from src.modules.updates.auto_check import _try_auto_apply
        stack, apply_mock = _apply_env(auto_apply=True)
        with stack:
            await _try_auto_apply({"version": "9.9.9"}, "1.0.0", "stable")
        apply_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mandatory_respects_inflight(self):
        from src.modules.updates.auto_check import _try_auto_apply
        stack, apply_mock = _apply_env(auto_apply=False, active=True)
        with stack:
            await _try_auto_apply({"version": "9.9.9", "mandatory": True}, "1.0.0", "stable")
        apply_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mandatory_respects_maintenance(self):
        from src.modules.updates.auto_check import _try_auto_apply
        stack, apply_mock = _apply_env(auto_apply=False, maintenance=True)
        with stack:
            await _try_auto_apply({"version": "9.9.9", "mandatory": True}, "1.0.0", "stable")
        apply_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mandatory_respects_failure_cooldown(self):
        from src.modules.updates.auto_check import _try_auto_apply
        stack, apply_mock = _apply_env(auto_apply=False, recent_failed=True)
        with stack:
            await _try_auto_apply({"version": "9.9.9", "mandatory": True}, "1.0.0", "stable")
        apply_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mandatory_skips_when_not_newer(self):
        from src.modules.updates.auto_check import _try_auto_apply
        stack, apply_mock = _apply_env(auto_apply=False, is_newer=False)
        with stack:
            await _try_auto_apply({"version": "0.0.1", "mandatory": True}, "9.9.9", "stable")
        apply_mock.assert_not_awaited()


class TestMandatoryWatcher:

    @pytest.mark.asyncio
    async def test_watcher_forces_mandatory(self):
        from src.modules.updates import auto_check
        manifest = {"version": "9.9.9", "mandatory": True}
        with patch("src.modules.updates.checker.check_for_update",
                   new=AsyncMock(return_value=(manifest, None))), \
             patch("src.modules.updates.manager.get_current_version", return_value="1.0.0"), \
             patch.object(auto_check, "_get_channel", return_value="stable"), \
             patch.object(auto_check, "_try_auto_apply", new=AsyncMock()) as apply_mock:
            await auto_check._run_one_mandatory_check()
            apply_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_watcher_ignores_nonmandatory(self):
        from src.modules.updates import auto_check
        manifest = {"version": "9.9.9"}  # no mandatory flag
        with patch("src.modules.updates.checker.check_for_update",
                   new=AsyncMock(return_value=(manifest, None))), \
             patch("src.modules.updates.manager.get_current_version", return_value="1.0.0"), \
             patch.object(auto_check, "_get_channel", return_value="stable"), \
             patch.object(auto_check, "_try_auto_apply", new=AsyncMock()) as apply_mock:
            await auto_check._run_one_mandatory_check()
            apply_mock.assert_not_awaited()

    def test_interval_default_env_and_floor(self, monkeypatch):
        from src.modules.updates import auto_check
        monkeypatch.delenv("MANDATORY_UPDATE_CHECK_INTERVAL", raising=False)
        assert auto_check._mandatory_interval() == 300
        monkeypatch.setenv("MANDATORY_UPDATE_CHECK_INTERVAL", "600")
        assert auto_check._mandatory_interval() == 600
        monkeypatch.setenv("MANDATORY_UPDATE_CHECK_INTERVAL", "5")  # below floor
        assert auto_check._mandatory_interval() == 60


class TestMandatorySignature:

    def test_signature_covers_mandatory_field(self):
        from src.modules.updates.checker import _verify_manifest_signature
        from cryptography.hazmat.primitives import serialization

        _, pub_pem, priv_key = _make_key_pair()
        m = _make_manifest(private_key=None)
        del m["signature"]
        m["mandatory"] = True
        m["signature"] = _sign(m, priv_key)   # sign WITH mandatory=true

        pub = serialization.load_pem_public_key(pub_pem)
        with patch("src.modules.updates.checker._load_pub_keys", return_value=[pub]):
            assert _verify_manifest_signature(m) is True
            # flip the flag after signing → signature must no longer verify
            m["mandatory"] = False
            assert _verify_manifest_signature(m) is False
