"""Storage backend package."""
from app.core.storage_backends.protocol import StorageBackend
from app.core.storage_backends.factory import get_storage_backend

__all__ = ["StorageBackend", "get_storage_backend"]
