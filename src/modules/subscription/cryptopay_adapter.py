"""
VPN Management Studio Client Portal - CryptoPay Adapter
Integration with CryptoPay (Telegram @CryptoBot) for cryptocurrency payments

Docs: https://help.send.tg/en/articles/10279948-crypto-pay-api
SDK: https://github.com/Fomalhaut88/aiocryptopay

Supported: BTC, TON, USDT, USDC, BUSD, ETH (testnet)
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
import logging
from enum import Enum

# pip install aiocryptopay
from aiocryptopay import AioCryptoPay, Networks
from aiocryptopay.models.invoice import Invoice

logger = logging.getLogger(__name__)


class CryptoAsset(str, Enum):
    """Supported cryptocurrencies"""
    BTC = "BTC"
    TON = "TON"
    USDT = "USDT"
    USDC = "USDC"
    BUSD = "BUSD"
    ETH = "ETH"  # Testnet only


class CryptoPayAdapter:
    """
    Adapter for CryptoPay API (@CryptoBot)

    Setup:
        1. Open @CryptoBot in Telegram
        2. Go to Crypto Pay → Create App
        3. Get API token
        4. Set webhook URL (optional)

    Usage:
        adapter = CryptoPayAdapter("YOUR_API_TOKEN")
        invoice = await adapter.create_invoice(
            amount_usd=10.0,
            currency="USDT",
            description="Basic Plan - 30 days"
        )
    """

    def __init__(self, api_token: str, testnet: bool = False):
        self.api_token = api_token
        self.testnet = testnet
        network = Networks.TEST_NET if testnet else Networks.MAIN_NET
        self.client = AioCryptoPay(token=api_token, network=network)

        # Currency display names
        self.currency_names = {
            "BTC": "Bitcoin",
            "TON": "Toncoin",
            "USDT": "Tether",
            "USDC": "USD Coin",
            "BUSD": "Binance USD",
            "ETH": "Ethereum (Testnet)"
        }

    async def get_app_info(self) -> Dict[str, Any]:
        """Get information about your app"""
        try:
            app = await self.client.get_me()
            return {
                "id": app.app_id,
                "name": app.name,
                "payment_methods": []
            }
        except Exception as e:
            logger.error(f"Failed to get app info: {e}")
            return {}

    async def get_balance(self) -> Dict[str, float]:
        """Get balances for all currencies"""
        try:
            balances = await self.client.get_balance()
            return {
                balance.currency_code: float(balance.available)
                for balance in balances
            }
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return {}

    async def get_exchange_rates(self) -> Dict[str, float]:
        """Get current exchange rates (crypto to USD)"""
        try:
            rates = await self.client.get_exchange_rates()
            return {
                rate.source: float(rate.rate) if rate.target == "USD" else None
                for rate in rates
                if rate.target == "USD"
            }
        except Exception as e:
            logger.error(f"Failed to get exchange rates: {e}")
            # Fallback approximate rates
            return {
                "BTC": 50000.0,
                "TON": 5.0,
                "USDT": 1.0,
                "USDC": 1.0,
                "BUSD": 1.0,
                "ETH": 3000.0
            }

    async def get_currencies(self) -> List[Dict[str, Any]]:
        """Get list of supported currencies"""
        try:
            currencies = await self.client.get_currencies()
            return [
                {
                    "code": curr.code,
                    "name": curr.name,
                    "is_blockchain": curr.is_blockchain,
                    "is_stablecoin": curr.is_stablecoin,
                    "is_fiat": curr.is_fiat,
                    "decimals": curr.decimals
                }
                for curr in currencies
            ]
        except Exception as e:
            logger.error(f"Failed to get currencies: {e}")
            return []

    async def create_invoice(
        self,
        amount_usd: float,
        currency: str = "USDT",
        description: str = "VPN Subscription",
        expires_in_minutes: int = 60,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create payment invoice

        Args:
            amount_usd: Amount in USD
            currency: Cryptocurrency (BTC, USDT, TON, etc.)
            description: Payment description
            expires_in_minutes: Invoice expiry time
            metadata: Additional data (user_id, plan_id, etc.)

        Returns:
            Invoice data with payment URL and crypto amount
        """
        try:
            # Convert USD to crypto amount using exchange rates
            rates = await self.get_exchange_rates()
            rate = rates.get(currency, 1.0)

            if rate == 0:
                rate = 1.0  # Prevent division by zero

            crypto_amount = amount_usd / rate

            # Create invoice (aiocryptopay uses string asset names, not enums)
            invoice = await self.client.create_invoice(
                asset=currency,
                amount=crypto_amount,
                description=description,
                expires_in=expires_in_minutes * 60,  # Convert to seconds
                payload=str(metadata) if metadata else None  # Store metadata
            )

            logger.info(f"Created invoice {invoice.invoice_id}: {amount_usd} USD → {crypto_amount} {currency}")

            return {
                "invoice_id": str(invoice.invoice_id),
                "amount_usd": amount_usd,
                "amount_crypto": crypto_amount,
                "currency": currency,
                "status": invoice.status,
                # bot_invoice_url = t.me/CryptoBot?start=IVxxx — works as inline button in Telegram
                # mini_app_invoice_url = WebApp link — does NOT work as regular button, excluded
                "payment_url": invoice.bot_invoice_url or getattr(invoice, 'pay_url', '') or "",
                "pay_url": getattr(invoice, 'pay_url', ''),
                "web_app_url": getattr(invoice, 'web_app_invoice_url', ''),
                "created_at": invoice.created_at.isoformat() if invoice.created_at else datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)).isoformat(),
                "description": description,
                "metadata": metadata,
                "hash": invoice.hash  # For webhook verification
            }

        except Exception as e:
            logger.error(f"Failed to create invoice: {e}")
            raise

    async def get_invoice(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        """Get invoice status and details"""
        try:
            result = await self.client.get_invoices(invoice_ids=[invoice_id])

            # v0.4.8 returns Invoice, List[Invoice], or None
            if not result:
                return None

            invoice = result[0] if isinstance(result, list) else result

            return {
                "invoice_id": str(invoice.invoice_id),
                "status": invoice.status,
                "amount": invoice.amount,
                "currency": invoice.asset,
                "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
                "paid_at": invoice.paid_at.isoformat() if hasattr(invoice, 'paid_at') and invoice.paid_at else None,
                "description": invoice.description,
                "payment_url": invoice.bot_invoice_url,
                "hash": invoice.hash
            }

        except Exception as e:
            logger.error(f"Failed to get invoice {invoice_id}: {e}")
            return None

    async def check_payment(self, invoice_id: int) -> str:
        """
        Check if invoice is paid

        Returns:
            Status: "paid", "pending", "expired", "cancelled"
        """
        try:
            invoice_data = await self.get_invoice(invoice_id)
            if not invoice_data:
                return "not_found"

            return invoice_data["status"]

        except Exception as e:
            logger.error(f"Failed to check payment for {invoice_id}: {e}")
            return "error"

    async def get_paid_invoices(
        self,
        currency: Optional[str] = None,
        count: int = 100
    ) -> List[Dict[str, Any]]:
        """Get list of paid invoices"""
        try:
            result = await self.client.get_invoices(
                asset=currency,
                status="paid",
                count=count
            )

            if not result:
                return []

            # v0.4.8 returns Invoice, List[Invoice], or None
            items = result if isinstance(result, list) else [result]

            return [
                {
                    "invoice_id": str(inv.invoice_id),
                    "amount": inv.amount,
                    "currency": inv.asset,
                    "status": inv.status,
                    "created_at": inv.created_at.isoformat() if inv.created_at else None,
                    "paid_at": inv.paid_at.isoformat() if hasattr(inv, 'paid_at') and inv.paid_at else None,
                    "description": inv.description
                }
                for inv in items
            ]

        except Exception as e:
            logger.error(f"Failed to get paid invoices: {e}")
            return []

    async def process_webhook(self, body: bytes, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Process webhook update from CryptoPay

        Args:
            body: Request body (JSON bytes)
            headers: Request headers

        Returns:
            Update data with invoice_id and status
        """
        try:
            import json
            import hashlib
            import hmac as hmac_mod

            # Verify HMAC-SHA256 signature (CryptoPay docs)
            # Key = SHA256(api_token), Sign = HMAC-SHA256(key, body)
            signature = headers.get("crypto-pay-api-signature", "")
            if not signature:
                logger.warning("Missing crypto-pay-api-signature header")
                return None

            secret = hashlib.sha256(self.api_token.encode()).digest()
            calculated = hmac_mod.new(secret, body, hashlib.sha256).hexdigest()
            if not hmac_mod.compare_digest(signature, calculated):
                logger.warning("Invalid CryptoPay webhook signature")
                return None

            data = json.loads(body)

            if data.get("update_type") == "invoice_paid":
                payload = data.get("payload", {})
                return {
                    "type": "invoice_paid",
                    "invoice_id": str(payload.get("invoice_id")),
                    "status": payload.get("status"),
                    "amount": payload.get("amount"),
                    "currency": payload.get("asset"),
                    "paid_at": payload.get("paid_at"),
                    "payload": payload.get("payload")  # Metadata
                }

            return {
                "type": data.get("update_type"),
                "data": data.get("payload")
            }

        except Exception as e:
            logger.error(f"Failed to process webhook: {e}")
            return None

    async def transfer(
        self,
        user_id: int,
        currency: str,
        amount: float,
        spend_id: str,
        comment: Optional[str] = None
    ) -> bool:
        """
        Transfer funds to user (for refunds or payouts)

        Args:
            user_id: Telegram user ID
            currency: Currency code
            amount: Amount to transfer
            spend_id: Unique spend ID (prevents double spending)
            comment: Optional comment

        Returns:
            True if successful
        """
        try:
            transfer = await self.client.transfer(
                user_id=user_id,
                asset=currency,
                amount=amount,
                spend_id=spend_id,
                comment=comment
            )

            logger.info(f"Transferred {amount} {currency} to user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to transfer: {e}")
            return False


# ═══════════════════════════════════════════════════════════════════════════
# Helper functions for FastAPI integration
# ═══════════════════════════════════════════════════════════════════════════

async def create_subscription_invoice(
    adapter: CryptoPayAdapter,
    user_id: int,
    plan_name: str,
    amount_usd: float,
    currency: str = "USDT",
    duration_days: int = 30
) -> Dict[str, Any]:
    """Create invoice for subscription purchase"""
    description = f"VPN Manager - {plan_name} ({duration_days} days)"

    metadata = {
        "user_id": user_id,
        "plan_name": plan_name,
        "duration_days": duration_days,
        "type": "subscription"
    }

    return await adapter.create_invoice(
        amount_usd=amount_usd,
        currency=currency,
        description=description,
        expires_in_minutes=60,
        metadata=metadata
    )


# Example usage
if __name__ == "__main__":
    async def main():
        # Initialize adapter
        adapter = CryptoPayAdapter("YOUR_API_TOKEN")

        # Get app info
        app_info = await adapter.get_app_info()
        print(f"App: {app_info}")

        # Get balances
        balances = await adapter.get_balance()
        print(f"Balances: {balances}")

        # Create invoice
        invoice = await adapter.create_invoice(
            amount_usd=10.0,
            currency="USDT",
            description="Test payment",
            metadata={"user_id": 123, "plan": "basic"}
        )
        print(f"Invoice: {invoice['payment_url']}")

        # Check payment
        await asyncio.sleep(5)
        status = await adapter.check_payment(int(invoice["invoice_id"]))
        print(f"Status: {status}")

    asyncio.run(main())
