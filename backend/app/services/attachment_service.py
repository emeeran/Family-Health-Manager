"""Attachment service."""
import shutil
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile

from app.models.base import Attachment, HealthRecord
from app.core.storage import (
    stream_file,
    delete_file,
    get_staging_dir,
    save_file_hashed,
    hash_existing_file,
    _content_hash_to_path,
)


class AttachmentService:
    """Attachment management service."""

    ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
    MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def upload_attachment(
        self, record_id: UUID, file: UploadFile, household_id: UUID
    ) -> Attachment:
        """Upload and validate attachment using content-addressable storage."""
        from app.models.base import FamilyMember

        # Validate MIME type
        mime = file.content_type or "application/octet-stream"
        if mime not in self.ALLOWED_MIME_TYPES:
            raise ValueError(
                f"File type {mime} not allowed. Allowed: {', '.join(sorted(self.ALLOWED_MIME_TYPES))}"
            )

        result = await self.db.execute(
            select(HealthRecord)
            .join(FamilyMember, HealthRecord.family_member_id == FamilyMember.id)
            .where(HealthRecord.id == record_id, FamilyMember.household_id == household_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            raise ValueError("Health record not found")

        # Use content-addressable hashed storage
        file_path, content_hash, _ext = await save_file_hashed(file)

        # Generate thumbnail
        thumbnail_path = None
        try:
            from app.core.thumbnails import generate_thumbnail
            thumbnail_path = await generate_thumbnail(file_path, content_hash, mime)
        except Exception:
            pass  # Non-fatal — thumbnails are optional

        attachment = Attachment(
            health_record_id=record_id,
            file_path=str(file_path),
            file_name=file.filename or "upload",
            mime_type=mime,
            file_size=file_path.stat().st_size,
            content_hash=content_hash,
            storage_backend="local",
            thumbnail_path=str(thumbnail_path) if thumbnail_path else None,
            encrypted=False,
        )
        self.db.add(attachment)
        await self.db.flush()
        return attachment

    async def get_attachment(self, attachment_id: UUID, household_id: UUID) -> Attachment:
        """Get attachment metadata, verifying household ownership."""
        from app.models.base import FamilyMember

        result = await self.db.execute(
            select(Attachment)
            .join(HealthRecord, Attachment.health_record_id == HealthRecord.id)
            .join(FamilyMember, HealthRecord.family_member_id == FamilyMember.id)
            .where(
                Attachment.id == attachment_id,
                FamilyMember.household_id == household_id,
            )
        )
        attachment = result.scalar_one_or_none()
        if not attachment:
            raise ValueError("Attachment not found")
        return attachment

    async def download_attachment(
        self, attachment_id: UUID, household_id: UUID
    ):
        """Download attachment — returns async generator for streaming."""
        attachment = await self.get_attachment(attachment_id, household_id)
        file_path = Path(attachment.file_path)

        # Decrypt if needed
        if attachment.encrypted:
            from app.core.encryption import decrypt_file
            content = await decrypt_file(file_path)
            async def _decrypted_stream(content: bytes):
                chunk_size = 1024 * 1024
                for i in range(0, len(content), chunk_size):
                    yield content[i:i + chunk_size]
            return _decrypted_stream(content), attachment.mime_type, attachment.file_name

        return stream_file(file_path), attachment.mime_type, attachment.file_name

    async def delete_attachment(self, attachment_id: UUID, household_id: UUID) -> None:
        """Delete an attachment with reference-counted file deletion."""
        attachment = await self.get_attachment(attachment_id, household_id)
        content_hash = attachment.content_hash

        await self.db.delete(attachment)
        await self.db.flush()

        # Reference-counted: only delete physical file if no other references
        if content_hash:
            remaining = await self.db.execute(
                select(func.count()).select_from(Attachment).where(
                    Attachment.content_hash == content_hash
                )
            )
            if remaining.scalar() == 0:
                await delete_file(Path(attachment.file_path))
                # Also delete thumbnail if present
                if attachment.thumbnail_path:
                    thumb_path = Path(attachment.thumbnail_path)
                    if thumb_path.exists():
                        await delete_file(thumb_path)
        else:
            # Legacy files without hash — always delete
            await delete_file(Path(attachment.file_path))

    async def attach_staged_file(
        self, record_id: UUID, staging_file_id: str, original_file_name: str | None = None
    ) -> Attachment:
        """Move a staged file to content-addressable storage and link to a health record."""
        staging_root = get_staging_dir().resolve()
        staging_path = (staging_root / staging_file_id).resolve()
        if not staging_path.is_relative_to(staging_root):
            raise ValueError("Invalid staging file ID")

        if not staging_path.exists():
            raise ValueError(f"Staging file not found: {staging_file_id}")

        # Hash the staged file and move to content-addressed path
        content_hash = await hash_existing_file(staging_path)

        import mimetypes
        mime_type = mimetypes.guess_type(staging_file_id)[0] or "application/octet-stream"
        ext = Path(staging_file_id).suffix or ".bin"

        dest_path = _content_hash_to_path(content_hash, ext)

        if dest_path.exists():
            # Dedup — remove staging file, use existing
            staging_path.unlink()
        else:
            shutil.move(str(staging_path), str(dest_path))

        file_size = dest_path.stat().st_size

        # Generate thumbnail
        thumbnail_path = None
        try:
            from app.core.thumbnails import generate_thumbnail
            thumbnail_path = await generate_thumbnail(dest_path, content_hash, mime_type)
        except Exception:
            pass  # Non-fatal — thumbnails are optional

        attachment = Attachment(
            health_record_id=record_id,
            file_path=str(dest_path),
            file_name=original_file_name or staging_file_id,
            mime_type=mime_type,
            file_size=file_size,
            content_hash=content_hash,
            storage_backend="local",
            thumbnail_path=str(thumbnail_path) if thumbnail_path else None,
            encrypted=False,
        )
        self.db.add(attachment)
        await self.db.flush()
        return attachment
