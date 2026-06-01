"""File storage abstraction."""
import hashlib
import logging
import uuid
from pathlib import Path
from collections.abc import AsyncGenerator

import aiofiles
import aiofiles.os
from fastapi import UploadFile

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
CHUNK_SIZE = 1024 * 1024  # 1 MB

# Magic-byte signatures for content-type verification
MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "application/pdf": [b"%PDF"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
}


def get_files_dir() -> Path:
    """Return the canonical files directory: {STORAGE_PATH}/files/."""
    return Path(settings.STORAGE_PATH) / "files"


def get_staging_dir() -> Path:
    """Return the canonical staging directory: {STORAGE_PATH}/staging/."""
    return Path(settings.STORAGE_PATH) / "staging"


def get_thumbnails_dir() -> Path:
    """Return the canonical thumbnails directory: {STORAGE_PATH}/thumbnails/."""
    return Path(settings.STORAGE_PATH) / "thumbnails"


def _validate_storage_path(file_path: Path) -> None:
    """Ensure the file path is within the configured storage root."""
    storage_root = Path(settings.STORAGE_PATH).resolve()
    resolved = file_path.resolve()
    if not str(resolved).startswith(str(storage_root)):
        raise ValueError("Invalid file path: escapes storage root")


def _content_hash_to_path(content_hash: str, ext: str) -> Path:
    """Return sharded content-addressable path: files/ab/cdef0123...pdf."""
    shard = content_hash[:2]
    files_dir = get_files_dir() / shard
    files_dir.mkdir(parents=True, exist_ok=True)
    return files_dir / f"{content_hash}{ext}"


def scan_file(file_path: Path) -> bool:
    """Scan file for viruses using ClamAV (if available).

    Returns True if the file is clean (or ClamAV is not installed).
    Returns False if a virus is detected.
    """
    try:
        import clamd

        cd = clamd.ClamdUnixSocket()
        result = cd.scan(str(file_path))
        for _, (status, _) in result.items():
            if status == "FOUND":
                logger.warning("Virus detected in file: %s", file_path)
                return False
        return True
    except ImportError:
        return True
    except Exception:
        logger.debug("ClamAV scan skipped for %s", file_path)
        return True


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
    Save uploaded file using streaming I/O and return path and filename.

    Returns: (file_path, unique_filename)
    """
    validate_file(file)

    storage_dir = Path(settings.STORAGE_PATH) / prefix
    storage_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "").suffix or ".bin"
    unique_filename = f"{uuid.uuid4()}{ext}"
    file_path = storage_dir / unique_filename

    _validate_storage_path(file_path)

    declared_mime = file.content_type or "application/octet-stream"
    signatures = MAGIC_SIGNATURES.get(declared_mime)
    magic_checked = False

    async with aiofiles.open(file_path, "wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            # Validate magic bytes from first chunk
            if not magic_checked:
                if signatures and not any(chunk.startswith(sig) for sig in signatures):
                    await aiofiles.os.remove(file_path)
                    raise ValueError(
                        f"File content does not match declared type {declared_mime}"
                    )
                magic_checked = True
            await f.write(chunk)

    # Virus scan (no-op if ClamAV not installed)
    if not scan_file(file_path):
        await aiofiles.os.remove(file_path)
        raise ValueError("File failed virus scan")

    return file_path, unique_filename


async def save_file_hashed(file: UploadFile) -> tuple[Path, str, str]:
    """
    Stream-write uploaded file to a temp path while computing SHA-256.
    Move to content-addressable sharded path.
    Deduplicate if file with same hash already exists.

    Returns: (file_path, content_hash, ext)
    """
    validate_file(file)

    ext = Path(file.filename or "").suffix or ".bin"
    files_dir = get_files_dir()
    files_dir.mkdir(parents=True, exist_ok=True)

    declared_mime = file.content_type or "application/octet-stream"
    signatures = MAGIC_SIGNATURES.get(declared_mime)
    magic_checked = False

    # Stream to temp file while hashing
    hasher = hashlib.sha256()
    tmp_path = files_dir / f"_tmp_{uuid.uuid4()}{ext}"

    total_size = 0
    async with aiofiles.open(tmp_path, "wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            if not magic_checked:
                if signatures and not any(chunk.startswith(sig) for sig in signatures):
                    await aiofiles.os.remove(tmp_path)
                    raise ValueError(
                        f"File content does not match declared type {declared_mime}"
                    )
                magic_checked = True
            hasher.update(chunk)
            await f.write(chunk)
            total_size += len(chunk)

    if total_size > MAX_FILE_SIZE:
        await aiofiles.os.remove(tmp_path)
        raise ValueError(f"File size {total_size} exceeds maximum {MAX_FILE_SIZE}")

    content_hash = hasher.hexdigest()
    final_path = _content_hash_to_path(content_hash, ext)

    if final_path.exists():
        # Dedup: same content already stored
        await aiofiles.os.remove(tmp_path)
        logger.info("Deduplicated file with hash %s", content_hash[:12])
    else:
        # Move temp to final content-addressed path
        tmp_path.rename(final_path)

    # Virus scan
    if not scan_file(final_path):
        await aiofiles.os.remove(final_path)
        raise ValueError("File failed virus scan")

    return final_path, content_hash, ext


async def hash_existing_file(file_path: Path) -> str:
    """Compute SHA-256 of an existing file."""
    hasher = hashlib.sha256()
    async with aiofiles.open(file_path, "rb") as f:
        while True:
            chunk = await f.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


async def get_file(file_path: Path) -> bytes:
    """Read file content from storage."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    _validate_storage_path(file_path)
    async with aiofiles.open(file_path, "rb") as f:
        return await f.read()


async def stream_file(file_path: Path) -> AsyncGenerator[bytes, None]:
    """Stream file content in chunks for download."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    _validate_storage_path(file_path)
    async with aiofiles.open(file_path, "rb") as f:
        while True:
            chunk = await f.read(CHUNK_SIZE)
            if not chunk:
                break
            yield chunk


async def delete_file(file_path: Path) -> None:
    """Delete file from storage."""
    if file_path.exists():
        _validate_storage_path(file_path)
        await aiofiles.os.remove(file_path)


async def sweep_orphaned_staging() -> int:
    """Remove orphaned files from staging directory.

    Called during startup to clean up any files left from crashed sessions.
    """
    import time

    staging_dir = get_staging_dir()
    if not staging_dir.exists():
        return 0

    now = time.time()
    cutoff = now - 86400  # 24 hours
    removed = 0

    for entry in staging_dir.iterdir():
        if entry.is_file():
            try:
                if entry.stat().st_mtime < cutoff:
                    await aiofiles.os.remove(entry)
                    removed += 1
            except OSError:
                logger.warning("Failed to remove orphaned staging file: %s", entry)

    if removed:
        logger.info("Swept %d orphaned staging files", removed)
    return removed
