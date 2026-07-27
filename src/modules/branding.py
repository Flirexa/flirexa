"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `white_label_basic` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "white_label_basic"
_UPGRADE_HINT = (
    "This component requires the white_label_basic commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


BRANDING_DEFAULTS = {
    "branding_app_name": "Flirexa",
    "branding_customer_app_name": "",
    "branding_customer_logo_url": "",
    "branding_company_name": "",
    "branding_logo_url": "",
    "branding_favicon_url": "",
    "branding_primary_color": "#0d6efd",
    "branding_login_title": "Admin Panel",
    "branding_support_email": "",
    "branding_support_url": "",
    "branding_footer_text": "",
}

def get_branding(key: str, db=None) -> str:
    return BRANDING_DEFAULTS.get(key, "")

def get_all_branding(db=None) -> dict[str, str]:
    return dict(BRANDING_DEFAULTS)

def set_branding(updates: dict[str, str], db) -> dict[str, str]:
    raise RuntimeError(_UPGRADE_HINT)

def invalidate_cache() -> None:
    return None

def get_app_name(db=None) -> str:
    return BRANDING_DEFAULTS["branding_app_name"]
