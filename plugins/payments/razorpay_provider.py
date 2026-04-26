"""
Razorpay Payment Plugin — India & worldwide
Supports: Visa, Mastercard, UPI, NetBanking, Wallets

Setup:
  1. Register at https://razorpay.com/
  2. Get Key ID and Key Secret from Dashboard → Settings → API Keys
  3. Add to .env:
     RAZORPAY_KEY_ID=rzp_live_...
     RAZORPAY_KEY_SECRET=...
  4. Set webhook URL in Razorpay dashboard:
     https://YOUR_DOMAIN:10443/client-portal/webhooks/razorpay
  5. Enable "payment.captured" event in webhook settings
"""

import os
import hmac
import hashlib
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from src.modules.payment.base import PaymentProvider, Invoice, PaymentStatus

logger = logging.getLogger(__name__)

try:
    import razorpay
except ImportError:
    razorpay = None
    logger.warning("Razorpay plugin: 'razorpay' not installed. Run: pip install razorpay")


class RazorpayProvider(PaymentProvider):

    def __init__(self):
        if not razorpay:
            raise ImportError("razorpay not installed. Run: pip install razorpay")
        self.key_id = os.getenv("RAZORPAY_KEY_ID", "")
        self.key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
        self.webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
        if not self.key_id or not self.key_secret:
            raise ValueError("RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET required")
        self.client = razorpay.Client(auth=(self.key_id, self.key_secret))

    @property
    def name(self) -> str:
        return "razorpay"

    @property
    def display_name(self) -> str:
        return "Razorpay (IN)"

    @property
    def currencies(self) -> list:
        return ["INR", "USD", "EUR"]

    async def create_invoice(self, amount: int, currency: str = "INR",
                             description: Optional[str] = None, expires_in_minutes: int = 60,
                             metadata: Optional[Dict[str, Any]] = None) -> Invoice:
        invoice_id = self.generate_invoice_id()
        meta = metadata or {}

        # Razorpay payment link
        link = self.client.payment_link.create({
            "amount": amount,  # in paise for INR, cents for USD
            "currency": currency.upper(),
            "description": description or "VPN Subscription",
            "reference_id": invoice_id,
            "expire_by": int((datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)).timestamp()),
            "callback_url": meta.get("return_url", ""),
            "callback_method": "get",
            "notes": {"invoice_id": invoice_id},
        })

        payment_url = link.get("short_url", "")
        razorpay_id = link.get("id", "")

        logger.info(f"Razorpay link created: {razorpay_id} (invoice {invoice_id})")

        return Invoice(
            id=invoice_id, amount=amount, currency=currency.upper(),
            status=PaymentStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
            metadata={"provider": "razorpay", "razorpay_id": razorpay_id,
                       "payment_url": payment_url, "approval_url": payment_url, **(metadata or {})},
        )

    async def check_payment(self, invoice_id: str) -> PaymentStatus:
        try:
            link = self.client.payment_link.fetch(invoice_id)
            status = link.get("status", "")
            if status == "paid":
                return PaymentStatus.COMPLETED
            elif status == "expired":
                return PaymentStatus.EXPIRED
            elif status == "cancelled":
                return PaymentStatus.FAILED
            return PaymentStatus.PENDING
        except Exception as e:
            logger.error(f"Razorpay check error: {e}")
            return PaymentStatus.PENDING

    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        return None

    async def process_webhook(self, data: Dict[str, Any]) -> bool:
        event = data.get("event", "")
        if event == "payment_link.paid":
            payload = data.get("payload", {}).get("payment_link", {}).get("entity", {})
            logger.info(f"Razorpay payment confirmed: {payload.get('id')}")
            return True
        elif event == "payment.captured":
            logger.info(f"Razorpay payment captured")
            return True
        return False

    async def test_connection(self) -> Dict[str, Any]:
        try:
            self.client.payment.all({"count": 1})
            return {"connected": True, "message": "Razorpay connected"}
        except Exception as e:
            return {"connected": False, "message": str(e)}


PROVIDER_CLASS = RazorpayProvider
