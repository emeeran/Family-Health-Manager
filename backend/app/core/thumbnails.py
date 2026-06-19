"""Thumbnail generation for attachments."""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_thumbnails_dir

logger = logging.getLogger(__name__)

THUMBNAIL_WIDTH = 300
THUMBNAIL_FORMAT = "WEBP"


def _make_image_thumbnail_sync(source_path: Path, dest_path: Path) -> Path:
    """Blocking core: render an image thumbnail with Pillow."""
    from PIL import Image

    img = Image.open(source_path)
    img.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH))
    img.save(dest_path, THUMBNAIL_FORMAT, quality=80)
    return dest_path


async def generate_image_thumbnail(source_path: Path, dest_path: Path) -> Path:
    """Generate a thumbnail for an image file using Pillow.

    The blocking PIL work runs in a worker thread so it does not freeze the
    event loop (this runs in a FastAPI BackgroundTask).
    """
    return await asyncio.to_thread(_make_image_thumbnail_sync, source_path, dest_path)


def _make_pdf_thumbnail_sync(source_path: Path, dest_path: Path) -> Path:
    """Blocking core: render a PDF first-page thumbnail with PyMuPDF + Pillow."""
    import fitz  # PyMuPDF

    doc = fitz.open(str(source_path))
    if len(doc) == 0:
        doc.close()
        raise ValueError("PDF has no pages")

    page = doc[0]
    # Render at 72 DPI
    mat = fitz.Matrix(1.0, 1.0)
    pix = page.get_pixmap(matrix=mat)

    from PIL import Image
    import io

    img = Image.open(io.BytesIO(pix.tobytes("png")))
    img.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH))
    img.save(dest_path, THUMBNAIL_FORMAT, quality=80)

    doc.close()
    return dest_path


async def generate_pdf_thumbnail(source_path: Path, dest_path: Path) -> Path:
    """Generate a thumbnail from the first page of a PDF using PyMuPDF.

    The blocking PyMuPDF/PIL work runs in a worker thread so it does not
    freeze the event loop (this runs in a FastAPI BackgroundTask).
    """
    return await asyncio.to_thread(_make_pdf_thumbnail_sync, source_path, dest_path)


async def generate_thumbnail(
    file_path: Path, content_hash: str, mime_type: str, encrypted: bool = False
) -> Path | None:
    """Generate and store a thumbnail for the given file.

    Returns the thumbnail path, or None if generation is not supported.
    When *encrypted* is True the file is decrypted to a temp path first.
    """
    thumb_dir = get_thumbnails_dir()
    thumb_dir.mkdir(parents=True, exist_ok=True)
    dest_path = thumb_dir / f"{content_hash}.webp"

    if dest_path.exists():
        return dest_path

    if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
        return None

    try:
        from app.core.storage import plaintext_path

        async with plaintext_path(file_path, encrypted) as plain:
            if mime_type.startswith("image/"):
                await generate_image_thumbnail(plain, dest_path)
            else:
                await generate_pdf_thumbnail(plain, dest_path)

        logger.info("Generated thumbnail for %s at %s", content_hash[:12], dest_path)
        return dest_path
    except Exception:
        logger.warning("Failed to generate thumbnail for %s", file_path, exc_info=True)
        return None


async def generate_thumbnail_background(
    db: AsyncSession,
    attachment_id: UUID,
    file_path: Path,
    content_hash: str,
    mime_type: str,
    encrypted: bool = False,
) -> None:
    """Generate a thumbnail in a background task and persist the path to the DB.

    Performance optimization: designed to be used with FastAPI BackgroundTasks
    so that thumbnail generation does not block the HTTP response. The attachment
    is saved with thumbnail_path=None initially; this function updates it once
    the thumbnail is ready.

    If a client requests the thumbnail before it is generated, the existing
    GET /{attachment_id}/thumbnail endpoint returns 404, which the frontend
    can interpret as "pending" and retry.

    Errors are logged but never propagated — thumbnails are non-critical.
    """
    try:
        thumb_path = await generate_thumbnail(file_path, content_hash, mime_type, encrypted)
        if thumb_path is None:
            return

        # Update the attachment row with the generated thumbnail path
        from app.models.attachment import Attachment

        await db.execute(
            update(Attachment)
            .where(Attachment.id == attachment_id)
            .values(thumbnail_path=str(thumb_path))
        )
        await db.commit()
        logger.info("Background thumbnail saved for attachment %s", attachment_id)
    except Exception:
        # Gracefully handle all errors — thumbnail generation is non-critical
        logger.warning(
            "Background thumbnail generation failed for attachment %s",
            attachment_id,
            exc_info=True,
        )
