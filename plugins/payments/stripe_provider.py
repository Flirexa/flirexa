"""
Stripe Payment Plugin for VPN Management Studio

Setup:
  1. pip install stripe
  2. Add to .env:
     STRIPE_SECRET_KEY=sk_live_...
     STRIPE_WEBHOOK_SECRET=whsec_...   (optional, for webhook verification)
  3. Restart services
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from src.modules.payment.base import PaymentProvider, Invoice, PaymentStatus

logger = logging.getLogger(__name__)

try:
    import stripe
except ImportError:
    stripe = None
    logger.warning("Stripe plugin: 'stripe' package not installed. Run: pip install stripe")


class StripeProvider(PaymentProvider):

    def __init__(self):
        if not stripe:
            raise ImportError("stripe package not installed. Run: pip install stripe")

        self.secret_key = os.getenv("STRIPE_SECRET_KEY", "")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

        if not self.secret_key:
            raise ValueError("STRIPE_SECRET_KEY not configured")

        stripe.api_key = self.secret_key

    @property
    def name(self) -> str:
        return "stripe"

    @property
    def display_name(self) -> str:
        return "Stripe (Card)"

    @property
    def currencies(self) -> list:
        return ["USD", "EUR", "GBP", "CAD", "AUD", "JPY"]

    async def create_invoice(
        self,
        amount: int,
        currency: str = "USD",
        description: Optional[str] = None,
        expires_in_minutes: int = 60,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Invoice:
        invoice_id = self.generate_invoice_id()
        meta = metadata or {}

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": currency.lower(),
                    "unit_amount": amount,
                    "product_data": {"name": description or "VPN Subscription"},
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=meta.get("return_url", "https://example.com/success"),
            cancel_url=meta.get("cancel_url", "https://example.com/cancel"),
            metadata={"invoice_id": invoice_id},
            expires_at=int((datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)).timestamp()),
        )

        logger.info(f"Stripe session created: {session.id} (invoice {invoice_id})")

        return Invoice(
            id=invoice_id,
            amount=amount,
            currency=currency.upper(),
            status=PaymentStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
            metadata={
                "provider": "stripe",
                "stripe_session_id": session.id,
                "payment_url": session.url,
                "approval_url": session.url,
                **(metadata or {}),
            },
        )

    async def check_payment(self, invoice_id: str) -> PaymentStatus:
        try:
            session = stripe.checkout.Session.retrieve(invoice_id)
            if session.payment_status == "paid":
                return PaymentStatus.COMPLETED
            elif session.status == "expired":
                return PaymentStatus.EXPIRED
            return PaymentStatus.PENDING
        except Exception as e:
            logger.error(f"Stripe check_payment error: {e}")
            return PaymentStatus.PENDING

    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        try:
            session = stripe.checkout.Session.retrieve(invoice_id)
            status = PaymentStatus.COMPLETED if session.payment_status == "paid" else PaymentStatus.PENDING
            return Invoice(
                id=invoice_id,
                amount=session.amount_total or 0,
                currency=(session.currency or "usd").upper(),
                status=status,
                created_at=datetime.now(timezone.utc),
                metadata={"provider": "stripe", "stripe_session_id": session.id},
            )
        except Exception as e:
            logger.error(f"Stripe get_invoice error: {e}")
            return None

    async def process_webhook(self, data: Dict[str, Any]) -> bool:
        event_type = data.get("type", "")
        if event_type == "checkout.session.completed":
            session = data.get("data", {}).get("object", {})
            if session.get("payment_status") == "paid":
                logger.info(f"Stripe payment completed: {session.get('id')}")
                return True
        return False

    async def test_connection(self) -> Dict[str, Any]:
        try:
            stripe.Account.retrieve()
            return {"connected": True, "message": "Stripe connected"}
        except Exception as e:
            return {"connected": False, "message": str(e)}


PROVIDER_CLASS = StripeProvider
