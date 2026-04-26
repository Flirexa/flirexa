"""
Branding Module — White-label configuration from SystemConfig DB
"""

from typing import Optional, Dict
from loguru import logger

# Default branding values (used when no DB config exists)
BRANDING_DEFAULTS = {
    "branding_app_name": "VPN Management Studio",
    "branding_company_name": "",
    "branding_logo_url": "",
    "branding_favicon_url": "",
    "branding_primary_color": "#0d6efd",
    "branding_login_title": "Admin Panel",
    "branding_support_email": "",
    "branding_support_url": "",
    "branding_footer_text": "",
}

# In-memory cache (refreshed on API call)
_branding_cache: Optional[Dict[str, str]] = None


def get_branding(key: str, db=None) -> str:
    """
    Get a single branding value.

    Args:
        key: Branding key (e.g. 'branding_app_name')
        db: Optional SQLAlchemy session. If None, returns from cache or default.

    Returns:
        Branding value string
    """
    global _branding_cache

    if _branding_cache and key in _branding_cache:
        return _branding_cache[key]

    if db:
        _load_branding_from_db(db)
        if _branding_cache and key in _branding_cache:
            return _branding_cache[key]

    return BRANDING_DEFAULTS.get(key, "")


def get_all_branding(db=None) -> Dict[str, str]:
    """
    Get all branding values as a dict.

    Args:
        db: Optional SQLAlchemy session

    Returns:
        Dict of all branding key-value pairs
    """
    global _branding_cache

    if db:
        _load_branding_from_db(db)

    if _branding_cache:
        # Merge defaults with cached (cached values override defaults)
        result = dict(BRANDING_DEFAULTS)
        result.update(_branding_cache)
        return result

    return dict(BRANDING_DEFAULTS)


def set_branding(updates: Dict[str, str], db) -> Dict[str, str]:
    """
    Save branding values to SystemConfig DB.

    Args:
        updates: Dict of branding key-value pairs to update
        db: SQLAlchemy session

    Returns:
        Updated branding dict
    """
    global _branding_cache
    from ..database.models import SystemConfig

    for key, value in updates.items():
        if key not in BRANDING_DEFAULTS:
            continue

        existing = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if existing:
            existing.value = str(value)
        else:
            db.add(SystemConfig(key=key, value=str(value)))

    db.commit()

    # Refresh cache
    _load_branding_from_db(db)

    return get_all_branding()


def invalidate_cache():
    """Clear the branding cache (e.g. after DB update)"""
    global _branding_cache
    _branding_cache = None


def _load_branding_from_db(db):
    """Load branding values from SystemConfig into cache"""
    global _branding_cache

    try:
        from ..database.models import SystemConfig

        keys = list(BRANDING_DEFAULTS.keys())
        rows = db.query(SystemConfig).filter(SystemConfig.key.in_(keys)).all()

        _branding_cache = {}
        for row in rows:
            _branding_cache[row.key] = row.value

    except Exception as e:
        logger.debug(f"Failed to load branding from DB: {e}")
        _branding_cache = {}


def get_app_name(db=None) -> str:
    """Shortcut to get the app name"""
    return get_branding("branding_app_name", db)
