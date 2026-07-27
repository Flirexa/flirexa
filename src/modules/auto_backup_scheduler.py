"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `auto_backup` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "auto_backup"
_UPGRADE_HINT = (
    "This component requires the auto_backup commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


def backup_cycle() -> None:
    return None

async def backup_loop() -> None:
    return None
