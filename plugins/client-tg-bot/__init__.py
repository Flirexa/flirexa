"""client-tg-bot — full Telegram self-service bot for end users."""

from fastapi import APIRouter

from src.modules.plugin_loader import Plugin


router = APIRouter(prefix="/api/v1/plugins/client-tg-bot", tags=["plugins"])


@router.get("/status")
async def status():
    return {"plugin": "client-tg-bot", "version": "1.0.0", "active": True}


class ClientTgBotPlugin(Plugin):
    def get_router(self):
        return router


_MANIFEST = {
    "name": "client-tg-bot",
    "version": "1.0.0",
    "display_name": "Client Telegram Bot",
    "requires_license_feature": "telegram_client_bot",
}

PLUGIN = ClientTgBotPlugin(_MANIFEST)
