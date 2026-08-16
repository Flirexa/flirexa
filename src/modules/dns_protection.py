"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `dns_protection` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "dns_protection"
_UPGRADE_HINT = (
    "This component requires the dns_protection commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


class DnsProtectionError(ValueError):
    pass

def resolve_dns_for_client(db, client, server) -> str:
    return server.dns

def portal_state(*args, **kwargs):
    return {'available': False, 'advanced': False, 'enabled': False, 'profiles': []}

def select_portal_profile(*args, **kwargs):
    raise DnsProtectionError(_UPGRADE_HINT)
