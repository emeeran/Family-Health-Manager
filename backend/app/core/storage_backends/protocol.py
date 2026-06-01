"""Storage backend protocol definition."""
from pathlib import Path
from collections.abc import AsyncGenerator
from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol defining the interface for storage backends."""

    async def put(
        self, content_hash: str, ext: str, data: bytes, encrypt: bool = False
    ) -> Path:
        """Store data at a content-addressable path.

        Args:
            content_hash: SHA-256 hex digest of the content.
            ext: File extension including dot (e.g., '.pdf').
            data: Raw file bytes.
            encrypt: Whether to encrypt the data before storing.

        Returns:
            Path to the stored file.
        """
        ...

    async def get(self, file_path: Path, decrypt: bool = False) -> bytes:
        """Read file content from storage.

        Args:
            file_path: Path to the file.
            decrypt: Whether to decrypt the data after reading.

        Returns:
            Raw file bytes.
        """
        ...

    async def stream(self, file_path: Path, decrypt: bool = False) -> AsyncGenerator[bytes, None]:
        """Stream file content in chunks.

        Args:
            file_path: Path to the file.
            decrypt: Whether to decrypt the data after reading.

        Yields:
            Chunks of file content.
        """
        ...

    async def delete(self, file_path: Path) -> None:
        """Delete a file from storage."""
        ...

    async def exists(self, file_path: Path) -> bool:
        """Check if a file exists in storage."""
        ...
