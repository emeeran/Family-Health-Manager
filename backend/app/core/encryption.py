"""Encryption at rest using Fernet (symmetric encryption) via cryptography library."""
import logging
from pathlib import Path

import aiofiles
import aiofiles.os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Cache the Fernet instance per-process
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the application SECRET_KEY using PBKDF2."""
    global _fernet
    if _fernet is not None:
        return _fernet

    settings = get_settings()
    # Static salt derived from app name for deterministic key derivation
    salt = b"health-manager-encryption-salt-v1"

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(settings.SECRET_KEY.encode()))
    _fernet = Fernet(key)
    return _fernet


def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt bytes using Fernet."""
    return _get_fernet().encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    """Decrypt bytes using Fernet."""
    return _get_fernet().decrypt(data)


async def encrypt_file(source_path: Path, dest_path: Path | None = None) -> Path:
    """Encrypt a file. If dest_path is None, encrypts in-place."""
    async with aiofiles.open(source_path, "rb") as f:
        plaintext = await f.read()

    ciphertext = encrypt_bytes(plaintext)

    target = dest_path or source_path
    async with aiofiles.open(target, "wb") as f:
        await f.write(ciphertext)

    return target


async def decrypt_file(file_path: Path) -> bytes:
    """Decrypt a file and return the plaintext bytes."""
    async with aiofiles.open(file_path, "rb") as f:
        ciphertext = await f.read()

    return decrypt_bytes(ciphertext)
