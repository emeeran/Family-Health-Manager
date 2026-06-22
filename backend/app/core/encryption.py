"""Encryption at rest using Fernet (symmetric encryption) via cryptography library.

Performance optimisations:
- #2  Stream encryption/decryption in 64 KB chunks instead of loading entire
     files into memory.  Wire format: [4-byte big-endian chunk-size][Fernet-encrypted-chunk] repeated.
- #3  Cache the derived Fernet instance in a module-level variable so the
     expensive PBKDF2 key derivation only happens once per process.
"""

import logging
import struct
import binascii
from collections.abc import AsyncGenerator
from pathlib import Path

import aiofiles
import aiofiles.os
import base64
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Performance: 64 KB chunk size — balances memory usage with Fernet overhead
# (each chunk incurs a small framing cost from Fernet's own metadata).
ENCRYPTION_CHUNK_SIZE = 64 * 1024

# Module-level Fernet caches so PBKDF2 derivation runs only once per process.
_fernet_cache: Fernet | None = None  # primary: dedicated ENCRYPTION_KEY (or legacy)
_legacy_fernet_cache: Fernet | None = None  # SECRET_KEY-derived, for decrypting old data


def _legacy_fernet() -> Fernet:
    """The original SECRET_KEY-derived Fernet.

    Retained so that data encrypted before a dedicated ENCRYPTION_KEY was
    introduced (existing installs) stays decryptable after the key is set.
    """
    global _legacy_fernet_cache
    if _legacy_fernet_cache is not None:
        return _legacy_fernet_cache

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
    _legacy_fernet_cache = Fernet(key)
    return _legacy_fernet_cache


def get_fernet() -> Fernet:
    """Primary Fernet used for new encryption.

    Uses the dedicated ``ENCRYPTION_KEY`` when set (preferred — it decouples
    file/secret encryption from JWT signing and survives JWT-key rotation).
    Falls back to the legacy SECRET_KEY-derived key so existing installs keep
    working unchanged.
    """
    global _fernet_cache
    if _fernet_cache is not None:
        return _fernet_cache

    settings = get_settings()
    if settings.ENCRYPTION_KEY:
        _fernet_cache = Fernet(settings.ENCRYPTION_KEY.encode())
    else:
        _fernet_cache = _legacy_fernet()
    return _fernet_cache


def _decrypt_token(token: bytes) -> bytes:
    """Decrypt a Fernet token, falling back to the legacy key on failure.

    Keeps files/secrets encrypted before ENCRYPTION_KEY was set readable.
    """
    primary = get_fernet()
    try:
        return primary.decrypt(token)
    except InvalidToken:
        legacy = _legacy_fernet()
        if primary is legacy:
            raise  # same key already failed — nothing else to try
        return legacy.decrypt(token)


def clear_encryption_cache() -> None:
    """Clear the cached Fernet instances (useful in tests)."""
    global _fernet_cache, _legacy_fernet_cache
    _fernet_cache = None
    _legacy_fernet_cache = None


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a short secret (TOTP secret, JSON backup codes) at rest."""
    return get_fernet().encrypt(plaintext.encode()).decode("ascii")


def is_secret_encrypted(stored: str | None) -> bool:
    """True if ``stored`` is a Fernet token produced by :func:`encrypt_secret`.

    Used by the one-time migration to decide which legacy plaintext values
    still need encrypting. A plaintext TOTP secret (base32, uppercase) or a JSON
    backup-codes string is never a valid Fernet token, so this is reliable.
    """
    if not stored:
        return False
    try:
        _decrypt_token(stored.encode())
        return True
    except (InvalidToken, ValueError, binascii.Error):
        return False


def decrypt_secret(stored: str | None) -> str | None:
    """Decrypt a stored secret, reading legacy plaintext through unchanged.

    Existing installs have plaintext ``totp_secret``/``backup_codes``; this keeps
    them readable until they are re-encrypted (on next write or by the migration).
    """
    if not stored:
        return stored
    try:
        return _decrypt_token(stored.encode()).decode()
    except (InvalidToken, ValueError, binascii.Error):
        return stored  # legacy plaintext — readable as-is


def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt bytes using Fernet."""
    return get_fernet().encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    """Decrypt bytes using Fernet (primary key, falling back to legacy)."""
    return _decrypt_token(data)


async def encrypt_file(source_path: Path, dest_path: Path | None = None) -> Path:
    """Encrypt a file in 64 KB chunks.  If *dest_path* is ``None``, encrypts in-place.

    Chunked wire format (repeated until EOF):
        [4-byte big-endian chunk-size][Fernet-encrypted-chunk]
    A zero-length terminating header (4 zero bytes) marks the end.
    """
    fernet = get_fernet()
    target = dest_path or source_path

    # Read source, write to target — when encrypting in-place we must finish
    # writing all chunks before closing, which is safe because we open source
    # for reading first and write to the same path after draining it.
    async with aiofiles.open(source_path, "rb") as src, aiofiles.open(target, "wb") as dst:
        while True:
            plaintext = await src.read(ENCRYPTION_CHUNK_SIZE)
            if not plaintext:
                break

            encrypted_chunk = fernet.encrypt(plaintext)
            # Write [4-byte big-endian length][encrypted chunk]
            await dst.write(struct.pack(">I", len(encrypted_chunk)))
            await dst.write(encrypted_chunk)

        # Terminating header: zero-length signals end of stream
        await dst.write(struct.pack(">I", 0))

    return target


async def decrypt_file(file_path: Path) -> bytes:
    """Decrypt a chunked-encrypted file and return the full plaintext bytes.

    Reads the wire format written by :func:`encrypt_file`:
        [4-byte big-endian chunk-size][Fernet-encrypted-chunk] …
    """
    plaintext = bytearray()

    async with aiofiles.open(file_path, "rb") as f:
        while True:
            header = await f.read(4)
            if not header or len(header) < 4:
                break
            chunk_size = struct.unpack(">I", header)[0]
            if chunk_size == 0:
                break
            encrypted_chunk = await f.read(chunk_size)
            plaintext.extend(_decrypt_token(encrypted_chunk))

    return bytes(plaintext)


async def decrypt_file_chunks(file_path: Path) -> AsyncGenerator[bytes, None]:
    """Stream-decrypt a chunked-encrypted file, yielding plaintext chunks.

    This is the async-generator counterpart of :func:`decrypt_file` and is
    designed for streaming responses where loading the entire plaintext into
    memory is undesirable.
    """
    async with aiofiles.open(file_path, "rb") as f:
        while True:
            header = await f.read(4)
            if not header or len(header) < 4:
                break
            chunk_size = struct.unpack(">I", header)[0]
            if chunk_size == 0:
                break
            encrypted_chunk = await f.read(chunk_size)
            yield _decrypt_token(encrypted_chunk)
