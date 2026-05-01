"""File storage abstraction."""
import uuid
from pathlib import Path
from fastapi import UploadFile
import aiofiles
import aiofiles.os
from app.core.config import get_settings

settings = get_settings()

ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

# Magic-byte signatures for content-type verification
MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "application/pdf": [b"%PDF"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
}


def _validate_storage_path(file_path: Path) -> None:
    """Ensure the file path is within the configured storage root."""
    storage_root = Path(settings.STORAGE_PATH).resolve()
    resolved = file_path.resolve()
    if not str(resolved).startswith(str(storage_root)):
        raise ValueError("Invalid file path: escapes storage root")


def validate_file(file: UploadFile) -> None:
    """Validate file MIME type and size."""
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Invalid MIME type: {file.content_type}")

    file.file.seek(0, 2)  # Seek to end
    size = file.file.tell()
    file.file.seek(0)  # Reset to beginning

    if size > MAX_FILE_SIZE:
        raise ValueError(f"File size {size} exceeds maximum {MAX_FILE_SIZE}")


async def save_file(file: UploadFile, prefix: str = "attachments") -> tuple[Path, str]:
    """
    Save uploaded file and return path and filename.

    Returns: (file_path, unique_filename)
    """
    validate_file(file)

    storage_dir = Path(settings.STORAGE_PATH) / prefix
    storage_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "").suffix or ".bin"
    unique_filename = f"{uuid.uuid4()}{ext}"
    file_path = storage_dir / unique_filename

    _validate_storage_path(file_path)

    content = await file.read()

    # Verify actual file content matches declared MIME type via magic bytes
    declared_mime = file.content_type or "application/octet-stream"
    signatures = MAGIC_SIGNATURES.get(declared_mime)
    if signatures and not any(content.startswith(sig) for sig in signatures):
        raise ValueError(f"File content does not match declared type {declared_mime}")

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    return file_path, unique_filename


async def get_file(file_path: Path) -> bytes:
    """Read file content from storage."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    _validate_storage_path(file_path)
    async with aiofiles.open(file_path, "rb") as f:
        return await f.read()


async def delete_file(file_path: Path) -> None:
    """Delete file from storage."""
    if file_path.exists():
        _validate_storage_path(file_path)
        await aiofiles.os.remove(file_path)
