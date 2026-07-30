"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `payments` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "payments"
_UPGRADE_HINT = (
    "This component requires the payments commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


PAID_SETTING_FIELDS = {
    'cryptopay_api_token', 'cryptopay_testnet',
    'paypal_client_id', 'paypal_client_secret', 'paypal_sandbox',
    'paypal_webhook_id', 'stripe_secret_key', 'stripe_webhook_secret',
    'payme_merchant_id', 'payme_secret_key', 'mollie_api_key',
    'razorpay_key_id', 'razorpay_key_secret',
    'razorpay_webhook_secret',
}

def get_settings_snapshot(*args, **kwargs) -> dict:
    return {
        'cryptopay_configured': False, 'cryptopay_token_masked': '',
        'cryptopay_testnet': False, 'paypal_configured': False,
        'paypal_client_id_masked': '', 'paypal_sandbox': True,
        'paypal_webhook_id_masked': '', 'stripe_configured': False,
        'stripe_key_masked': '', 'payme_configured': False,
        'payme_id_masked': '', 'mollie_configured': False,
        'mollie_key_masked': '', 'razorpay_configured': False,
        'razorpay_key_masked': '',
    }

def collect_env_updates(data) -> dict[str, str]:
    explicit = data.model_fields_set
    mapping = {
        'cryptopay_api_token': 'CRYPTOPAY_API_TOKEN',
        'paypal_client_id': 'PAYPAL_CLIENT_ID',
        'paypal_client_secret': 'PAYPAL_CLIENT_SECRET',
        'paypal_webhook_id': 'PAYPAL_WEBHOOK_ID',
        'stripe_secret_key': 'STRIPE_SECRET_KEY',
        'stripe_webhook_secret': 'STRIPE_WEBHOOK_SECRET',
        'payme_merchant_id': 'PAYME_MERCHANT_ID',
        'payme_secret_key': 'PAYME_SECRET_KEY',
        'mollie_api_key': 'MOLLIE_API_KEY',
        'razorpay_key_id': 'RAZORPAY_KEY_ID',
        'razorpay_key_secret': 'RAZORPAY_KEY_SECRET',
        'razorpay_webhook_secret': 'RAZORPAY_WEBHOOK_SECRET',
    }
    updates = {env: str(getattr(data, field)) for field, env in mapping.items()
               if field in explicit and getattr(data, field) is not None}
    for field, env in {'cryptopay_testnet': 'CRYPTOPAY_TESTNET',
                       'paypal_sandbox': 'PAYPAL_SANDBOX'}.items():
        if field in explicit and getattr(data, field) is not None:
            updates[env] = 'true' if getattr(data, field) else 'false'
    return updates

async def reload_paid_providers(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

async def test_paid_provider(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)
