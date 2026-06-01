"""Thumbnail generation for attachments."""
import logging
from pathlib import Path


from app.core.storage import get_thumbnails_dir

logger = logging.getLogger(__name__)

THUMBNAIL_WIDTH = 300
THUMBNAIL_FORMAT = "WEBP"


async def generate_image_thumbnail(source_path: Path, dest_path: Path) -> Path:
    """Generate a thumbnail for an image file using Pillow."""
    from PIL import Image

    img = Image.open(source_path)
    img.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH))
    img.save(dest_path, THUMBNAIL_FORMAT, quality=80)
    return dest_path


async def generate_pdf_thumbnail(source_path: Path, dest_path: Path) -> Path:
    """Generate a thumbnail from the first page of a PDF using PyMuPDF."""
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


async def generate_thumbnail(
    file_path: Path, content_hash: str, mime_type: str
) -> Path | None:
    """Generate and store a thumbnail for the given file.

    Returns the thumbnail path, or None if generation is not supported.
    """
    thumb_dir = get_thumbnails_dir()
    thumb_dir.mkdir(parents=True, exist_ok=True)
    dest_path = thumb_dir / f"{content_hash}.webp"

    if dest_path.exists():
        return dest_path

    try:
        if mime_type.startswith("image/"):
            await generate_image_thumbnail(file_path, dest_path)
        elif mime_type == "application/pdf":
            await generate_pdf_thumbnail(file_path, dest_path)
        else:
            return None

        logger.info("Generated thumbnail for %s at %s", content_hash[:12], dest_path)
        return dest_path
    except Exception:
        logger.warning(
            "Failed to generate thumbnail for %s", file_path, exc_info=True
        )
        return None
