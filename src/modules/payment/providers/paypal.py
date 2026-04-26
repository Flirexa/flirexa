"""
VPN Management Studio Payment Module - PayPal Provider
Integration with PayPal REST API v2 (Orders)

Docs: https://developer.paypal.com/docs/api/orders/v2/
"""

import httpx
import base64
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from src.modules.payment.base import PaymentProvider, Invoice, PaymentStatus

logger = logging.getLogger(__name__)


class PayPalProvider(PaymentProvider):
    """
    PayPal payment provider using Orders REST API v2.

    Setup:
        1. Create app at https://developer.paypal.com/dashboard/applications
        2. Get Client ID and Client Secret
        3. Configure webhook URL for CHECKOUT.ORDER.APPROVED event

    Usage:
        provider = PayPalProvider(client_id="...", client_secret="...", sandbox=True)
        invoice = await provider.create_invoice(1000, "USD", description="Basic Plan")
    """

    SANDBOX_URL = "https://api-m.sandbox.paypal.com"
    LIVE_URL = "https://api-m.paypal.com"

    def __init__(self, client_id: str, client_secret: str, sandbox: bool = False, webhook_id: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.sandbox = sandbox
        self.webhook_id = webhook_id
        self.api_url = self.SANDBOX_URL if sandbox else self.LIVE_URL

        # OAuth2 token cache
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    @property
    def name(self) -> str:
        return "paypal"

    @property
    def display_name(self) -> str:
        return "PayPal"

    @property
    def currencies(self) -> list:
        return ["USD", "EUR", "GBP"]

    async def _get_access_token(self) -> str:
        """Get OAuth2 access token (cached)"""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self.api_url}/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data="grant_type=client_credentials",
            )
            resp.raise_for_status()
            data = resp.json()

        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)
        return self._access_token

    async def _request(
        self, method: str, endpoint: str, json_data: Optional[dict] = None
    ) -> dict:
        """Make authenticated API request"""
        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            if method == "GET":
                resp = await client.get(f"{self.api_url}{endpoint}", headers=headers)
            elif method == "POST":
                resp = await client.post(
                    f"{self.api_url}{endpoint}", headers=headers, json=json_data
                )
            else:
                raise ValueError(f"Unsupported method: {method}")

            if resp.status_code not in (200, 201):
                logger.error(f"PayPal API error {resp.status_code}: {resp.text}")
                raise Exception(f"PayPal API error: {resp.status_code}")

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
        Create PayPal order.

        Args:
            amount: Amount in cents (e.g., 1000 = $10.00)
            currency: Currency code (USD, EUR, GBP)
            description: Payment description
            expires_in_minutes: Not used by PayPal (orders expire after buyer approval)
            metadata: Additional metadata (should include return_url, cancel_url)
        """
        amount_str = f"{amount / 100:.2f}"
        invoice_id = self.generate_invoice_id()

        return_url = (metadata or {}).get("return_url", "https://example.com/success")
        cancel_url = (metadata or {}).get("cancel_url", "https://example.com/cancel")

        order_data = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": invoice_id,
                    "description": description or "VPN Subscription",
                    "amount": {
                        "currency_code": currency.upper(),
                        "value": amount_str,
                    },
                }
            ],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "payment_method_preference": "IMMEDIATE_PAYMENT_REQUIRED",
                        "return_url": return_url,
                        "cancel_url": cancel_url,
                        "user_action": "PAY_NOW",
                    }
                }
            },
        }

        result = await self._request("POST", "/v2/checkout/orders", order_data)

        # Extract approval URL
        approve_url = ""
        for link in result.get("links", []):
            if link.get("rel") == "payer-action":
                approve_url = link["href"]
                break

        paypal_order_id = result.get("id", "")

        invoice = Invoice(
            id=invoice_id,
            amount=amount,
            currency=currency.upper(),
            status=PaymentStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
            metadata={
                "provider": "paypal",
                "paypal_order_id": paypal_order_id,
                "approval_url": approve_url,
                **(metadata or {}),
            },
        )

        logger.info(
            f"Created PayPal order {paypal_order_id} (invoice {invoice_id}): "
            f"{amount_str} {currency}"
        )
        return invoice

    async def capture_order(self, paypal_order_id: str) -> Dict[str, Any]:
        """
        Capture an approved PayPal order.

        Args:
            paypal_order_id: PayPal order ID (from create_invoice metadata)

        Returns:
            Capture result with status and transaction details
        """
        try:
            result = await self._request(
                "POST", f"/v2/checkout/orders/{paypal_order_id}/capture"
            )

            status = result.get("status", "")
            capture_id = ""
            captures = (
                result.get("purchase_units", [{}])[0]
                .get("payments", {})
                .get("captures", [])
            )
            if captures:
                capture_id = captures[0].get("id", "")

            logger.info(
                f"Captured PayPal order {paypal_order_id}: status={status}, "
                f"capture_id={capture_id}"
            )

            return {
                "status": status,
                "capture_id": capture_id,
                "order_id": paypal_order_id,
                "raw": result,
            }
        except Exception as e:
            logger.error(f"Failed to capture PayPal order {paypal_order_id}: {e}")
            raise

    async def check_payment(self, invoice_id: str) -> PaymentStatus:
        """Check order status by PayPal order ID"""
        try:
            result = await self._request("GET", f"/v2/checkout/orders/{invoice_id}")
            status = result.get("status", "").upper()

            status_map = {
                "CREATED": PaymentStatus.PENDING,
                "SAVED": PaymentStatus.PENDING,
                "APPROVED": PaymentStatus.PENDING,  # Needs capture
                "VOIDED": PaymentStatus.FAILED,
                "COMPLETED": PaymentStatus.COMPLETED,
                "PAYER_ACTION_REQUIRED": PaymentStatus.PENDING,
            }
            return status_map.get(status, PaymentStatus.PENDING)

        except Exception as e:
            logger.error(f"Failed to check PayPal order {invoice_id}: {e}")
            return PaymentStatus.PENDING

    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """Get order details"""
        try:
            result = await self._request("GET", f"/v2/checkout/orders/{invoice_id}")
            status = await self.check_payment(invoice_id)

            pu = result.get("purchase_units", [{}])[0]
            amount_data = pu.get("amount", {})
            amount_value = float(amount_data.get("value", 0))

            return Invoice(
                id=invoice_id,
                amount=int(amount_value * 100),
                currency=amount_data.get("currency_code", "USD"),
                status=status,
                created_at=datetime.now(timezone.utc),
                metadata={"provider": "paypal", "paypal_order_id": invoice_id},
            )
        except Exception as e:
            logger.error(f"Failed to get PayPal order {invoice_id}: {e}")
            return None

    async def process_webhook(self, data: Dict[str, Any]) -> bool:
        """
        Process PayPal webhook event.

        Handles CHECKOUT.ORDER.APPROVED — auto-captures the order.

        Args:
            data: Webhook payload (parsed JSON)

        Returns:
            True if processed successfully
        """
        event_type = data.get("event_type", "")
        resource = data.get("resource", {})

        if event_type == "CHECKOUT.ORDER.APPROVED":
            order_id = resource.get("id")
            if order_id:
                try:
                    capture_result = await self.capture_order(order_id)
                    return capture_result.get("status") == "COMPLETED"
                except Exception as e:
                    logger.error(f"Auto-capture failed for order {order_id}: {e}")
                    return False

        elif event_type == "PAYMENT.CAPTURE.COMPLETED":
            logger.info(f"Payment capture completed: {resource.get('id')}")
            return True

        return True

    async def verify_webhook_signature(
        self, headers: Dict[str, str], body: bytes
    ) -> bool:
        """
        Verify PayPal webhook signature.

        For production: verify via PayPal API /v1/notifications/verify-webhook-signature
        For development/sandbox: skip verification (PayPal sandbox signatures are unreliable)
        """
        if self.sandbox:
            # Sandbox signatures are unreliable, but still validate headers exist
            required_headers = [
                "paypal-transmission-id",
                "paypal-transmission-sig",
                "paypal-cert-url",
            ]
            missing = [h for h in required_headers if not headers.get(h)]
            if missing:
                logger.warning(
                    f"PayPal sandbox webhook missing signature headers: {missing}"
                )
                return False
            logger.info("PayPal sandbox webhook: signature headers present, skipping full verification")
            return True

        if not self.webhook_id:
            logger.error("PayPal webhook_id not configured — cannot verify signature in production")
            return False

        try:
            token = await self._get_access_token()
            verification_data = {
                "auth_algo": headers.get("paypal-auth-algo", ""),
                "cert_url": headers.get("paypal-cert-url", ""),
                "transmission_id": headers.get("paypal-transmission-id", ""),
                "transmission_sig": headers.get("paypal-transmission-sig", ""),
                "transmission_time": headers.get("paypal-transmission-time", ""),
                "webhook_id": self.webhook_id,
                "webhook_event": body.decode("utf-8") if isinstance(body, bytes) else body,
            }

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.api_url}/v1/notifications/verify-webhook-signature",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=verification_data,
                )
                result = resp.json()
                return result.get("verification_status") == "SUCCESS"

        except Exception as e:
            logger.error(f"Webhook signature verification failed: {e}")
            return False

    async def test_connection(self) -> Dict[str, Any]:
        """Test PayPal API connection"""
        try:
            token = await self._get_access_token()
            return {
                "connected": True,
                "sandbox": self.sandbox,
                "message": "PayPal connected successfully",
            }
        except Exception as e:
            return {
                "connected": False,
                "sandbox": self.sandbox,
                "message": str(e),
            }
