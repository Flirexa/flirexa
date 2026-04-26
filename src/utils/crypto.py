"""
VPN Management Studio Cryptographic Utilities
For encrypting/decrypting sensitive data (private keys, etc.)
"""

import os
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from loguru import logger


def get_encryption_key() -> bytes:
    """
    Get or generate the encryption key

    Uses ENCRYPTION_KEY environment variable or generates from SECRET_KEY
    """
    env_key = os.getenv("ENCRYPTION_KEY")
    if env_key:
        # Use provided key directly (should be Fernet-compatible base64)
        return env_key.encode()

    # Derive key from SECRET_KEY, or fall back to a host-specific secret.
    secret_key = os.getenv("SECRET_KEY", "")
    if not secret_key:
        try:
            with open("/etc/machine-id", "r", encoding="utf-8") as f:
                machine_id = f.read().strip()
            secret_key = hashlib.sha256(
                f"vpnmanager-utils-crypto-{machine_id}".encode()
            ).hexdigest()
        except Exception:
            secret_key = hashlib.sha256(
                b"vpnmanager-utils-crypto-fallback"
            ).hexdigest()
    salt = os.getenv("ENCRYPTION_SALT", "vpnmanager-salt").encode()

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )

    key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
    return key


def encrypt_key(plain_text: str) -> str:
    """
    Encrypt a private key or sensitive data

    Args:
        plain_text: Plain text to encrypt

    Returns:
        Base64-encoded encrypted data
    """
    try:
        key = get_encryption_key()
        f = Fernet(key)
        encrypted = f.encrypt(plain_text.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        # Return plain text if encryption fails (not recommended for production)
        return plain_text


def decrypt_key(encrypted_text: str) -> str:
    """
    Decrypt an encrypted private key

    Args:
        encrypted_text: Base64-encoded encrypted data

    Returns:
        Decrypted plain text
    """
    try:
        # Check if it's actually encrypted (starts with encryption marker)
        if not encrypted_text.startswith("gAAA"):
            # Might be plain text, return as-is
            return encrypted_text

        key = get_encryption_key()
        f = Fernet(key)
        decrypted = f.decrypt(base64.urlsafe_b64decode(encrypted_text))
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        # Return as-is if decryption fails (might be plain text)
        return encrypted_text


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key

    Returns:
        Base64-encoded encryption key
    """
    return Fernet.generate_key().decode()


def is_encrypted(text: str) -> bool:
    """
    Check if text appears to be encrypted

    Args:
        text: Text to check

    Returns:
        True if appears encrypted
    """
    # Fernet tokens start with "gAAA"
    return text.startswith("gAAA") and len(text) > 100
