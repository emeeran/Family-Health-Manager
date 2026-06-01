"""One-time migration script for existing attachment files.

Migrates flat files to content-addressed paths, computes hashes,
generates thumbnails, and optionally encrypts files.
"""
import asyncio
import hashlib
import logging
import shutil
from pathlib import Path

import aiofiles

from app.core.database import SessionLocal
from app.core.storage import _content_hash_to_path

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024


async def migrate_all(encrypt: bool = False) -> dict:
    """Run all migration steps on existing attachments.

    Args:
        encrypt: Whether to encrypt files after migrating.

    Returns:
        Summary dict with counts of migrated, deduped, thumbnailed, encrypted files.
    """
    from sqlalchemy import select
    from app.models.base import Attachment

    stats = {"migrated": 0, "deduped": 0, "thumbnailed": 0, "encrypted": 0, "errors": 0}

    async with SessionLocal() as db:
        result = await db.execute(select(Attachment))
        attachments = list(result.scalars().all())

        for att in attachments:
            try:
                file_path = Path(att.file_path)
                if not file_path.exists():
                    logger.warning("File missing for attachment %s: %s", att.id, file_path)
                    continue

                # Compute hash
                hasher = hashlib.sha256()
                async with aiofiles.open(file_path, "rb") as f:
                    while True:
                        chunk = await f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        hasher.update(chunk)
                content_hash = hasher.hexdigest()

                # Determine extension
                ext = Path(att.file_name).suffix or Path(file_path).suffix or ".bin"

                # Check if already on content-addressed path
                expected_path = _content_hash_to_path(content_hash, ext)
                if file_path.resolve() == expected_path.resolve():
                    # Already migrated
                    att.content_hash = content_hash
                    att.storage_backend = "local"
                    await db.flush()
                    continue

                if expected_path.exists():
                    # Dedup
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

                await db.flush()

            except Exception:
                stats["errors"] += 1
                logger.exception("Failed to migrate attachment %s", att.id)

        await db.commit()

    logger.info("Migration complete: %s", stats)
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(migrate_all(encrypt=False))
    print(f"Migration result: {result}")
