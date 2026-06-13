"""One-time migration script for existing attachment files.

Migrates flat files to content-addressed paths, computes hashes,
generates thumbnails, and optionally encrypts files.

Performance optimizations (#23):
- Batch processing with asyncio.gather and semaphore (max 5 concurrent)
- Streaming hash computation (read file in chunks for hashing)
- Progress logging every 10 files
- Per-file error handling (one failure does not stop the migration)
"""
import asyncio
import hashlib
import logging
import shutil
from pathlib import Path
from typing import Any

import aiofiles

from app.core.database import SessionLocal
from app.core.storage import _content_hash_to_path

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MB chunks for streaming I/O
_MAX_CONCURRENT_MIGRATIONS = 5  # Semaphore limit for concurrent file processing
_PROGRESS_LOG_INTERVAL = 10  # Log progress every N files


async def _compute_streaming_hash(file_path: Path) -> str:
    """Compute SHA-256 hash by reading the file in chunks.

    Performance: avoids loading the entire file into memory by streaming
    through fixed-size chunks, keeping peak memory usage at CHUNK_SIZE.
    """
    hasher = hashlib.sha256()
    async with aiofiles.open(file_path, "rb") as f:
        while True:
            chunk = await f.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


async def _migrate_single_attachment(
    att: Any,
    encrypt: bool,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Migrate a single attachment file.

    Performance: runs under a semaphore to bound concurrency.
    Per-file error handling ensures one failure does not stop the batch.

    Returns:
        A stats dict with incremental counts for this single attachment.
    """
    stats: dict[str, int] = {
        "migrated": 0,
        "deduped": 0,
        "thumbnailed": 0,
        "encrypted": 0,
        "errors": 0,
    }

    async with semaphore:
        try:
            file_path = Path(att.file_path)
            if not file_path.exists():
                logger.warning("File missing for attachment %s: %s", att.id, file_path)
                return stats

            # Streaming hash computation — reads in chunks to keep memory flat
            content_hash = await _compute_streaming_hash(file_path)

            # Determine extension
            ext = Path(att.file_name).suffix or Path(file_path).suffix or ".bin"

            # Check if already on content-addressed path
            expected_path = _content_hash_to_path(content_hash, ext)
            if file_path.resolve() == expected_path.resolve():
                # Already migrated
                att.content_hash = content_hash
                att.storage_backend = "local"
                return stats

            if expected_path.exists():
                # Dedup — remove the source file since content already exists
                file_path.unlink()
                stats["deduped"] += 1
            else:
                shutil.move(str(file_path), str(expected_path))

            att.file_path = str(expected_path)
            att.content_hash = content_hash
            att.storage_backend = "local"
            stats["migrated"] += 1

            # Generate thumbnail
            try:
                from app.core.thumbnails import generate_thumbnail

                thumb = await generate_thumbnail(
                    expected_path, content_hash, att.mime_type
                )
                if thumb:
                    att.thumbnail_path = str(thumb)
                    stats["thumbnailed"] += 1
            except Exception:
                pass

            # Encrypt if requested
            if encrypt:
                from app.core.encryption import encrypt_file

                await encrypt_file(expected_path)
                att.encrypted = True
                stats["encrypted"] += 1

        except Exception:
            stats["errors"] += 1
            logger.exception("Failed to migrate attachment %s", att.id)

    return stats


async def migrate_all(encrypt: bool = False) -> dict:
    """Run all migration steps on existing attachments.

    Performance: processes files concurrently using asyncio.gather with a
    semaphore to cap at _MAX_CONCURRENT_MIGRATIONS. Progress is logged every
    _PROGRESS_LOG_INTERVAL files. Each file is processed independently so a
    single failure does not abort the entire migration.

    Args:
        encrypt: Whether to encrypt files after migrating.

    Returns:
        Summary dict with counts of migrated, deduped, thumbnailed, encrypted files.
    """
    from sqlalchemy import select
    from app.models.base import Attachment

    total_stats: dict[str, int] = {
        "migrated": 0,
        "deduped": 0,
        "thumbnailed": 0,
        "encrypted": 0,
        "errors": 0,
    }

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_MIGRATIONS)

    async with SessionLocal() as db:
        result = await db.execute(select(Attachment))
        attachments = list(result.scalars().all())
        total = len(attachments)

        logger.info("Migration: starting batch processing of %d files", total)

        # Process files concurrently in batches, logging progress periodically
        processed = 0
        for batch_start in range(0, total, _MAX_CONCURRENT_MIGRATIONS):
            batch = attachments[batch_start : batch_start + _MAX_CONCURRENT_MIGRATIONS]

            # Run the batch concurrently via asyncio.gather
            batch_results = await asyncio.gather(
                *[_migrate_single_attachment(att, encrypt, semaphore) for att in batch]
            )

            # Aggregate stats from the batch
            for single_stats in batch_results:
                for key in total_stats:
                    total_stats[key] += single_stats.get(key, 0)

            # Flush after each batch so the DB stays in sync
            await db.flush()

            processed += len(batch)
            if processed % _PROGRESS_LOG_INTERVAL < _MAX_CONCURRENT_MIGRATIONS:
                logger.info(
                    "Migration: %d/%d files processed", processed, total
                )

        await db.commit()

    logger.info("Migration complete: %s", total_stats)
    return total_stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(migrate_all(encrypt=False))
    print(f"Migration result: {result}")
