"""Local filesystem storage backend with content-addressable storage."""
import logging
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

    async def put(
        self, content_hash: str, ext: str, data: bytes, encrypt: bool = False
    ) -> Path:
        """Store data at a content-addressable path."""
        if encrypt:
            from app.core.encryption import encrypt_bytes
            data = encrypt_bytes(data)

        file_path = self._hash_to_path(content_hash, ext)

        if file_path.exists():
            return file_path

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(data)

        return file_path

    async def get(self, file_path: Path, decrypt: bool = False) -> bytes:
        """Read file content from storage."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        async with aiofiles.open(file_path, "rb") as f:
            data = await f.read()

        if decrypt:
            from app.core.encryption import decrypt_bytes
            data = decrypt_bytes(data)

        return data

    async def stream(
        self, file_path: Path, decrypt: bool = False
    ) -> AsyncGenerator[bytes, None]:
        """Stream file content in chunks."""
        if decrypt:
            # Must read full content for decryption
            data = await self.get(file_path, decrypt=True)
            for i in range(0, len(data), CHUNK_SIZE):
                yield data[i : i + CHUNK_SIZE]
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
