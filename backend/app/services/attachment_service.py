"""Attachment service."""

from pathlib import Path
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile

from app.models.base import Attachment, HealthRecord
from app.core.storage import (
    ALLOWED_MIME_TYPES,
    stream_file,
    delete_file,
    get_staging_dir,
    save_file_hashed,
    _store_plaintext_file,
    finalize_staged_to_content_addressed,
    _read_staging_meta,
    _safe_unlink,
)


class AttachmentService:
    """Attachment management service."""

    MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def upload_attachment(
        self,
        record_id: UUID,
        file: UploadFile,
        household_id: UUID,
        background_tasks: "object | None" = None,
    ) -> Attachment:
        """Upload and validate attachment using content-addressable storage.

        Performance optimization: thumbnail generation is deferred to a
        FastAPI BackgroundTask so it does not block the HTTP response.
        The attachment is saved with thumbnail_path=None and updated
        asynchronously once the thumbnail is ready.
        """
        from app.models.base import FamilyMember

        # Validate MIME type
        mime = file.content_type or "application/octet-stream"
        if mime not in ALLOWED_MIME_TYPES:
            raise ValueError(
                f"File type {mime} not allowed. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
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

        # Performance: defer thumbnail generation to background task
        # instead of blocking the upload response. The attachment is
        # created with thumbnail_path=None and updated asynchronously.
        attachment = Attachment(
            health_record_id=record_id,
            file_path=str(file_path),
            file_name=file.filename or "upload",
            mime_type=mime,
            file_size=file_path.stat().st_size,
            content_hash=content_hash,
            storage_backend="local",
            thumbnail_path=None,
            encrypted=True,
        )
        self.db.add(attachment)
        await self.db.flush()

        if background_tasks is not None:
            from app.core.thumbnails import generate_thumbnail_background
            from fastapi import BackgroundTasks

            if isinstance(background_tasks, BackgroundTasks):
                background_tasks.add_task(
                    generate_thumbnail_background,
                    self.db,
                    attachment.id,
                    file_path,
                    content_hash,
                    mime,
                    True,
                )

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

    async def download_attachment(self, attachment_id: UUID, household_id: UUID):
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
                    yield content[i : i + chunk_size]

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
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.content_hash == content_hash)
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
        self,
        record_id: UUID,
        staging_file_id: str,
        original_file_name: str | None = None,
        background_tasks: "object | None" = None,
    ) -> Attachment:
        """Move a staged file to content-addressable storage and link to a health record.

        Performance optimization: thumbnail generation is deferred to a
        FastAPI BackgroundTask so it does not block the response.
        """
        staging_root = get_staging_dir().resolve()
        staging_path = (staging_root / staging_file_id).resolve()
        if not staging_path.is_relative_to(staging_root):
            raise ValueError("Invalid staging file ID")

        if not staging_path.exists():
            raise ValueError(f"Staging file not found: {staging_file_id}")

        import mimetypes

        ext = Path(staging_file_id).suffix or ".bin"

        meta = _read_staging_meta(staging_file_id)
        if meta and meta.get("content_hash"):
            # Phase 0: the staged file is already encrypted at rest — relocate
            # it to content-addressable storage (dedup-aware, no re-encrypt).
            mime_type = (
                meta.get("mime")
                or mimetypes.guess_type(staging_file_id)[0]
                or "application/octet-stream"
            )
            dest_path, content_hash = await finalize_staged_to_content_addressed(
                staging_path, meta["content_hash"], meta.get("ext") or ext
            )
            _safe_unlink(staging_root / f"{staging_file_id}.meta")
        else:
            # Legacy plaintext-staged file (pre-Phase-0 uploads still in
            # flight): optimize + hash + encrypt exactly as before.
            mime_type = mimetypes.guess_type(staging_file_id)[0] or "application/octet-stream"
            dest_path, content_hash = await _store_plaintext_file(staging_path, ext, mime_type)
            staging_path.unlink(missing_ok=True)

        file_size = dest_path.stat().st_size

        # Performance: defer thumbnail generation to background task
        # instead of blocking the response.
        attachment = Attachment(
            health_record_id=record_id,
            file_path=str(dest_path),
            file_name=original_file_name or staging_file_id,
            mime_type=mime_type,
            file_size=file_size,
            content_hash=content_hash,
            storage_backend="local",
            thumbnail_path=None,
            encrypted=True,
        )
        self.db.add(attachment)
        await self.db.flush()

        if background_tasks is not None:
            from app.core.thumbnails import generate_thumbnail_background
            from fastapi import BackgroundTasks

            if isinstance(background_tasks, BackgroundTasks):
                background_tasks.add_task(
                    generate_thumbnail_background,
                    self.db,
                    attachment.id,
                    dest_path,
                    content_hash,
                    mime_type,
                    True,
                )

        return attachment
