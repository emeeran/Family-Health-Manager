"""Attachment router."""
import aiofiles
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.services.attachment_service import AttachmentService
from app.schemas.attachment import AttachmentResponse
from app.models.base import Household

router = APIRouter(prefix="/attachments", tags=["Attachments"])


@router.post("/records/{record_id}", status_code=201, response_model=AttachmentResponse)
async def upload_attachment(
    record_id: UUID,
    file: UploadFile = File(...),
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Upload an attachment to a health record."""
    service = AttachmentService(db)

    try:
        attachment = await service.upload_attachment(record_id, file, household.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return attachment


@router.get("/{attachment_id}")
async def download_attachment(
    attachment_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Download an attachment as a streaming response."""
    service = AttachmentService(db)

    try:
        stream, mime_type, file_name = await service.download_attachment(
            attachment_id, household.id
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Attachment not found")

    return StreamingResponse(
        stream,
        media_type=mime_type,
        headers={"Content-Disposition": f'inline; filename="{file_name}"'},
    )


@router.get("/{attachment_id}/thumbnail")
async def get_thumbnail(
    attachment_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get a thumbnail for an attachment."""
    service = AttachmentService(db)

    try:
        attachment = await service.get_attachment(attachment_id, household.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if not attachment.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not available")

    thumb_path = Path(attachment.thumbnail_path)
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file not found")

    async def _stream_thumbnail():
        async with aiofiles.open(thumb_path, "rb") as f:
            while chunk := await f.read(1024 * 1024):
                yield chunk

    return StreamingResponse(
        _stream_thumbnail(),
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.delete("/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete an attachment."""
    service = AttachmentService(db)

    try:
        await service.delete_attachment(attachment_id, household.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Attachment not found")
