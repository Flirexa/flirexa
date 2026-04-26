"""
VPN Manager Default Configuration
"""

import os
from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field


def _parse_comma_list_str(val: str) -> List[str]:
    """Parse comma-separated string into list of strings"""
    if not val or not val.strip():
        return []
    return [s.strip() for s in val.split(",") if s.strip()]


def _parse_comma_list_int(val: str) -> List[int]:
    """Parse comma-separated string into list of ints"""
    if not val or not val.strip():
        return []
    return [int(s.strip()) for s in val.split(",") if s.strip()]


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # ========================================================================
    # General
    # ========================================================================
    APP_NAME: str = "VPN Manager"
    APP_VERSION: str = "5.0.0"
    DEBUG: bool = False
    ENV: str = "development"  # development, staging, production

    # Base paths
    BASE_DIR: Path = Path(__file__).parent.parent
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data")))

    # ========================================================================
    # Database
    # ========================================================================
    DATABASE_URL: str = "postgresql://vpnmanager:vpnmanager@localhost:5432/vpnmanager_db"
    SQL_ECHO: bool = False

    # ========================================================================
    # API Server
    # ========================================================================
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 10086
    API_PREFIX: str = "/api/v1"
    API_RELOAD: bool = False

    # Security
    SECRET_KEY: str = Field(
        default="change-me-in-production-use-openssl-rand-hex-32",
        description="Secret key for JWT and encryption"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    ALGORITHM: str = "HS256"

    # CORS (comma-separated in .env, e.g. "http://localhost,https://example.com")
    CORS_ORIGINS: str = "*"

    @property
    def cors_origins_list(self) -> List[str]:
        return _parse_comma_list_str(self.CORS_ORIGINS)

    # ========================================================================
    # WireGuard
    # ========================================================================
    WG_INTERFACE: str = "wg0"
    WG_CONFIG_PATH: str = "/etc/wireguard/wg0.conf"
    WG_CONFIG_DIR: str = "/root"

    # Default server settings
    WG_DEFAULT_ENDPOINT: str = "YOUR_SERVER_IP:51820"
    WG_DEFAULT_DNS: str = "1.1.1.1,1.0.0.1"
    WG_DEFAULT_MTU: int = 1420
    WG_DEFAULT_KEEPALIVE: int = 25

    # IP pools
    WG_IPV4_POOL: str = "10.66.66.0/24"
    WG_IPV6_POOL: str = "fd42:42:42::/64"

    # ========================================================================
    # Telegram Bots
    # ========================================================================
    # Admin Bot
    ADMIN_BOT_TOKEN: Optional[str] = None
    ADMIN_BOT_ALLOWED_USERS: str = ""  # comma-separated user IDs

    @property
    def admin_bot_allowed_users_list(self) -> List[int]:
        return _parse_comma_list_int(self.ADMIN_BOT_ALLOWED_USERS)

    # Client Bot
    CLIENT_BOT_TOKEN: Optional[str] = None
    CLIENT_BOT_ENABLED: bool = False

    # ========================================================================
    # Encryption
    # ========================================================================
    ENCRYPTION_KEY: Optional[str] = None  # For encrypting private keys in DB

    # ========================================================================
    # Logging
    # ========================================================================
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: Optional[str] = None

    # ========================================================================
    # License (Stub)
    # ========================================================================
    LICENSE_KEY: Optional[str] = None
    LICENSE_CHECK_ENABLED: bool = False

    # ========================================================================
    # Payment (Stub)
    # ========================================================================
    PAYMENT_ENABLED: bool = False
    PAYMENT_WEBHOOK_SECRET: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings"""
    return settings


def reload_settings() -> Settings:
    """Reload settings from environment"""
    global settings
    settings = Settings()
    return settings
