"""
VPN Management Studio Payment Module - Base Classes
Abstract interfaces for payment providers
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
import uuid


class PaymentStatus(str, Enum):
    """Payment status"""
    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"
    FAILED = "failed"
    REFUNDED = "refunded"


@dataclass
class Invoice:
    """Payment invoice"""
    id: str
    amount: int  # Amount in smallest units (cents, satoshi, etc.)
    currency: str  # Currency code (USD, BTC, USDT, TON)
    status: PaymentStatus = PaymentStatus.PENDING

    # Payment details
    wallet_address: Optional[str] = None
    qr_code: Optional[str] = None  # QR code data URL or path
    qr_code_url: Optional[str] = None  # URL to QR image

    # Crypto specific
    crypto_amount: Optional[str] = None  # Amount in crypto (e.g., "0.00123456")
    exchange_rate: Optional[float] = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Transaction info
    tx_hash: Optional[str] = None
    confirmations: int = 0

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if invoice has expired"""
        if self.expires_at is None:
            return False
        return datetime.now() >= self.expires_at

    def is_completed(self) -> bool:
        """Check if payment is completed"""
        return self.status == PaymentStatus.COMPLETED

    def is_pending(self) -> bool:
        """Check if payment is still pending"""
        return self.status == PaymentStatus.PENDING


class PaymentProvider(ABC):
    """
    Abstract base class for payment providers

    Implement this class to add new payment methods.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'btc', 'usdt', 'ton')"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name"""
        pass

    @property
    @abstractmethod
    def currencies(self) -> list:
        """List of supported currencies"""
        pass

    @abstractmethod
    async def create_invoice(
        self,
        amount: int,
        currency: str,
        description: Optional[str] = None,
        expires_in_minutes: int = 60,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Invoice:
        """
        Create a payment invoice

        Args:
            amount: Amount in smallest units (cents for fiat, satoshi for BTC)
            currency: Currency code
            description: Payment description
            expires_in_minutes: Invoice expiry time
            metadata: Additional metadata to store

        Returns:
            Created Invoice object
        """
        pass

    @abstractmethod
    async def check_payment(self, invoice_id: str) -> PaymentStatus:
        """
        Check payment status

        Args:
            invoice_id: Invoice ID to check

        Returns:
            Current payment status
        """
        pass

    @abstractmethod
    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """
        Get invoice details

        Args:
            invoice_id: Invoice ID

        Returns:
            Invoice object or None if not found
        """
        pass

    @abstractmethod
    async def process_webhook(self, data: Dict[str, Any]) -> bool:
        """
        Process webhook callback from payment provider

        Args:
            data: Webhook payload data

        Returns:
            True if processed successfully
        """
        pass

    async def cancel_invoice(self, invoice_id: str) -> bool:
        """
        Cancel a pending invoice

        Args:
            invoice_id: Invoice ID to cancel

        Returns:
            True if cancelled successfully
        """
        # Default implementation - override if provider supports cancellation
        return False

    def validate_address(self, address: str) -> bool:
        """
        Validate a wallet address

        Args:
            address: Wallet address to validate

        Returns:
            True if valid
        """
        # Default implementation - override for specific validation
        return len(address) > 0

    @staticmethod
    def generate_invoice_id() -> str:
        """Generate a unique invoice ID"""
        return str(uuid.uuid4())


class PaymentManager:
    """
    Manager for handling multiple payment providers

    Usage:
        manager = PaymentManager()
        manager.register_provider(NOWPaymentsProvider(api_key=...))

        invoice = await manager.create_invoice('nowpayments', 1000, 'USD')
    """

    def __init__(self):
        self.providers: Dict[str, PaymentProvider] = {}

    def register_provider(self, provider: PaymentProvider) -> None:
        """Register a payment provider"""
        self.providers[provider.name] = provider

    def get_provider(self, name: str) -> Optional[PaymentProvider]:
        """Get a payment provider by name"""
        return self.providers.get(name)

    def get_available_providers(self) -> list:
        """Get list of available provider names"""
        return list(self.providers.keys())

    async def create_invoice(
        self,
        provider_name: str,
        amount: int,
        currency: str,
        **kwargs
    ) -> Optional[Invoice]:
        """Create an invoice using the specified provider"""
        provider = self.get_provider(provider_name)
        if not provider:
            return None
        return await provider.create_invoice(amount, currency, **kwargs)

    async def check_payment(
        self,
        provider_name: str,
        invoice_id: str
    ) -> Optional[PaymentStatus]:
        """Check payment status"""
        provider = self.get_provider(provider_name)
        if not provider:
            return None
        return await provider.check_payment(invoice_id)
