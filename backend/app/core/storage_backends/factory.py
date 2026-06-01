"""Storage backend factory."""
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_backend_instance = None


def get_storage_backend():
    """Return the configured storage backend singleton."""
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance

    settings = get_settings()
    backend_name = settings.STORAGE_BACKEND.lower()

    if backend_name == "local":
        from app.core.storage_backends.local import LocalStorageBackend
        _backend_instance = LocalStorageBackend()
    else:
        raise ValueError(f"Unknown storage backend: {backend_name}")

    logger.info("Initialized storage backend: %s", backend_name)
    return _backend_instance
