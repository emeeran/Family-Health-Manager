"""Attachment service."""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks, UploadFile

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

logger = logging.getLogger(__name__)


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

    async def delete_attachment(
        self,
        attachment_id: UUID,
        household_id: UUID,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        """Delete an attachment with reference-counted, post-commit file deletion.

        The blob is content-addressed and may be dedup-shared with another
        attachment OR a member's profile photo, so references are counted across
        both before the file is removed. Physical deletion is deferred to
        ``background_tasks`` when supplied: a BackgroundTask runs only after the
        response is sent, which (under the yield-based get_db dependency) is
        after the commit — so a rollback can't orphan the file (row restored →
        bytes gone). Callers without a response cycle (e.g. unit tests) pass
        ``background_tasks=None`` for synchronous deletion.
        """
        attachment = await self.get_attachment(attachment_id, household_id)
        content_hash = attachment.content_hash
        file_path = Path(attachment.file_path)
        thumb_path = Path(attachment.thumbnail_path) if attachment.thumbnail_path else None

        await self.db.delete(attachment)
        await self.db.flush()

        to_delete: list[Path] = []
        if content_hash:
            # Reference-counted across attachments AND member profile photos —
            # a member photo can share the same hash, so the old attachment-only
            # count could orphan a member's photo blob.
            if await self._blob_is_referenced(content_hash):
                return
            to_delete.append(file_path)
            if thumb_path:
                to_delete.append(thumb_path)
        else:
            to_delete.append(file_path)  # legacy file without hash — always delete

        for path in to_delete:
            if background_tasks is not None:
                background_tasks.add_task(delete_file, path)
            else:
                await delete_file(path)

    async def _blob_is_referenced(self, content_hash: str) -> bool:
        """True if any attachment or member profile photo still references *content_hash*."""
        from app.models.base import FamilyMember

        attachments_count = (
            await self.db.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.content_hash == content_hash)
            )
        ).scalar()
        members_count = (
            await self.db.execute(
                select(func.count())
                .select_from(FamilyMember)
                .where(FamilyMember.photo_content_hash == content_hash)
            )
        ).scalar()
        return (attachments_count or 0) + (members_count or 0) > 0

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

    async def attach_staged_files(
        self,
        record_id: UUID,
        items: list[tuple[str, str | None]],
        background_tasks: "BackgroundTasks | None" = None,
    ) -> list[Attachment]:
        """Batch-attach multiple staged files to a record.

        File finalization (hash/encrypt/relocate/stat) is session-free, so it is
        run concurrently with asyncio.gather; the Attachment rows are then added
        and flushed in a SINGLE call. This replaces an N×(finalize+flush) loop
        while keeping all session use serial (AsyncSession is not concurrency-safe).

        ``items`` is a list of ``(staging_file_id, original_file_name)``.
        Missing staging files are skipped (logged); any other error is re-raised
        so the caller's transaction rolls back. Returns the created attachments.
        """
        import mimetypes

        staging_root = get_staging_dir().resolve()

        # 1. Validate every staging path serially before doing any file I/O.
        #    Missing files are skipped (matches the prior per-file loop, which
        #    caught ValueError and continued); a path-traversal attempt is a
        #    genuine error and aborts the batch.
        validated: list[tuple[str, str | None, Path]] = []
        for staging_file_id, original_file_name in items:
            staging_file_id = (staging_file_id or "").strip()
            if not staging_file_id:
                continue
            staging_path = (staging_root / staging_file_id).resolve()
            if not staging_path.is_relative_to(staging_root):
                raise ValueError("Invalid staging file ID")
            if not staging_path.exists():
                logger.warning("Staging file %s not found, skipping", staging_file_id)
                continue
            validated.append((staging_file_id, original_file_name, staging_path))

        if not validated:
            return []

        # 2. Concurrent, session-free finalization. return_exceptions keeps a
        #    single failure from cancelling its siblings.
        async def _finalize(staging_file_id: str, staging_path: Path):
            ext = Path(staging_file_id).suffix or ".bin"
            meta = _read_staging_meta(staging_file_id)
            if meta and meta.get("content_hash"):
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
                mime_type = mimetypes.guess_type(staging_file_id)[0] or "application/octet-stream"
                dest_path, content_hash = await _store_plaintext_file(staging_path, ext, mime_type)
                staging_path.unlink(missing_ok=True)
            return dest_path, content_hash, mime_type, dest_path.stat().st_size

        results = await asyncio.gather(
            *[_finalize(sid, sp) for sid, _on, sp in validated],
            return_exceptions=True,
        )

        # 3. Build + add Attachment rows serially; flush once.
        built: list[tuple[Attachment, Path, str, str]] = []
        for (staging_file_id, original_file_name, _sp), res in zip(validated, results):
            if isinstance(res, BaseException):
                # Missing files are non-fatal (skip + continue); anything else
                # aborts the save so get_db rolls back.
                if isinstance(res, ValueError) and "not found" in str(res):
                    logger.warning("Staging file %s not found, skipping", staging_file_id)
                    continue
                raise res
            dest_path, content_hash, mime_type, file_size = res
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
            built.append((attachment, dest_path, content_hash, mime_type))

        if built:
            await self.db.flush()

        # 4. Register thumbnail BackgroundTasks serially (ids populated by flush).
        if background_tasks is not None and isinstance(background_tasks, BackgroundTasks):
            from app.core.thumbnails import generate_thumbnail_background

            for attachment, dest_path, content_hash, mime_type in built:
                background_tasks.add_task(
                    generate_thumbnail_background,
                    self.db,
                    attachment.id,
                    dest_path,
                    content_hash,
                    mime_type,
                    True,
                )

        return [a for a, _dp, _ch, _mt in built]
