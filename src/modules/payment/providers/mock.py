"""
VPN Management Studio Payment Provider - Mock
For testing and development
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from loguru import logger

from ..base import PaymentProvider, Invoice, PaymentStatus


class MockPaymentProvider(PaymentProvider):
    """
    Mock payment provider for testing

    Simulates payment flow without actual transactions.
    Useful for development and testing.
    """

    def __init__(self):
        self._invoices: Dict[str, Invoice] = {}

    @property
    def name(self) -> str:
        return "mock"

    @property
    def display_name(self) -> str:
        return "Test Payment"

    @property
    def currencies(self) -> list:
        return ["USD", "RUB", "TEST"]

    async def create_invoice(
        self,
        amount: int,
        currency: str,
        description: Optional[str] = None,
        expires_in_minutes: int = 60,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Invoice:
        """Create a mock invoice"""
        invoice_id = self.generate_invoice_id()

        invoice = Invoice(
            id=invoice_id,
            amount=amount,
            currency=currency,
            status=PaymentStatus.PENDING,
            wallet_address=f"mock_wallet_{invoice_id[:8]}",
            expires_at=datetime.now() + timedelta(minutes=expires_in_minutes),
            metadata=metadata or {},
        )

        self._invoices[invoice_id] = invoice

        logger.info(f"Mock invoice created: {invoice_id}, amount: {amount} {currency}")

        return invoice

    async def check_payment(self, invoice_id: str) -> PaymentStatus:
        """Check mock payment status"""
        invoice = self._invoices.get(invoice_id)
        if not invoice:
            return PaymentStatus.FAILED

        # Check if expired
        if invoice.is_expired():
            invoice.status = PaymentStatus.EXPIRED
            return PaymentStatus.EXPIRED

        return invoice.status

    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """Get mock invoice"""
        return self._invoices.get(invoice_id)

    async def process_webhook(self, data: Dict[str, Any]) -> bool:
        """Process mock webhook"""
        invoice_id = data.get("invoice_id")
        new_status = data.get("status")

        if not invoice_id or not new_status:
            return False

        invoice = self._invoices.get(invoice_id)
        if not invoice:
            return False

        try:
            invoice.status = PaymentStatus(new_status)
            if invoice.status == PaymentStatus.COMPLETED:
                invoice.completed_at = datetime.now()
                invoice.tx_hash = f"mock_tx_{invoice_id[:8]}"
            return True
        except ValueError:
            return False

    async def simulate_payment(self, invoice_id: str) -> bool:
        """
        Simulate a successful payment (for testing)

        Args:
            invoice_id: Invoice ID to mark as paid

        Returns:
            True if successful
        """
        invoice = self._invoices.get(invoice_id)
        if not invoice:
            return False

        if invoice.status != PaymentStatus.PENDING:
            return False

        invoice.status = PaymentStatus.COMPLETED
        invoice.completed_at = datetime.now()
        invoice.tx_hash = f"mock_tx_{invoice_id[:8]}"
        invoice.confirmations = 6

        logger.info(f"Mock payment simulated: {invoice_id}")
        return True

    async def simulate_expiry(self, invoice_id: str) -> bool:
        """
        Simulate invoice expiry (for testing)
        """
        invoice = self._invoices.get(invoice_id)
        if not invoice:
            return False

        invoice.status = PaymentStatus.EXPIRED
        return True
