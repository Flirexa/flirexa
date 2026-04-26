"""
Payment Plugin Template
=======================

Copy this file, rename it (e.g. stripe_provider.py), and implement the methods below.
The plugin will be auto-loaded when you restart services.

Requirements:
  - File must be in plugins/payments/ directory
  - File must define PROVIDER_CLASS pointing to your class
  - Class must extend PaymentProvider from src.modules.payment.base
  - Install any required pip packages: pip install <package>

Example:
  plugins/payments/stripe_provider.py   → Stripe
  plugins/payments/yookassa_provider.py → YooKassa
  plugins/payments/liqpay_provider.py   → LiqPay
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from src.modules.payment.base import PaymentProvider, Invoice, PaymentStatus

logger = logging.getLogger(__name__)


class TemplateProvider(PaymentProvider):
    """
    Template payment provider.
    Replace 'Template' with your provider name (e.g. StripeProvider).
    """

    def __init__(self):
        # Read credentials from environment variables
        # Your customers configure these in .env
        self.api_key = os.getenv("TEMPLATE_API_KEY", "")
        self.secret_key = os.getenv("TEMPLATE_SECRET_KEY", "")

        if not self.api_key:
            raise ValueError("TEMPLATE_API_KEY not configured in .env")

    @property
    def name(self) -> str:
        """Unique provider ID (lowercase, no spaces)"""
        return "template"

    @property
    def display_name(self) -> str:
        """Human-readable name shown to users"""
        return "Template Pay"

    @property
    def currencies(self) -> list:
        """List of supported currency codes"""
        return ["USD", "EUR"]

    async def create_invoice(
        self,
        amount: int,
        currency: str = "USD",
        description: Optional[str] = None,
        expires_in_minutes: int = 60,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Invoice:
        """
        Create a payment invoice/order.

        Args:
            amount: Amount in cents (1000 = $10.00)
            currency: Currency code
            description: What the user is paying for
            metadata: May contain return_url, cancel_url, order_id

        Returns:
            Invoice object with payment URL in metadata["payment_url"]
        """
        invoice_id = self.generate_invoice_id()

        # TODO: Call your payment provider's API here
        # Example:
        #   import stripe
        #   stripe.api_key = self.api_key
        #   session = stripe.checkout.Session.create(
        #       payment_method_types=['card'],
        #       line_items=[{'price_data': {...}, 'quantity': 1}],
        #       mode='payment',
        #       success_url=metadata.get('return_url', ''),
        #       cancel_url=metadata.get('cancel_url', ''),
        #   )
        #   payment_url = session.url

        payment_url = ""  # Replace with actual URL from provider

        return Invoice(
            id=invoice_id,
            amount=amount,
            currency=currency.upper(),
            status=PaymentStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
            metadata={
                "provider": self.name,
                "payment_url": payment_url,
                "approval_url": payment_url,
                **(metadata or {}),
            },
        )

    async def check_payment(self, invoice_id: str) -> PaymentStatus:
        """
        Check if payment has been completed.

        Args:
            invoice_id: Your internal or provider's invoice/order ID

        Returns:
            PaymentStatus.COMPLETED, PENDING, FAILED, or EXPIRED
        """
        # TODO: Call your provider's API to check status
        return PaymentStatus.PENDING

    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """Get invoice details from provider."""
        # TODO: Implement if needed
        return None

    async def process_webhook(self, data: Dict[str, Any]) -> bool:
        """
        Process incoming webhook from payment provider.

        Args:
            data: Parsed webhook JSON payload

        Returns:
            True if payment is confirmed
        """
        # TODO: Verify signature, check payment status
        # Return True when payment is confirmed
        return False

    async def test_connection(self) -> Dict[str, Any]:
        """Test API connection (called from admin Settings)."""
        try:
            # TODO: Make a test API call
            return {"connected": True, "message": f"{self.display_name} connected"}
        except Exception as e:
            return {"connected": False, "message": str(e)}


# ── Required: point to your provider class ──
# The plugin loader looks for this variable
PROVIDER_CLASS = TemplateProvider
