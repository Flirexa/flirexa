"""
VPN Management Studio Telegram Bots Module
Admin and Client bots for Telegram integration
"""

from .admin_bot import AdminBot
from .client_bot import ClientBot

__all__ = ["AdminBot", "ClientBot"]
