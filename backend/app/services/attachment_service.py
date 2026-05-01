"""Attachment service."""
import shutil
from pathlib import Path
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile
from app.models.base import Attachment, HealthRecord
from app.core.storage import get_file, delete_file
from app.core.config import get_settings


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
        """Upload and validate attachment."""
        from app.models.base import FamilyMember

        # Validate MIME type
        mime = file.content_type or "application/octet-stream"
        if mime not in self.ALLOWED_MIME_TYPES:
            raise ValueError(f"File type {mime} not allowed. Allowed: {', '.join(sorted(self.ALLOWED_MIME_TYPES))}")

        result = await self.db.execute(
            select(HealthRecord)
            .join(FamilyMember, HealthRecord.family_member_id == FamilyMember.id)
            .where(HealthRecord.id == record_id, FamilyMember.household_id == household_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            raise ValueError("Health record not found")

        settings = get_settings()
        originals_dir = Path(settings.STORAGE_PATH).parent.parent / "original medical records"
        originals_dir.mkdir(parents=True, exist_ok=True)

        import uuid as _uuid
        ext = Path(file.filename or "").suffix or ".bin"
        unique_name = f"{_uuid.uuid4()}{ext}"
        dest_path = originals_dir / unique_name

        content = await file.read()
        if len(content) > self.MAX_FILE_SIZE:
            raise ValueError(f"File exceeds {self.MAX_FILE_SIZE // (1024*1024)}MB limit")
        dest_path.write_bytes(content)

        attachment = Attachment(
            health_record_id=record_id,
            file_path=str(dest_path),
            file_name=file.filename or unique_name,
            mime_type=file.content_type or "application/octet-stream",
            file_size=len(content),
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

    async def download_attachment(self, attachment_id: UUID, household_id: UUID) -> tuple[bytes, str]:
        """Download attachment content with MIME type."""
        attachment = await self.get_attachment(attachment_id, household_id)
        content = await get_file(Path(attachment.file_path))
        return content, attachment.mime_type

    async def delete_attachment(self, attachment_id: UUID, household_id: UUID) -> None:
        """Delete an attachment."""
        attachment = await self.get_attachment(attachment_id, household_id)
        await delete_file(Path(attachment.file_path))
        await self.db.delete(attachment)
        await self.db.flush()

    async def attach_staged_file(
        self, record_id: UUID, staging_file_id: str, original_file_name: str | None = None
    ) -> Attachment:
        """Move a staged file to permanent storage and link it to a health record."""
        settings = get_settings()
        staging_root = (Path(settings.STORAGE_PATH) / "staging").resolve()
        staging_path = (staging_root / staging_file_id).resolve()
        if not staging_path.is_relative_to(staging_root):
            raise ValueError("Invalid staging file ID")

        if not staging_path.exists():
            raise ValueError(f"Staging file not found: {staging_file_id}")

        # Store originals in dedicated directory at project root
        originals_dir = Path(settings.STORAGE_PATH).parent.parent / "original medical records"
        originals_dir.mkdir(parents=True, exist_ok=True)
        dest_path = originals_dir / staging_file_id
        shutil.move(str(staging_path), str(dest_path))

        # Guess MIME type from extension
        import mimetypes
        mime_type = mimetypes.guess_type(staging_file_id)[0] or "application/octet-stream"
        file_size = dest_path.stat().st_size

        attachment = Attachment(
            health_record_id=record_id,
            file_path=str(dest_path),
            file_name=original_file_name or staging_file_id,
            mime_type=mime_type,
            file_size=file_size,
        )
        self.db.add(attachment)
        await self.db.flush()
        return attachment
