"""
VPN Management Studio Payment Module - NOWPayments Provider
Integration with NOWPayments API (cryptocurrency payments)

Docs: https://documenter.getpostman.com/view/7907941/S1a32n38
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

import httpx

from src.modules.payment.base import PaymentProvider, Invoice, PaymentStatus

logger = logging.getLogger(__name__)


class NOWPaymentsProvider(PaymentProvider):
    """
    NOWPayments payment provider for cryptocurrency payments.

    Setup:
        1. Register at https://nowpayments.io
        2. Get API Key from Settings → API Keys
        3. Get IPN Secret from Settings → IPN
        4. Set IPN Callback URL in NOWPayments dashboard

    Usage:
        provider = NOWPaymentsProvider(api_key="...", ipn_secret="...", sandbox=False)
        invoice = await provider.create_invoice(1000, "USD", description="VPN Plan")
    """

    LIVE_URL = "https://api.nowpayments.io/v1"
    SANDBOX_URL = "https://api-sandbox.nowpayments.io/v1"

    CONFIRMED_STATUSES = {"finished", "confirmed", "complete"}

    def __init__(self, api_key: str, ipn_secret: str = "", sandbox: bool = False):
        self.api_key = api_key
        self.ipn_secret = ipn_secret
        self.sandbox = sandbox
        self.api_url = self.SANDBOX_URL if sandbox else self.LIVE_URL

    @property
    def name(self) -> str:
        return "nowpayments"

    @property
    def display_name(self) -> str:
        return "NOWPayments (Crypto)"

    @property
    def currencies(self) -> list:
        return ["BTC", "ETH", "USDT", "USDC", "LTC", "XMR", "TON", "SOL", "TRX"]

    async def _request(
        self, method: str, endpoint: str, json_data: Optional[dict] = None
    ) -> dict:
        """Make authenticated API request."""
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            url = f"{self.api_url}{endpoint}"
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "POST":
                resp = await client.post(url, headers=headers, json=json_data)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if resp.status_code not in (200, 201):
                logger.error(f"NOWPayments API error {resp.status_code}: {resp.text}")
                raise Exception(f"NOWPayments API error: {resp.status_code}")

            return resp.json()

    async def create_invoice(
        self,
        amount: int,
        currency: str = "USD",
        description: Optional[str] = None,
        expires_in_minutes: int = 60,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Invoice:
        """
        Create NOWPayments invoice.

        Args:
            amount: Amount in cents (e.g., 1000 = $10.00)
            currency: Price currency (USD, EUR)
            description: Payment description
            expires_in_minutes: Not directly used by NOWPayments
            metadata: Should include ipn_callback_url, order_id, success_url, cancel_url
        """
        amount_float = amount / 100
        invoice_id = self.generate_invoice_id()
        meta = metadata or {}

        payload = {
            "price_amount": amount_float,
            "price_currency": currency.lower(),
            "order_id": meta.get("order_id", invoice_id),
            "order_description": description or "VPN Subscription",
            "ipn_callback_url": meta.get("ipn_callback_url", ""),
            "success_url": meta.get("success_url", ""),
            "cancel_url": meta.get("cancel_url", ""),
            "is_fee_paid_by_user": False,
        }

        # Optional: pre-select pay currency
        if meta.get("pay_currency"):
            payload["pay_currency"] = meta["pay_currency"]

        result = await self._request("POST", "/invoice", payload)

        nowpayments_id = str(result.get("id", ""))
        invoice_url = result.get("invoice_url", "")

        invoice = Invoice(
            id=invoice_id,
            amount=amount,
            currency=currency.upper(),
            status=PaymentStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
            metadata={
                "provider": "nowpayments",
                "nowpayments_id": nowpayments_id,
                "payment_url": invoice_url,
                "approval_url": invoice_url,
                **(metadata or {}),
            },
        )

        logger.info(
            f"Created NOWPayments invoice {nowpayments_id} (internal {invoice_id}): "
            f"{amount_float} {currency}"
        )
        return invoice

    async def check_payment(self, invoice_id: str) -> PaymentStatus:
        """Check payment status by NOWPayments payment ID."""
        try:
            result = await self._request("GET", f"/payment/{invoice_id}")
            status = result.get("payment_status", "").lower()

            if status in self.CONFIRMED_STATUSES:
                return PaymentStatus.COMPLETED
            elif status in ("expired", "refunded"):
                return PaymentStatus.EXPIRED if status == "expired" else PaymentStatus.REFUNDED
            elif status in ("failed",):
                return PaymentStatus.FAILED
            else:
                return PaymentStatus.PENDING

        except Exception as e:
            logger.error(f"Failed to check NOWPayments status for {invoice_id}: {e}")
            return PaymentStatus.PENDING

    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """Get payment details."""
        try:
            result = await self._request("GET", f"/payment/{invoice_id}")

            status_str = result.get("payment_status", "").lower()
            if status_str in self.CONFIRMED_STATUSES:
                status = PaymentStatus.COMPLETED
            elif status_str == "expired":
                status = PaymentStatus.EXPIRED
            elif status_str == "failed":
                status = PaymentStatus.FAILED
            else:
                status = PaymentStatus.PENDING

            amount_usd = float(result.get("price_amount", 0))

            return Invoice(
                id=invoice_id,
                amount=int(amount_usd * 100),
                currency=result.get("price_currency", "USD").upper(),
                status=status,
                created_at=datetime.now(timezone.utc),
                crypto_amount=str(result.get("pay_amount", "")),
                metadata={
                    "provider": "nowpayments",
                    "nowpayments_id": invoice_id,
                    "pay_currency": result.get("pay_currency", ""),
                    "payment_status": status_str,
                },
            )
        except Exception as e:
            logger.error(f"Failed to get NOWPayments invoice {invoice_id}: {e}")
            return None

    def verify_signature(self, body_bytes: bytes, sig_header: str) -> bool:
        """Verify NOWPayments HMAC-SHA512 IPN signature."""
        if not self.ipn_secret:
            logger.error("IPN secret not configured — rejecting webhook")
            return False
        if not sig_header:
            return False

        # NOWPayments signs sorted JSON
        try:
            payload = json.loads(body_bytes)
            sorted_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        except Exception:
            sorted_payload = body_bytes.decode("utf-8", errors="replace")

        expected = hmac.new(
            self.ipn_secret.encode("utf-8"),
            sorted_payload.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()

        return hmac.compare_digest(expected, sig_header.lower())

    async def process_webhook(self, data: Dict[str, Any], signature: str = "") -> bool:
        """
        Process NOWPayments IPN webhook.

        Args:
            data: Parsed webhook payload
            signature: x-nowpayments-sig header value

        Returns:
            True if payment is confirmed
        """
        payment_status = data.get("payment_status", "").lower()
        payment_id = str(data.get("payment_id", ""))
        order_id = str(data.get("order_id", ""))

        logger.info(
            f"NOWPayments IPN: payment_id={payment_id} status={payment_status} order_id={order_id}"
        )

        if payment_status in self.CONFIRMED_STATUSES:
            logger.info(f"NOWPayments payment confirmed: {payment_id}")
            return True

        return False

    async def test_connection(self) -> Dict[str, Any]:
        """Test NOWPayments API connection."""
        try:
            result = await self._request("GET", "/status")
            return {
                "connected": result.get("message") == "OK",
                "sandbox": self.sandbox,
                "message": "NOWPayments connected" if result.get("message") == "OK" else result.get("message", "Unknown"),
            }
        except Exception as e:
            return {
                "connected": False,
                "sandbox": self.sandbox,
                "message": str(e),
            }
