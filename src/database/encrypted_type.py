"""
VPN Management Studio — Transparent column encryption using Fernet (AES-128-CBC + HMAC).

Usage in models:
    from src.database.encrypted_type import EncryptedText
    ssh_password = mapped_column(EncryptedText(), nullable=True)

The key is derived from VMS_ENCRYPTION_KEY env var (set by installer).
Fallback to /etc/machine-id only if env var is not set — WARNING: machine-id
changes on server migration, making encrypted data unreadable on a new host.
Existing plain-text values are read as-is and will be encrypted on next write.
"""

import os
import sys
import hashlib
import base64
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


def _derive_key() -> bytes:
    """Derive a stable Fernet key from VMS_ENCRYPTION_KEY env var or machine-id fallback."""
    raw = os.getenv("VMS_ENCRYPTION_KEY", "")
    if not raw:
        if os.getenv("VMS_SUPPRESS_ENCRYPTION_WARNING", "0") != "1":
            print(
                "WARNING: VMS_ENCRYPTION_KEY is not set. Falling back to /etc/machine-id. "
                "Encrypted data will be unreadable if you migrate to a different server. "
                "Set VMS_ENCRYPTION_KEY in .env to fix this.",
                file=sys.stderr,
            )
        try:
            with open("/etc/machine-id", "r") as f:
                raw = f.read().strip()
        except Exception:
            raw = "vpnmanager-fallback-encryption-key"
    # Fernet needs 32 url-safe base64 bytes
    digest = hashlib.sha256(f"vpnmanager-field-enc-{raw}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_key())

# Prefix to distinguish encrypted values from legacy plain-text
_ENC_PREFIX = "enc::"


class EncryptedText(TypeDecorator):
    """SQLAlchemy column type that transparently encrypts/decrypts Text values."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt before storing."""
        if value is None:
            return None
        token = _fernet.encrypt(value.encode("utf-8")).decode("ascii")
        return f"{_ENC_PREFIX}{token}"

    def process_result_value(self, value, dialect):
        """Decrypt when reading.  Legacy plain-text values pass through."""
        if value is None:
            return None
        if value.startswith(_ENC_PREFIX):
            token = value[len(_ENC_PREFIX):]
            try:
                return _fernet.decrypt(token.encode("ascii")).decode("utf-8")
            except InvalidToken:
                return value  # corrupted — return raw
        # Legacy plain-text (not yet encrypted) — return as-is
        return value
