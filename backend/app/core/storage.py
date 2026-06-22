"""File storage abstraction."""

import asyncio
import contextlib
import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from collections.abc import AsyncGenerator

import aiofiles
import aiofiles.os
from fastapi import UploadFile

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
CHUNK_SIZE = 1024 * 1024  # 1 MB

# Magic-byte signatures for content-type verification
MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "application/pdf": [b"%PDF"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    # WebP uses a RIFF container: "RIFF" at offset 0, "WEBP" at offset 8.
    "image/webp": [b"RIFF"],
}


def _magic_matches(chunk: bytes, mime: str) -> bool:
    """Return True if the first chunk matches the expected magic bytes for mime.

    WebP is a RIFF container, so its signature is split across two offsets
    ("RIFF" at 0, "WEBP" at 8) and cannot be verified by a single prefix.
    """
    if mime == "image/webp":
        return chunk[:4] == b"RIFF" and chunk[8:12] == b"WEBP"
    signatures = MAGIC_SIGNATURES.get(mime)
    if not signatures:
        return False
    return any(chunk.startswith(sig) for sig in signatures)


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


def _safe_unlink(path: Path) -> None:
    """Best-effort file deletion."""
    try:
        path.unlink()
    except OSError:
        pass


def optimize_pdf(src: Path) -> Path:
    """Downsample a PDF via ghostscript to shrink scanned-document size.

    Returns a path to the optimized PDF (a temp file beside *src*). On any
    failure — gs not installed, gs error, or no size reduction — returns *src*
    unchanged, so the app always works (just unoptimized) without gs.
    """
    if not settings.OPTIMIZE_PDFS:
        return src
    gs = shutil.which("gs")
    if not gs:
        logger.info("ghostscript not installed — storing PDF unoptimized")
        return src
    out = src.parent / f"{src.name}.opt.pdf"
    try:
        # Note: PDFSETTINGS needs the PostScript-name form (/ebook), not bare
        # "ebook" — the latter makes gs exit non-zero.
        pdf_settings = f"/{settings.PDF_OPTIMIZE_DPI.lstrip('/')}"
        result = subprocess.run(
            [
                gs,
                "-sDEVICE=pdfwrite",
                f"-dPDFSETTINGS={pdf_settings}",
                "-dNOPAUSE",
                "-dBATCH",
                f"-sOutputFile={out}",
                str(src),
            ],
            capture_output=True,
            timeout=120,
        )
    except Exception:
        logger.warning("PDF optimization error", exc_info=True)
        _safe_unlink(out)
        return src
    if result.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        logger.warning("ghostscript optimization failed: %s", result.stderr.decode()[:200])
        _safe_unlink(out)
        return src
    # Only accept the optimized copy if it actually shrank the file.
    if out.stat().st_size >= src.stat().st_size:
        _safe_unlink(out)
        return src
    return out


async def _store_plaintext_file(src_plaintext: Path, ext: str, mime: str) -> tuple[Path, str]:
    """Optimize (PDF) → hash plaintext → encrypt → write content-addressed.

    Returns ``(final_path, content_hash)``. *src_plaintext* is read but not
    deleted (the caller owns it). Dedup: if ``final_path`` already exists the
    existing encrypted file is reused. The stored file is Fernet-encrypted
    (chunked); ``content_hash`` is of the **plaintext** so dedup/integrity work.
    """
    from app.core.encryption import encrypt_file

    optimized = (
        await asyncio.to_thread(optimize_pdf, src_plaintext)
        if mime == "application/pdf"
        else src_plaintext
    )
    try:
        content_hash = await hash_existing_file(optimized)
        final_path = _content_hash_to_path(content_hash, ext)
        if not final_path.exists():
            await encrypt_file(optimized, final_path)
        return final_path, content_hash
    finally:
        if optimized is not src_plaintext:
            _safe_unlink(optimized)


@contextlib.asynccontextmanager
async def plaintext_path(file_path: Path, encrypted: bool):
    """Async context manager yielding a Path to PLAINTEXT file content.

    For libraries that need a real file path (fitz, Pillow, tesseract). When not
    encrypted, yields ``file_path`` directly; otherwise decrypts to a temp file
    and removes it on exit.
    """
    if not encrypted:
        yield file_path
        return
    from app.core.encryption import decrypt_file

    tmp = tempfile.NamedTemporaryFile(suffix=".plain", delete=False)  # noqa: SIM115
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        tmp_path.write_bytes(await decrypt_file(file_path))
        yield tmp_path
    finally:
        _safe_unlink(tmp_path)


async def stream_plaintext(file_path: Path, encrypted: bool) -> AsyncGenerator[bytes, None]:
    """Yield plaintext chunks — raw stream when unencrypted, else decrypted."""
    if not encrypted:
        async for chunk in stream_file(file_path):
            yield chunk
        return
    from app.core.encryption import decrypt_file_chunks

    async for chunk in decrypt_file_chunks(file_path):
        yield chunk


_clamav_unavailable_warned = False


def scan_file(file_path: Path) -> bool:
    """Scan file for viruses using ClamAV (if available).

    Returns True if the file is clean (or ClamAV is not installed).
    Returns False if a virus is detected.
    """
    global _clamav_unavailable_warned
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
        # clamd not installed (the common self-hosted case). Warn once so it's
        # visible that uploads are NOT being virus-scanned, without spamming.
        if not _clamav_unavailable_warned:
            logger.warning("ClamAV (clamd) not installed — uploads will not be virus-scanned")
            _clamav_unavailable_warned = True
        return True
    except Exception:
        logger.warning("ClamAV scan failed for %s — treating file as clean", file_path)
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


async def save_file_hashed(file: UploadFile) -> tuple[Path, str, str]:
    """Stream an upload to a temp file, then optimize + encrypt + store.

    Validates MIME/size/magic-bytes, virus-scans the plaintext, then runs the
    storage pipeline (PDF optimization → SHA-256 → Fernet encrypt → content-
    addressed path with dedup). Returns ``(file_path, content_hash, ext)``;
    the stored file is encrypted (set ``Attachment.encrypted = True``).
    """
    validate_file(file)

    ext = Path(file.filename or "").suffix or ".bin"
    files_dir = get_files_dir()
    files_dir.mkdir(parents=True, exist_ok=True)

    declared_mime = file.content_type or "application/octet-stream"
    magic_checked = False

    tmp_path = files_dir / f"_tmp_{uuid.uuid4()}{ext}"

    total_size = 0
    async with aiofiles.open(tmp_path, "wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            if not magic_checked:
                if not _magic_matches(chunk, declared_mime):
                    await aiofiles.os.remove(tmp_path)
                    raise ValueError(f"File content does not match declared type {declared_mime}")
                magic_checked = True
            await f.write(chunk)
            total_size += len(chunk)

    if total_size > MAX_FILE_SIZE:
        await aiofiles.os.remove(tmp_path)
        raise ValueError(f"File size {total_size} exceeds maximum {MAX_FILE_SIZE}")

    try:
        # Virus-scan the PLAINTEXT (before encryption) so ClamAV sees real content.
        if not scan_file(tmp_path):
            raise ValueError("File failed virus scan")
        final_path, content_hash = await _store_plaintext_file(tmp_path, ext, declared_mime)
    finally:
        _safe_unlink(tmp_path)

    return final_path, content_hash, ext


async def save_staged_secured(
    file: UploadFile, member_id: uuid.UUID | str | None = None
) -> tuple[Path, str, str]:
    """Stream an upload to encrypted-at-rest staging and return its content hash.

    Validates MIME/size/magic-bytes, virus-scans the plaintext, computes the
    SHA-256 of the plaintext (dedup + extraction-cache key), then Fernet-encrypts
    to ``staging/<id>``. A sidecar ``staging/<id>.meta`` JSON records
    ``{content_hash, ext, mime, original_name, member_id}`` so
    :func:`attach_staged_file` can relocate the already-encrypted file to
    content-addressable storage without re-hashing/re-encrypting, and
    :func:`app.routers.health_records.get_staging_file` can verify the staging
    id belongs to the requesting member (the staging id is an opaque uuid4
    handle, but tying it to the member closes the IDOR where a leaked id would
    stream another household's staged document).

    Returns ``(staged_path, unique_filename, content_hash)``. This closes the
    plaintext-staging window: previously a staged file sat as plaintext on disk
    until attach (or for 24h if the upload was abandoned).
    """
    from app.core.encryption import encrypt_file

    validate_file(file)

    staging_dir = get_staging_dir()
    staging_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "").suffix or ".bin"
    unique_filename = f"{uuid.uuid4()}{ext}"
    staged_path = staging_dir / unique_filename
    _validate_storage_path(staged_path)

    declared_mime = file.content_type or "application/octet-stream"

    # 1. Stream to a plaintext temp, validating magic + size, hashing inline.
    tmp_path = staging_dir / f"_tmp_{uuid.uuid4()}{ext}"
    hasher = hashlib.sha256()
    total_size = 0
    magic_checked = False
    try:
        async with aiofiles.open(tmp_path, "wb") as f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                if not magic_checked:
                    if not _magic_matches(chunk, declared_mime):
                        raise ValueError(
                            f"File content does not match declared type {declared_mime}"
                        )
                    magic_checked = True
                hasher.update(chunk)
                await f.write(chunk)
                total_size += len(chunk)

        if total_size > MAX_FILE_SIZE:
            raise ValueError(f"File size {total_size} exceeds maximum {MAX_FILE_SIZE}")

        # 2. Virus-scan the plaintext before encryption.
        if not scan_file(tmp_path):
            raise ValueError("File failed virus scan")

        content_hash = hasher.hexdigest()

        # 3. Encrypt the plaintext temp → encrypted-at-rest staging file.
        await encrypt_file(tmp_path, staged_path)
    finally:
        _safe_unlink(tmp_path)

    # 4. Sidecar metadata so the attach step can finalize without re-work.
    meta = {
        "content_hash": content_hash,
        "ext": ext,
        "mime": declared_mime,
        "original_name": file.filename,
        "member_id": str(member_id) if member_id else None,
    }
    try:
        async with aiofiles.open(f"{staged_path}.meta", "w") as mf:
            await mf.write(json.dumps(meta))
    except Exception as exc:  # pragma: no cover - best-effort metadata
        logger.warning("Failed to write staging sidecar for %s: %s", unique_filename, exc)

    return staged_path, unique_filename, content_hash


async def finalize_staged_to_content_addressed(
    staged_encrypted_path: Path, content_hash: str, ext: str
) -> tuple[Path, str]:
    """Relocate an already-encrypted staged file to content-addressable storage.

    Dedup-aware: if the destination already exists (same plaintext hash) the
    staged copy is dropped and the existing encrypted file reused. No
    re-encryption or re-hashing — the staged file is already Fernet-encrypted
    and its plaintext hash is known. Returns ``(final_path, content_hash)``.
    """
    final_path = _content_hash_to_path(content_hash, ext)
    if final_path.exists():
        await aiofiles.os.remove(staged_encrypted_path)  # duplicate — reuse existing
    else:
        await aiofiles.os.rename(staged_encrypted_path, final_path)
    return final_path, content_hash


def _read_staging_meta(staging_file_id: str) -> dict | None:
    """Read the staging sidecar metadata for a staged file, if present.

    Returns ``None`` for legacy plaintext-staged files (created before Phase 0,
    which have no sidecar) so the attach path can fall back to the old
    optimize+hash+encrypt flow.
    """
    meta_path = get_staging_dir() / f"{staging_file_id}.meta"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


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
