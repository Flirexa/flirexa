"""
VPN Management Studio Client Portal - Cryptocurrency Payment Provider
Integration with NOWPayments API for crypto payments
"""

import httpx
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import logging
import hashlib
import hmac

from src.modules.payment.base import PaymentProvider, Invoice, PaymentStatus

logger = logging.getLogger(__name__)


class CryptoPaymentProvider(PaymentProvider):
    """
    Cryptocurrency payment provider using NOWPayments API

    Supports: BTC, USDT (TRC20, ERC20), ETH, TON, and more

    Setup:
        1. Register at https://nowpayments.io/
        2. Get API key and IPN secret
        3. Configure webhook URL

    Usage:
        provider = CryptoPaymentProvider(
            api_key="your_api_key",
            ipn_secret="your_ipn_secret"
        )
        invoice = await provider.create_invoice(1000, "USDT", description="Basic Plan - 30 days")
    """

    def __init__(
        self,
        api_key: str,
        ipn_secret: str,
        api_url: str = "https://api.nowpayments.io/v1",
        sandbox: bool = False
    ):
        self.api_key = api_key
        self.ipn_secret = ipn_secret
        self.api_url = "https://api-sandbox.nowpayments.io/v1" if sandbox else api_url
        self.sandbox = sandbox

        # Supported currencies
        self._currencies = {
            "BTC": {"name": "Bitcoin", "decimals": 8},
            "USDT": {"name": "Tether (TRC20)", "decimals": 6},
            "USDTERC20": {"name": "Tether (ERC20)", "decimals": 6},
            "ETH": {"name": "Ethereum", "decimals": 18},
            "TON": {"name": "Toncoin", "decimals": 9},
            "TRX": {"name": "Tron", "decimals": 6},
            "LTC": {"name": "Litecoin", "decimals": 8},
        }

    @property
    def name(self) -> str:
        return "crypto"

    @property
    def display_name(self) -> str:
        return "Cryptocurrency"

    @property
    def currencies(self) -> list:
        return list(self._currencies.keys())

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make API request to NOWPayments"""
        url = f"{self.api_url}{endpoint}"
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                if method == "GET":
                    resp = await client.get(url, headers=headers)
                elif method == "POST":
                    resp = await client.post(url, headers=headers, json=data)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                result = resp.json()
                if resp.status_code not in (200, 201):
                    logger.error(f"NOWPayments API error: {result}")
                    raise Exception(f"API error: {result.get('message', 'Unknown error')}")
                return result
        except httpx.HTTPError as e:
            logger.error(f"Network error: {e}")
            raise Exception(f"Network error: {str(e)}")

    async def get_exchange_rate(self, currency: str, amount_usd: float) -> float:
        """
        Get current exchange rate and calculate crypto amount

        Args:
            currency: Crypto currency code (BTC, USDT, etc.)
            amount_usd: Amount in USD

        Returns:
            Amount in cryptocurrency
        """
        try:
            # Get minimum payment amount
            result = await self._request("GET", f"/min-amount?currency_from=usd&currency_to={currency.lower()}")
            min_amount = float(result.get("min_amount", 0))

            # Estimate price
            result = await self._request("GET", f"/estimate?amount={amount_usd}&currency_from=usd&currency_to={currency.lower()}")
            crypto_amount = float(result.get("estimated_amount", 0))

            if crypto_amount < min_amount:
                logger.warning(f"Amount {crypto_amount} {currency} is below minimum {min_amount}")

            return crypto_amount

        except Exception as e:
            logger.error(f"Failed to get exchange rate: {e}")
            # Fallback estimates (approximate, should be updated)
            fallback_rates = {
                "BTC": amount_usd / 50000,  # ~$50k per BTC
                "USDT": amount_usd,  # 1:1 with USD
                "USDTERC20": amount_usd,
                "ETH": amount_usd / 3000,  # ~$3k per ETH
                "TON": amount_usd / 5,  # ~$5 per TON
            }
            return fallback_rates.get(currency, amount_usd)

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
            amount: Amount in USD cents (e.g., 1000 = $10.00)
            currency: Crypto currency code (BTC, USDT, etc.)
            description: Payment description
            expires_in_minutes: Invoice expiry time
            metadata: Additional metadata

        Returns:
            Created Invoice object
        """
        amount_usd = amount / 100.0  # Convert cents to dollars

        # Get crypto amount
        crypto_amount = await self.get_exchange_rate(currency, amount_usd)

        # Generate invoice ID
        invoice_id = self.generate_invoice_id()

        # Create payment via NOWPayments API
        try:
            payment_data = {
                "price_amount": amount_usd,
                "price_currency": "usd",
                "pay_currency": currency.lower(),
                "order_id": invoice_id,
                "order_description": description or f"Payment {invoice_id}",
                "ipn_callback_url": metadata.get("callback_url") if metadata else None,
            }

            result = await self._request("POST", "/payment", payment_data)

            invoice = Invoice(
                id=invoice_id,
                amount=amount,
                currency=currency,
                status=PaymentStatus.PENDING,
                wallet_address=result.get("pay_address"),
                crypto_amount=str(crypto_amount),
                exchange_rate=amount_usd / crypto_amount if crypto_amount > 0 else 0,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
                metadata={
                    "provider": "nowpayments",
                    "payment_id": result.get("payment_id"),
                    "pay_amount": result.get("pay_amount"),
                    "payment_url": result.get("invoice_url"),
                    **(metadata or {})
                }
            )

            logger.info(f"Created crypto invoice {invoice_id}: {amount_usd} USD → {crypto_amount} {currency}")
            return invoice

        except Exception as e:
            logger.error(f"Failed to create invoice: {e}")
            raise

    async def check_payment(self, invoice_id: str) -> PaymentStatus:
        """
        Check payment status

        Args:
            invoice_id: Invoice ID to check

        Returns:
            Current payment status
        """
        try:
            # Get payment status from NOWPayments
            result = await self._request("GET", f"/payment/{invoice_id}")

            payment_status = result.get("payment_status", "").lower()

            # Map NOWPayments status to our status
            status_map = {
                "waiting": PaymentStatus.PENDING,
                "confirming": PaymentStatus.PENDING,
                "confirmed": PaymentStatus.PENDING,
                "sending": PaymentStatus.PENDING,
                "finished": PaymentStatus.COMPLETED,
                "partially_paid": PaymentStatus.PENDING,
                "failed": PaymentStatus.FAILED,
                "refunded": PaymentStatus.REFUNDED,
                "expired": PaymentStatus.EXPIRED,
            }

            return status_map.get(payment_status, PaymentStatus.PENDING)

        except Exception as e:
            logger.error(f"Failed to check payment status for {invoice_id}: {e}")
            return PaymentStatus.PENDING

    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """
        Get invoice details

        Args:
            invoice_id: Invoice ID

        Returns:
            Invoice object or None if not found
        """
        try:
            result = await self._request("GET", f"/payment/{invoice_id}")

            status = await self.check_payment(invoice_id)

            invoice = Invoice(
                id=invoice_id,
                amount=int(float(result.get("price_amount", 0)) * 100),  # USD to cents
                currency=result.get("pay_currency", "").upper(),
                status=status,
                wallet_address=result.get("pay_address"),
                crypto_amount=result.get("pay_amount"),
                tx_hash=result.get("outcome_hash"),
                confirmations=result.get("outcome_confirmations", 0),
                created_at=datetime.fromisoformat(result.get("created_at")) if result.get("created_at") else datetime.now(timezone.utc),
                completed_at=datetime.fromisoformat(result.get("updated_at")) if result.get("updated_at") and status == PaymentStatus.COMPLETED else None,
                metadata={
                    "provider": "nowpayments",
                    "payment_id": result.get("payment_id"),
                    "payment_status": result.get("payment_status"),
                }
            )

            return invoice

        except Exception as e:
            logger.error(f"Failed to get invoice {invoice_id}: {e}")
            return None

    async def process_webhook(self, data: Dict[str, Any], signature: str = "") -> bool:
        """
        Process IPN (Instant Payment Notification) webhook from NOWPayments

        Args:
            data: Webhook payload data (parsed JSON body)
            signature: Value of x-nowpayments-sig HTTP header

        Returns:
            True if processed successfully
        """
        try:
            # Verify signature
            if not self._verify_ipn_signature(data, signature):
                logger.warning("Invalid IPN signature")
                return False

            payment_status = data.get("payment_status", "").lower()
            order_id = data.get("order_id")

            if payment_status == "finished":
                logger.info(f"Payment completed: {order_id}")
                return True

            elif payment_status in ["failed", "expired"]:
                logger.info(f"Payment {payment_status}: {order_id}")
                return True

            return True

        except Exception as e:
            logger.error(f"Failed to process webhook: {e}")
            return False

    def _verify_ipn_signature(self, data: Dict[str, Any], signature: str) -> bool:
        """
        Verify IPN signature from NOWPayments.

        NOWPayments signs the JSON body:
        1. Sort body keys alphabetically
        2. JSON-encode with sorted keys (compact separators)
        3. HMAC-SHA512 with IPN secret as key
        4. Compare with x-nowpayments-sig header value
        """
        if not self.ipn_secret:
            logger.error("IPN secret not configured — rejecting webhook to prevent unauthorized payment confirmation")
            return False

        if not signature:
            logger.warning("Missing x-nowpayments-sig header")
            return False

        try:
            import json

            # Sort body keys and create compact JSON
            sorted_data = dict(sorted(data.items()))
            signature_string = json.dumps(sorted_data, separators=(",", ":"))

            # Calculate HMAC-SHA512
            calculated = hmac.new(
                self.ipn_secret.encode(),
                signature_string.encode(),
                hashlib.sha512
            ).hexdigest()

            return hmac.compare_digest(signature, calculated)

        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    async def get_available_currencies(self) -> list:
        """Get list of available currencies from NOWPayments"""
        try:
            result = await self._request("GET", "/currencies")
            return result.get("currencies", [])
        except Exception as e:
            logger.error(f"Failed to get available currencies: {e}")
            return list(self._currencies.keys())

    async def get_payment_url(self, invoice_id: str) -> Optional[str]:
        """Get payment page URL for invoice"""
        invoice = await self.get_invoice(invoice_id)
        if invoice and invoice.metadata:
            return invoice.metadata.get("payment_url")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# ALTERNATIVE: CoinGate Provider (if needed)
# ═══════════════════════════════════════════════════════════════════════════

class CoinGatePaymentProvider(PaymentProvider):
    """
    Alternative cryptocurrency payment provider using CoinGate API
    Similar to NOWPayments but different API
    """

    def __init__(self, api_token: str, sandbox: bool = False):
        self.api_token = api_token
        self.api_url = "https://api-sandbox.coingate.com/v2" if sandbox else "https://api.coingate.com/v2"
        self.sandbox = sandbox

    @property
    def name(self) -> str:
        return "coingate"

    @property
    def display_name(self) -> str:
        return "CoinGate Crypto"

    @property
    def currencies(self) -> list:
        return ["BTC", "USDT", "ETH", "LTC"]

    async def create_invoice(self, amount: int, currency: str, **kwargs) -> Invoice:
        """Create invoice via CoinGate"""
        # Implementation similar to CryptoPaymentProvider
        # Left as exercise or can be implemented if needed
        pass

    async def check_payment(self, invoice_id: str) -> PaymentStatus:
        pass

    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        pass

    async def process_webhook(self, data: Dict[str, Any]) -> bool:
        pass
