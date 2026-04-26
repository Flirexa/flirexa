"""
Mollie Payment Plugin — Europe & worldwide
Supports: Visa, Mastercard, iDEAL, Bancontact, SEPA, Apple Pay, Klarna

Setup:
  1. Register at https://www.mollie.com/
  2. Get API Key from Dashboard → Developers → API keys
  3. Add to .env:
     MOLLIE_API_KEY=live_...
  4. Set webhook URL in your Mollie dashboard or it's auto-configured per payment
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from src.modules.payment.base import PaymentProvider, Invoice, PaymentStatus

logger = logging.getLogger(__name__)

try:
    from mollie.api.client import Client as MollieClient
except ImportError:
    MollieClient = None
    logger.warning("Mollie plugin: 'mollie-api-python' not installed. Run: pip install mollie-api-python")


class MollieProvider(PaymentProvider):

    def __init__(self):
        if not MollieClient:
            raise ImportError("mollie-api-python not installed. Run: pip install mollie-api-python")
        self.api_key = os.getenv("MOLLIE_API_KEY", "")
        if not self.api_key:
            raise ValueError("MOLLIE_API_KEY required")
        self.client = MollieClient()
        self.client.set_api_key(self.api_key)

    @property
    def name(self) -> str:
        return "mollie"

    @property
    def display_name(self) -> str:
        return "Mollie (EU)"

    @property
    def currencies(self) -> list:
        return ["EUR", "USD", "GBP"]

    async def create_invoice(self, amount: int, currency: str = "EUR",
                             description: Optional[str] = None, expires_in_minutes: int = 60,
                             metadata: Optional[Dict[str, Any]] = None) -> Invoice:
        invoice_id = self.generate_invoice_id()
        meta = metadata or {}
        amount_str = f"{amount / 100:.2f}"

        payment = self.client.payments.create({
            "amount": {"currency": currency.upper(), "value": amount_str},
            "description": description or "VPN Subscription",
            "redirectUrl": meta.get("return_url", "https://example.com/success"),
            "webhookUrl": meta.get("ipn_callback_url", ""),
            "metadata": {"invoice_id": invoice_id},
        })

        payment_url = payment["_links"]["checkout"]["href"]
        mollie_id = payment["id"]

        logger.info(f"Mollie payment created: {mollie_id} (invoice {invoice_id})")

        return Invoice(
            id=invoice_id, amount=amount, currency=currency.upper(),
            status=PaymentStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
            metadata={"provider": "mollie", "mollie_id": mollie_id,
                       "payment_url": payment_url, "approval_url": payment_url, **(metadata or {})},
        )

    async def check_payment(self, invoice_id: str) -> PaymentStatus:
        try:
            payment = self.client.payments.get(invoice_id)
            if payment.is_paid():
                return PaymentStatus.COMPLETED
            elif payment.is_expired():
                return PaymentStatus.EXPIRED
            elif payment.is_failed():
                return PaymentStatus.FAILED
            return PaymentStatus.PENDING
        except Exception as e:
            logger.error(f"Mollie check error: {e}")
            return PaymentStatus.PENDING

    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        try:
            payment = self.client.payments.get(invoice_id)
            status = PaymentStatus.COMPLETED if payment.is_paid() else PaymentStatus.PENDING
            return Invoice(
                id=invoice_id,
                amount=int(float(payment["amount"]["value"]) * 100),
                currency=payment["amount"]["currency"],
                status=status,
                created_at=datetime.now(timezone.utc),
                metadata={"provider": "mollie", "mollie_id": invoice_id},
            )
        except Exception as e:
            logger.error(f"Mollie get_invoice error: {e}")
            return None

    async def process_webhook(self, data: Dict[str, Any]) -> bool:
        payment_id = data.get("id")
        if not payment_id:
            return False
        try:
            payment = self.client.payments.get(payment_id)
            if payment.is_paid():
                logger.info(f"Mollie payment confirmed: {payment_id}")
                return True
        except Exception as e:
            logger.error(f"Mollie webhook error: {e}")
        return False

    async def test_connection(self) -> Dict[str, Any]:
        try:
            self.client.methods.list()
            return {"connected": True, "message": "Mollie connected"}
        except Exception as e:
            return {"connected": False, "message": str(e)}


PROVIDER_CLASS = MollieProvider
