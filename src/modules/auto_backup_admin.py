"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `auto_backup` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "auto_backup"
_UPGRADE_HINT = (
    "This component requires the auto_backup commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


from fastapi import HTTPException

def _unavailable():
    raise HTTPException(status_code=403, detail=_UPGRADE_HINT)

def get_backup_settings(db):
    return _unavailable()

def update_backup_settings(data: dict, db):
    return _unavailable()

def mount_network_storage(db):
    return _unavailable()

def unmount_network_storage(db):
    return _unavailable()

def get_storage_status(db):
    return _unavailable()

def test_backup_write(db):
    return _unavailable()
