"""Stripe Checkout payment-method and webhook safety contracts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugins.payments import stripe_provider as stripe_module


def _provider(monkeypatch, *, mode: str | None = None, methods: str | None = None):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_contract")
    monkeypatch.delenv("STRIPE_PAYMENT_METHOD_MODE", raising=False)
    monkeypatch.delenv("STRIPE_PAYMENT_METHODS", raising=False)
    if mode is not None:
        monkeypatch.setenv("STRIPE_PAYMENT_METHOD_MODE", mode)
    if methods is not None:
        monkeypatch.setenv("STRIPE_PAYMENT_METHODS", methods)
    return stripe_module.StripeProvider()


async def _create(provider, monkeypatch) -> dict:
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="cs_test_dynamic", url="https://checkout.stripe.test/session")

    monkeypatch.setattr(stripe_module.stripe.checkout.Session, "create", create)
    invoice = await provider.create_invoice(
        amount=199,
        currency="USD",
        description="VPN subscription",
        metadata={
            "return_url": "https://portal.example/success",
            "cancel_url": "https://portal.example/cancel",
        },
    )
    assert invoice.metadata["stripe_session_id"] == "cs_test_dynamic"
    assert invoice.metadata["payment_url"] == "https://checkout.stripe.test/session"
    return captured


@pytest.mark.asyncio
async def test_automatic_mode_omits_payment_method_types_and_ignores_legacy_list(
    monkeypatch,
):
    provider = _provider(monkeypatch, methods="card,alipay,wechat_pay")

    kwargs = await _create(provider, monkeypatch)

    assert provider.payment_method_mode == "automatic"
    assert provider.payment_methods is None
    assert "payment_method_types" not in kwargs
    assert "payment_method_options" not in kwargs


@pytest.mark.asyncio
async def test_card_mode_keeps_an_explicit_card_only_override(monkeypatch):
    provider = _provider(monkeypatch, mode="card", methods="card,alipay")

    kwargs = await _create(provider, monkeypatch)

    assert kwargs["payment_method_types"] == ["card"]
    assert "payment_method_options" not in kwargs


@pytest.mark.asyncio
async def test_manual_mode_deduplicates_methods_and_keeps_wechat_web_option(
    monkeypatch,
):
    provider = _provider(
        monkeypatch,
        mode="manual",
        methods=" card, wechat_pay,card, alipay ",
    )

    kwargs = await _create(provider, monkeypatch)

    assert kwargs["payment_method_types"] == ["card", "wechat_pay", "alipay"]
    assert kwargs["payment_method_options"] == {"wechat_pay": {"client": "web"}}


@pytest.mark.parametrize(
    ("mode", "methods", "message"),
    [
        ("unsupported", None, "STRIPE_PAYMENT_METHOD_MODE"),
        ("manual", "", "cannot be empty"),
        ("manual", "card,not-valid!", "comma-separated list"),
    ],
)
def test_invalid_manual_configuration_fails_before_checkout(
    monkeypatch, mode, methods, message,
):
    with pytest.raises(ValueError, match=message):
        _provider(monkeypatch, mode=mode, methods=methods)


@pytest.mark.asyncio
async def test_delayed_checkout_success_extracts_the_original_invoice(monkeypatch):
    provider = _provider(monkeypatch)
    event = {
        "type": "checkout.session.async_payment_succeeded",
        "data": {
            "object": {
                "id": "cs_delayed",
                "payment_status": "paid",
                "metadata": {"invoice_id": "STRIPE-ORIGINAL"},
            }
        },
    }
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    provider.webhook_secret = "whsec_test"
    monkeypatch.setattr(
        stripe_module.stripe.Webhook,
        "construct_event",
        lambda body, signature, secret: event,
    )

    result = await provider.process_webhook(
        b"{}", {"stripe-signature": "t=1,v1=contract"}
    )

    assert result["verified"] is True
    assert result["order_id"] == "STRIPE-ORIGINAL"
