"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `telegram_client_bot` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "telegram_client_bot"
_UPGRADE_HINT = (
    "This component requires the telegram_client_bot commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


class ClientBotPayments:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(_UPGRADE_HINT)
