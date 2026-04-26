"""
Payme Payment Plugin — Uzbekistan
Supports: UzCard, Humo, Visa, Mastercard

Setup:
  1. Register at https://payme.uz (merchant account)
  2. Get Merchant ID and Secret Key
  3. Add to .env:
     PAYME_MERCHANT_ID=...
     PAYME_SECRET_KEY=...
  4. Set webhook URL in Payme dashboard:
     https://YOUR_DOMAIN:10443/client-portal/webhooks/payme
"""

import os
import json
import base64
import logging
import httpx
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from src.modules.payment.base import PaymentProvider, Invoice, PaymentStatus

logger = logging.getLogger(__name__)


class PaymeProvider(PaymentProvider):

    CHECKOUT_URL = "https://checkout.paycom.uz"

    def __init__(self):
        self.merchant_id = os.getenv("PAYME_MERCHANT_ID", "")
        self.secret_key = os.getenv("PAYME_SECRET_KEY", "")
        if not self.merchant_id:
            raise ValueError("PAYME_MERCHANT_ID required")

    @property
    def name(self) -> str:
        return "payme"

    @property
    def display_name(self) -> str:
        return "Payme (UZ)"

    @property
    def currencies(self) -> list:
        return ["UZS", "USD"]

    async def create_invoice(self, amount: int, currency: str = "USD",
                             description: Optional[str] = None, expires_in_minutes: int = 60,
                             metadata: Optional[Dict[str, Any]] = None) -> Invoice:
        invoice_id = self.generate_invoice_id()
        # Payme expects amount in tiyin (1 USD = 100 cents, but Payme uses tiyin for UZS)
        # For USD payments, amount is in cents already
        payme_amount = amount  # cents

        # Build checkout URL with base64 encoded params
        params = f"m={self.merchant_id};ac.order_id={invoice_id};a={payme_amount}"
        encoded = base64.b64encode(params.encode()).decode()
        payment_url = f"{self.CHECKOUT_URL}/{encoded}"

        return Invoice(
            id=invoice_id, amount=amount, currency=currency.upper(),
            status=PaymentStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
            metadata={"provider": "payme", "payment_url": payment_url, "approval_url": payment_url, **(metadata or {})},
        )

    async def check_payment(self, invoice_id: str) -> PaymentStatus:
        # Payme uses webhook-based confirmation, manual check requires merchant API
        return PaymentStatus.PENDING

    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        return None

    async def process_webhook(self, data: Dict[str, Any]) -> bool:
        method = data.get("method", "")
        if method == "receipts.pay":
            logger.info(f"Payme payment confirmed: {data.get('params', {}).get('id')}")
            return True
        elif method == "receipts.create":
            logger.info(f"Payme receipt created")
            return False  # Not yet paid
        return False

    async def test_connection(self) -> Dict[str, Any]:
        return {"connected": bool(self.merchant_id), "message": "Payme configured" if self.merchant_id else "No merchant ID"}


PROVIDER_CLASS = PaymeProvider
