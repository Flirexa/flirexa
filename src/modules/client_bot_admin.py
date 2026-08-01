"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `telegram_client_bot` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "telegram_client_bot"
_UPGRADE_HINT = (
    "This component requires the telegram_client_bot commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


from fastapi import HTTPException

def get_client_config(mask_token) -> dict:
    return {"client_bot_token_masked": "", "client_bot_enabled": False}

def prepare_client_config(config, mask_token) -> tuple[dict, dict]:
    if config.client_bot_token is None and config.client_bot_enabled is None:
        return {}, {}
    raise HTTPException(status_code=403, detail=_UPGRADE_HINT)

def restart_after_config(env_updates: dict, control_service):
    return None

def get_client_status(get_service_status) -> dict:
    return {"is_running": False, "pid": None, "uptime": None, "uptime_seconds": None, "service": "vpnmanager-client-bot", "status": "stopped"}

def control_client(action: str, control_service) -> bool:
    raise HTTPException(status_code=403, detail=_UPGRADE_HINT)

def restart_client_if_entitled(control_service) -> bool:
    return False
