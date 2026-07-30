"""Contracts for free/paid payment-settings separation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import system
from src.modules import payment_settings_commercial


def test_shared_system_route_has_no_paid_provider_implementations():
    source = Path("src/api/routes/system.py").read_text(encoding="utf-8")

    protected_symbols = (
        "CryptoPayAdapter",
        "PayPalProvider",
        "StripeProvider",
        "PaymeProvider",
        "MollieProvider",
        "RazorpayProvider",
        "plugins.payments",
        "subscription.cryptopay_adapter",
    )
    assert all(symbol not in source for symbol in protected_symbols)


def test_nowpayments_only_payload_does_not_reset_paid_defaults():
    request = system.PaymentSettingsUpdate(
        nowpayments_api_key="free-key",
        nowpayments_sandbox=True,
    )

    assert request.cryptopay_testnet is None
    assert not (request.model_fields_set & payment_settings_commercial.PAID_SETTING_FIELDS)
    assert payment_settings_commercial.collect_env_updates(request) == {}


def test_paid_env_collection_uses_only_explicit_fields():
    request = system.PaymentSettingsUpdate(
        cryptopay_api_token="token",
        cryptopay_testnet=False,
        paypal_sandbox=True,
    )

    assert payment_settings_commercial.collect_env_updates(request) == {
        "CRYPTOPAY_API_TOKEN": "token",
        "CRYPTOPAY_TESTNET": "false",
        "PAYPAL_SANDBOX": "true",
    }


@pytest.mark.asyncio
async def test_paid_self_test_is_delegated(monkeypatch):
    delegated = AsyncMock(return_value={"provider": "stripe", "configured": False})
    monkeypatch.setattr(
        system.commercial_payments,
        "test_paid_provider",
        delegated,
    )

    result = await system._payment_test_for_provider("stripe")

    assert result == {"provider": "stripe", "configured": False}
    delegated.assert_awaited_once()


@pytest.mark.asyncio
async def test_nowpayments_self_test_stays_in_open_core(monkeypatch):
    provider = SimpleNamespace(
        verify_signature=lambda body, signature: signature != "deadbeef" * 16,
    )
    from src.api.routes import client_portal

    monkeypatch.setattr(client_portal, "nowpayments_provider", provider)
    monkeypatch.setenv("NOWPAYMENTS_IPN_SECRET", "free-secret")
    result = await system._payment_test_for_provider("nowpayments")

    assert result["provider"] == "nowpayments"
    assert result["configured"] is True
    assert result["failed"] == 1  # simplistic fake rejects only the forged signature
