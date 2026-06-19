"""Local filesystem storage backend with content-addressable storage.

Performance optimisation (#10):
When ``decrypt=True``, ``stream()`` now decrypts on-the-fly using the chunked
wire format defined in ``encryption.py`` instead of loading the entire file
into memory before yielding the first byte.
"""

import logging
import struct
from pathlib import Path
from collections.abc import AsyncGenerator

import aiofiles
import aiofiles.os

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MB


class LocalStorageBackend:
    """Local filesystem storage backend using sharded content-addressable paths."""

    def __init__(self) -> None:
        settings = get_settings()
        self.storage_path = Path(settings.STORAGE_PATH)
        self.files_dir = self.storage_path / "files"

    def _hash_to_path(self, content_hash: str, ext: str) -> Path:
        """Return sharded content-addressable path."""
        shard = content_hash[:2]
        shard_dir = self.files_dir / shard
        shard_dir.mkdir(parents=True, exist_ok=True)
        return shard_dir / f"{content_hash}{ext}"

    async def put(self, content_hash: str, ext: str, data: bytes, encrypt: bool = False) -> Path:
        """Store data at a content-addressable path.

        When *encrypt* is ``True`` the data is written in the chunked wire
        format defined in ``encryption.py``:
            ``[4-byte big-endian chunk-size][Fernet-encrypted-chunk]`` repeated,
            terminated by a zero-length header.
        """
        file_path = self._hash_to_path(content_hash, ext)

        if file_path.exists():
            return file_path

        if encrypt:
            # Performance: encrypt in chunks and write the chunked wire format
            # so that stream() can later decrypt on-the-fly without loading
            # the entire file into memory.
            from app.core.encryption import ENCRYPTION_CHUNK_SIZE, get_fernet

            fernet = get_fernet()
            async with aiofiles.open(file_path, "wb") as f:
                offset = 0
                while offset < len(data):
                    plaintext_chunk = data[offset : offset + ENCRYPTION_CHUNK_SIZE]
                    encrypted_chunk = fernet.encrypt(plaintext_chunk)
                    await f.write(struct.pack(">I", len(encrypted_chunk)))
                    await f.write(encrypted_chunk)
                    offset += ENCRYPTION_CHUNK_SIZE
                # Terminating header
                await f.write(struct.pack(">I", 0))
        else:
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(data)

        return file_path

    async def get(self, file_path: Path, decrypt: bool = False) -> bytes:
        """Read file content from storage.

        When *decrypt* is ``True`` the file is expected to be in the chunked
        wire format written by :meth:`put`.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if decrypt:
            from app.core.encryption import get_fernet

            fernet = get_fernet()
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
                    plaintext.extend(fernet.decrypt(encrypted_chunk))

            return bytes(plaintext)

        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()

    async def stream(self, file_path: Path, decrypt: bool = False) -> AsyncGenerator[bytes, None]:
        """Stream file content in chunks.

        #10 Performance: when *decrypt* is ``True``, each encrypted chunk is
        decrypted and yielded immediately — no need to buffer the entire file.
        """
        if decrypt:
            # Stream-decrypt: read chunk headers, decrypt each, yield plaintext
            from app.core.encryption import get_fernet

            fernet = get_fernet()

            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            async with aiofiles.open(file_path, "rb") as f:
                while True:
                    header = await f.read(4)
                    if not header or len(header) < 4:
                        break
                    chunk_size = struct.unpack(">I", header)[0]
                    if chunk_size == 0:
                        break
                    encrypted_chunk = await f.read(chunk_size)
                    yield fernet.decrypt(encrypted_chunk)
        else:
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            async with aiofiles.open(file_path, "rb") as f:
                while True:
                    chunk = await f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

    async def delete(self, file_path: Path) -> None:
        """Delete a file from storage."""
        if file_path.exists():
            await aiofiles.os.remove(file_path)

    async def exists(self, file_path: Path) -> bool:
        """Check if a file exists."""
        return file_path.exists()
