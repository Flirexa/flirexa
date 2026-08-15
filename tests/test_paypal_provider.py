"""PayPal Orders v2 safety and return-flow contracts."""

from unittest.mock import AsyncMock

import pytest

from src.modules.payment.providers import paypal as paypal_module


if getattr(paypal_module, "FLIREXA_COMMERCIAL_STUB", False):
    pytest.skip("PayPal implementation is exercised by the private overlay", allow_module_level=True)


PayPalAPIError = paypal_module.PayPalAPIError
PayPalProvider = paypal_module.PayPalProvider


def _provider() -> PayPalProvider:
    return PayPalProvider("client", "secret", sandbox=True, webhook_id="WH-1")


@pytest.mark.asyncio
async def test_create_order_requires_real_https_return_urls():
    provider = _provider()
    provider._request = AsyncMock()

    with pytest.raises(ValueError, match="return_url"):
        await provider.create_invoice(500)
    with pytest.raises(ValueError, match="return_url"):
        await provider.create_invoice(
            500,
            metadata={"return_url": "http://portal.example/ok", "cancel_url": "https://portal.example/cancel"},
        )
    provider._request.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_order_forwards_configured_return_urls():
    provider = _provider()
    provider._request = AsyncMock(return_value={
        "id": "ORDER-1",
        "links": [{"rel": "payer-action", "href": "https://www.paypal.com/approve"}],
    })

    invoice = await provider.create_invoice(
        500,
        metadata={
            "return_url": "https://portal.example/payments?paypal_return=1",
            "cancel_url": "https://portal.example/payments?paypal_cancel=1",
        },
    )

    payload = provider._request.await_args.args[2]
    experience = payload["payment_source"]["paypal"]["experience_context"]
    assert experience["return_url"].endswith("paypal_return=1")
    assert experience["cancel_url"].endswith("paypal_cancel=1")
    assert invoice.metadata["paypal_order_id"] == "ORDER-1"


@pytest.mark.asyncio
async def test_capture_uses_deterministic_idempotency_key():
    provider = _provider()
    provider._request = AsyncMock(return_value={
        "status": "COMPLETED",
        "purchase_units": [{"payments": {"captures": [{"id": "CAP-1"}]}}],
    })

    result = await provider.capture_order("ORDER-1")

    headers = provider._request.await_args.kwargs["extra_headers"]
    assert headers["PayPal-Request-Id"] == "flirexa-capture-ORDER-1"
    assert result["capture_id"] == "CAP-1"


@pytest.mark.asyncio
async def test_capture_race_accepts_only_authoritative_completed_order():
    provider = _provider()
    provider._request = AsyncMock(side_effect=PayPalAPIError(422, {"name": "ORDER_ALREADY_CAPTURED"}))
    provider.get_order = AsyncMock(return_value={
        "status": "COMPLETED",
        "purchase_units": [{"payments": {"captures": [{"id": "CAP-1"}]}}],
    })

    result = await provider.capture_order("ORDER-1")

    assert result["status"] == "COMPLETED"
    assert result["capture_id"] == "CAP-1"
