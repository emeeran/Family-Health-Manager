"""Backup and restore service."""
import io
import json
import logging
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.base import (
    AIInsight,
    Attachment,
    Conversation,
    FamilyMember,
    HealthRecord,
    Household,
    Message,
    Notification,
    Provider,
    ProviderAssignment,
    Reminder,
)
from app.schemas.backup import (
    AIInsightBackup,
    AttachmentBackup,
    BackupCounts,
    BackupData,
    BackupImportResponse,
    BackupManifest,
    BackupValidationResponse,
    ConversationBackup,
    HealthRecordBackup,
    MemberBackup,
    MessageBackup,
    NotificationBackup,
    ProviderAssignmentBackup,
    ProviderBackup,
    ReminderBackup,
)

settings = get_settings()
logger = logging.getLogger(__name__)

BACKUP_VERSION = "1.0"
SUPPORTED_VERSIONS = {"1.0"}
SAFE_FILENAME_RE = re.compile(r"^files/[0-9a-f\-]{36}\.\w{1,10}$")


class BackupService:
    """Handles export, validation, and import of household data archives."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Export ──────────────────────────────────────────────────────

    async def export_backup(self, household_id: UUID) -> bytes:
        """Build a ZIP archive containing all household data + attachments."""
        household = await self._get_household(household_id)

        # Load all entities
        members = await self._load_members(household_id)
        member_ids = {m.id for m in members}

        providers = await self._load_providers(household_id)
        provider_ids = {p.id for p in providers}

        assignments = await self._load_assignments(member_ids, provider_ids)
        records = await self._load_records(member_ids)
        record_ids = {r.id for r in records}

        attachments = await self._load_attachments(record_ids)
        insights = await self._load_insights(record_ids)

        conversations = await self._load_conversations(household_id)
        conv_ids = {c.id for c in conversations}

        messages = await self._load_messages(conv_ids)
        reminders = await self._load_reminders(household_id)
        reminder_ids = {r.id for r in reminders}

        notifications = await self._load_notifications(reminder_ids)

        # Build attachment entries with zip path mapping
        attachment_backups = []
        for att in attachments:
            ext = Path(att.file_path).suffix or Path(att.file_name).suffix or ""
            zip_path = f"files/{att.id}{ext}"
            attachment_backups.append(
                AttachmentBackup(
                    id=att.id,
                    health_record_id=att.health_record_id,
                    file_name=att.file_name,
                    mime_type=att.mime_type,
                    file_size=att.file_size,
                    uploaded_at=att.uploaded_at,
                    file_name_in_zip=zip_path,
                )
            )

        data = BackupData(
            members=[MemberBackup.model_validate(m) for m in members],
            providers=[ProviderBackup.model_validate(p) for p in providers],
            provider_assignments=[ProviderAssignmentBackup.model_validate(a) for a in assignments],
            health_records=[HealthRecordBackup.model_validate(r) for r in records],
            attachments=attachment_backups,
            ai_insights=[AIInsightBackup.model_validate(i) for i in insights],
            conversations=[ConversationBackup.model_validate(c) for c in conversations],
            messages=[MessageBackup.model_validate(m) for m in messages],
            reminders=[ReminderBackup.model_validate(r) for r in reminders],
            notifications=[NotificationBackup.model_validate(n) for n in notifications],
        )

        counts = BackupCounts(
            members=len(members),
            providers=len(providers),
            provider_assignments=len(assignments),
            health_records=len(records),
            attachments=len(attachments),
            ai_insights=len(insights),
            conversations=len(conversations),
            messages=len(messages),
            reminders=len(reminders),
            notifications=len(notifications),
        )

        manifest = BackupManifest(
            version=BACKUP_VERSION,
            app_version=settings.APP_VERSION,
            created_at=datetime.now(timezone.utc),
            household_name=household.name,
            household_id=household.id,
            counts=counts,
        )

        # Build ZIP in memory
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", manifest.model_dump_json(indent=2))
            zf.writestr("data.json", data.model_dump_json(indent=2))

            # Add attachment files
            for att, att_backup in zip(attachments, attachment_backups):
                file_path = Path(att.file_path)
                if file_path.exists():
                    zf.write(file_path, att_backup.file_name_in_zip)
                else:
                    logger.warning("Attachment file missing on disk: %s", file_path)

        buf.seek(0)
        logger.info("Backup exported for household %s: %s", household_id, counts)
        return buf.read()

    # ── Validate ───────────────────────────────────────────────────

    def validate_backup(self, file_path: Path) -> BackupValidationResponse:
        """Validate a backup archive and stage it for import."""
        validation_id = str(uuid4())
        warnings: list[str] = []
        errors: list[str] = []

        if not zipfile.is_zipfile(file_path):
            return BackupValidationResponse(
                validation_id=validation_id, valid=False,
                errors=["Not a valid ZIP archive"],
            )

        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()

            if "manifest.json" not in names:
                errors.append("Missing manifest.json")
            if "data.json" not in names:
                errors.append("Missing data.json")

            if errors:
                return BackupValidationResponse(
                    validation_id=validation_id, valid=False, errors=errors,
                )

            # Parse manifest
            manifest_data = json.loads(zf.read("manifest.json"))
            manifest = BackupManifest.model_validate(manifest_data)

            if manifest.version not in SUPPORTED_VERSIONS:
                errors.append(f"Unsupported backup version: {manifest.version}")

            # Parse data
            data_raw = json.loads(zf.read("data.json"))
            try:
                data = BackupData.model_validate(data_raw)
            except Exception as exc:
                errors.append(f"Invalid data.json: {exc}")
                return BackupValidationResponse(
                    validation_id=validation_id, valid=False,
                    manifest=manifest, errors=errors,
                )

            # Check attachment files exist in ZIP
            for att in data.attachments:
                if att.file_name_in_zip not in names:
                    warnings.append(f"Missing file in archive: {att.file_name_in_zip}")

        if errors:
            return BackupValidationResponse(
                validation_id=validation_id, valid=False,
                manifest=manifest, warnings=warnings, errors=errors,
            )

        # Stage the file for import
        staging_dir = Path(settings.STORAGE_PATH) / "backup-staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        staged_path = staging_dir / validation_id
        file_path.rename(staged_path)

        return BackupValidationResponse(
            validation_id=validation_id, valid=True,
            manifest=manifest, warnings=warnings,
        )

    # ── Import ─────────────────────────────────────────────────────

    async def import_backup(
        self,
        household_id: UUID,
        staging_id: str,
        mode: str,
    ) -> BackupImportResponse:
        """Import a validated backup archive into the household."""
        staged_path = Path(settings.STORAGE_PATH) / "backup-staging" / staging_id
        if not staged_path.exists():
            raise ValueError("Staged backup file not found. Please re-validate.")

        imported = BackupCounts()
        skipped = BackupCounts()
        errors: list[str] = []
        id_maps: dict[str, dict[UUID, UUID]] = {}

        try:
            with zipfile.ZipFile(staged_path, "r") as zf:
                data = BackupData.model_validate(json.loads(zf.read("data.json")))

                if mode == "replace":
                    await self._delete_household_data(household_id)

                # Import in dependency order
                await self._import_members(household_id, data.members, mode, id_maps, imported, skipped, errors)
                await self._import_providers(household_id, data.providers, mode, id_maps, imported, skipped, errors)
                await self._import_assignments(data.provider_assignments, mode, id_maps, imported, skipped, errors)
                await self._import_records(data.health_records, mode, id_maps, imported, skipped, errors)
                await self._import_attachments(data.attachments, mode, id_maps, zf, imported, skipped, errors)
                await self._import_insights(data.ai_insights, mode, id_maps, imported, skipped, errors)
                await self._import_conversations(household_id, data.conversations, mode, id_maps, imported, skipped, errors)
                await self._import_messages(data.messages, mode, id_maps, imported, skipped, errors)
                await self._import_reminders(household_id, data.reminders, mode, id_maps, imported, skipped, errors)
                await self._import_notifications(data.notifications, mode, id_maps, imported, skipped, errors)

                await self.db.flush()

        except Exception as exc:
            await self.db.rollback()
            errors.append(f"Import failed: {exc}")
            logger.error("Backup import failed: %s", exc)
        finally:
            # Clean up staged file
            if staged_path.exists():
                staged_path.unlink()

        logger.info("Backup import complete for household %s: imported=%s, skipped=%s, errors=%d",
                     household_id, imported, len(errors))
        return BackupImportResponse(
            imported=imported,
            skipped=skipped,
            failed=len(errors),
            errors=errors,
        )

    # ── Delete household data (for replace mode) ──────────────────

    async def _delete_household_data(self, household_id: UUID) -> None:
        """Delete all household data in reverse dependency order."""
        # Get member IDs for record-scoped deletions
        member_result = await self.db.execute(
            select(FamilyMember.id).where(FamilyMember.household_id == household_id)
        )
        member_ids = [row[0] for row in member_result.all()]

        if member_ids:
            # Get record IDs for attachment/insight deletions
            record_result = await self.db.execute(
                select(HealthRecord.id).where(HealthRecord.family_member_id.in_(member_ids))
            )
            record_ids = [row[0] for row in record_result.all()]

            if record_ids:
                # Delete attachment files from disk
                att_result = await self.db.execute(
                    select(Attachment.file_path).where(Attachment.health_record_id.in_(record_ids))
                )
                for (fp,) in att_result.all():
                    p = Path(fp)
                    if p.exists():
                        p.unlink(missing_ok=True)

                await self.db.execute(delete(AIInsight).where(AIInsight.health_record_id.in_(record_ids)))
                await self.db.execute(delete(Attachment).where(Attachment.health_record_id.in_(record_ids)))
                await self.db.execute(delete(HealthRecord).where(HealthRecord.family_member_id.in_(member_ids)))

            # Get conversation IDs
            conv_result = await self.db.execute(
                select(Conversation.id).where(Conversation.household_id == household_id)
            )
            conv_ids = [row[0] for row in conv_result.all()]
            if conv_ids:
                await self.db.execute(delete(AIInsight).where(AIInsight.conversation_id.in_(conv_ids)))
                await self.db.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
                await self.db.execute(delete(Conversation).where(Conversation.household_id == household_id))

            await self.db.execute(delete(ProviderAssignment).where(ProviderAssignment.family_member_id.in_(member_ids)))
            await self.db.execute(delete(FamilyMember).where(FamilyMember.household_id == household_id))

        # Reminder-scoped
        reminder_result = await self.db.execute(
            select(Reminder.id).where(Reminder.household_id == household_id)
        )
        reminder_ids = [row[0] for row in reminder_result.all()]
        if reminder_ids:
            await self.db.execute(delete(Notification).where(Notification.reminder_id.in_(reminder_ids)))
        await self.db.execute(delete(Reminder).where(Reminder.household_id == household_id))

        await self.db.execute(delete(Provider).where(Provider.household_id == household_id))
        await self.db.flush()

    # ── Per-entity import helpers ─────────────────────────────────

    def _new_id(self, mode: str, old_id: UUID, entity_type: str, id_maps: dict) -> UUID:
        """Get the ID to use for import: original (replace) or new (merge)."""
        if mode == "replace":
            return old_id
        if entity_type not in id_maps:
            id_maps[entity_type] = {}
        if old_id not in id_maps[entity_type]:
            id_maps[entity_type][old_id] = uuid4()
        return id_maps[entity_type][old_id]

    def _map_id(self, entity_type: str, old_id: UUID, id_maps: dict) -> UUID:
        """Look up a remapped ID (merge mode). Returns original in replace mode."""
        mapping = id_maps.get(entity_type, {})
        return mapping.get(old_id, old_id)

    async def _import_members(self, household_id, items, mode, id_maps, imported, skipped, errors):
        # Batch lookup for merge mode to avoid N+1 queries
        existing_member_ids: set = set()
        if mode == "merge" and items:
            member_ids = [m.id for m in items]
            result = await self.db.execute(
                select(FamilyMember.id).where(FamilyMember.id.in_(member_ids))
            )
            existing_member_ids = {row[0] for row in result.all()}

        for m in items:
            try:
                if mode == "merge":
                    if m.id in existing_member_ids:
                        skipped.members += 1
                        id_maps.setdefault("members", {})[m.id] = m.id
                        continue
                new_id = self._new_id(mode, m.id, "members", id_maps)
                self.db.add(FamilyMember(
                    id=new_id, household_id=household_id,
                    first_name=m.first_name, last_name=m.last_name,
                    date_of_birth=m.date_of_birth, gender=m.gender,
                    relationship_type=m.relationship_type,
                    medical_history_summary=m.medical_history_summary,
                    is_active=m.is_active, created_at=m.created_at,
                ))
                imported.members += 1
            except Exception as exc:
                errors.append(f"Member {m.first_name} {m.last_name}: {exc}")

    async def _import_providers(self, household_id, items, mode, id_maps, imported, skipped, errors):
        # Batch lookup for merge mode to avoid N+1 queries
        existing_provider_ids: set = set()
        if mode == "merge" and items:
            provider_ids = [p.id for p in items]
            result = await self.db.execute(
                select(Provider.id).where(Provider.id.in_(provider_ids))
            )
            existing_provider_ids = {row[0] for row in result.all()}

        for p in items:
            try:
                if mode == "merge":
                    if p.id in existing_provider_ids:
                        skipped.providers += 1
                        id_maps.setdefault("providers", {})[p.id] = p.id
                        continue
                new_id = self._new_id(mode, p.id, "providers", id_maps)
                self.db.add(Provider(
                    id=new_id, household_id=household_id,
                    name=p.name, speciality=p.speciality,
                    phone=p.phone, address=p.address, created_at=p.created_at,
                ))
                imported.providers += 1
            except Exception as exc:
                errors.append(f"Provider {p.name}: {exc}")

    async def _import_assignments(self, items, mode, id_maps, imported, skipped, errors):
        # Batch lookup for merge mode to avoid N+1 queries
        existing_ids: set = set()
        if mode == "merge" and items:
            all_ids = [a.id for a in items]
            result = await self.db.execute(
                select(ProviderAssignment.id).where(ProviderAssignment.id.in_(all_ids))
            )
            existing_ids = set(result.scalars().all())

        for a in items:
            try:
                member_id = self._map_id("members", a.family_member_id, id_maps)
                provider_id = self._map_id("providers", a.provider_id, id_maps)
                if mode == "merge":
                    if a.id in existing_ids:
                        skipped.provider_assignments += 1
                        id_maps.setdefault("assignments", {})[a.id] = a.id
                        continue
                new_id = self._new_id(mode, a.id, "assignments", id_maps)
                self.db.add(ProviderAssignment(
                    id=new_id, provider_id=provider_id,
                    family_member_id=member_id, uhid=a.uhid, created_at=a.created_at,
                ))
                imported.provider_assignments += 1
            except Exception as exc:
                errors.append(f"ProviderAssignment {a.id}: {exc}")

    async def _import_records(self, items, mode, id_maps, imported, skipped, errors):
        # Batch lookup for merge mode to avoid N+1 queries
        existing_ids: set = set()
        if mode == "merge" and items:
            all_ids = [r.id for r in items]
            result = await self.db.execute(
                select(HealthRecord.id).where(HealthRecord.id.in_(all_ids))
            )
            existing_ids = set(result.scalars().all())

        for r in items:
            try:
                member_id = self._map_id("members", r.family_member_id, id_maps)
                provider_id = self._map_id("providers", r.provider_id, id_maps) if r.provider_id else None
                if mode == "merge":
                    if r.id in existing_ids:
                        skipped.health_records += 1
                        id_maps.setdefault("records", {})[r.id] = r.id
                        continue
                new_id = self._new_id(mode, r.id, "records", id_maps)
                self.db.add(HealthRecord(
                    id=new_id, family_member_id=member_id, provider_id=provider_id,
                    record_type=r.record_type, record_date=r.record_date,
                    record_time=r.record_time, clinical_data=r.clinical_data,
                    diagnosis=r.diagnosis, prescription_text=r.prescription_text,
                    next_review_date=r.next_review_date, is_deleted=r.is_deleted,
                    created_at=r.created_at, updated_at=r.updated_at,
                ))
                imported.health_records += 1
            except Exception as exc:
                errors.append(f"HealthRecord {r.id}: {exc}")

    async def _import_attachments(self, items, mode, id_maps, zf, imported, skipped, errors):
        storage_path = Path(settings.STORAGE_PATH)
        storage_path.mkdir(parents=True, exist_ok=True)

        # Batch lookup for merge mode to avoid N+1 queries
        existing_ids: set = set()
        if mode == "merge" and items:
            all_ids = [a.id for a in items]
            result = await self.db.execute(
                select(Attachment.id).where(Attachment.id.in_(all_ids))
            )
            existing_ids = set(result.scalars().all())

        for a in items:
            try:
                record_id = self._map_id("records", a.health_record_id, id_maps)
                if mode == "merge":
                    if a.id in existing_ids:
                        skipped.attachments += 1
                        id_maps.setdefault("attachments", {})[a.id] = a.id
                        continue
                new_id = self._new_id(mode, a.id, "attachments", id_maps)
                ext = Path(a.file_name_in_zip).suffix
                if not ext or not SAFE_FILENAME_RE.match(a.file_name_in_zip):
                    errors.append(f"Attachment {a.file_name}: invalid path '{a.file_name_in_zip}'")
                    continue
                new_filename = f"{new_id}{ext}"
                new_path = storage_path / new_filename

                # Extract file from ZIP
                if a.file_name_in_zip in zf.namelist():
                    with zf.open(a.file_name_in_zip) as src, open(new_path, "wb") as dst:
                        dst.write(src.read())

                self.db.add(Attachment(
                    id=new_id, health_record_id=record_id,
                    file_path=str(new_path), file_name=a.file_name,
                    mime_type=a.mime_type, file_size=a.file_size,
                    uploaded_at=a.uploaded_at,
                ))
                imported.attachments += 1
            except Exception as exc:
                errors.append(f"Attachment {a.file_name}: {exc}")

    async def _import_insights(self, items, mode, id_maps, imported, skipped, errors):
        # Batch lookup for merge mode to avoid N+1 queries
        existing_ids: set = set()
        if mode == "merge" and items:
            all_ids = [i.id for i in items]
            result = await self.db.execute(
                select(AIInsight.id).where(AIInsight.id.in_(all_ids))
            )
            existing_ids = set(result.scalars().all())

        for i in items:
            try:
                record_id = self._map_id("records", i.health_record_id, id_maps) if i.health_record_id else None
                conv_id = self._map_id("conversations", i.conversation_id, id_maps) if i.conversation_id else None
                if mode == "merge":
                    if i.id in existing_ids:
                        skipped.ai_insights += 1
                        continue
                new_id = self._new_id(mode, i.id, "insights", id_maps)
                self.db.add(AIInsight(
                    id=new_id, health_record_id=record_id,
                    conversation_id=conv_id, prompt=i.prompt,
                    response=i.response, provider_used=i.provider_used,
                    generated_at=i.generated_at,
                ))
                imported.ai_insights += 1
            except Exception as exc:
                errors.append(f"AIInsight {i.id}: {exc}")

    async def _import_conversations(self, household_id, items, mode, id_maps, imported, skipped, errors):
        # Batch lookup for merge mode to avoid N+1 queries
        existing_ids: set = set()
        if mode == "merge" and items:
            all_ids = [c.id for c in items]
            result = await self.db.execute(
                select(Conversation.id).where(Conversation.id.in_(all_ids))
            )
            existing_ids = set(result.scalars().all())

        for c in items:
            try:
                member_id = self._map_id("members", c.family_member_id, id_maps) if c.family_member_id else None
                if mode == "merge":
                    if c.id in existing_ids:
                        skipped.conversations += 1
                        id_maps.setdefault("conversations", {})[c.id] = c.id
                        continue
                new_id = self._new_id(mode, c.id, "conversations", id_maps)
                self.db.add(Conversation(
                    id=new_id, household_id=household_id,
                    family_member_id=member_id, scope=c.scope,
                    title=c.title, created_at=c.created_at, updated_at=c.updated_at,
                ))
                imported.conversations += 1
            except Exception as exc:
                errors.append(f"Conversation {c.id}: {exc}")

    async def _import_messages(self, items, mode, id_maps, imported, skipped, errors):
        # Batch lookup for merge mode to avoid N+1 queries
        existing_ids: set = set()
        if mode == "merge" and items:
            all_ids = [m.id for m in items]
            result = await self.db.execute(
                select(Message.id).where(Message.id.in_(all_ids))
            )
            existing_ids = set(result.scalars().all())

        for m in items:
            try:
                conv_id = self._map_id("conversations", m.conversation_id, id_maps)
                if mode == "merge":
                    if m.id in existing_ids:
                        skipped.messages += 1
                        continue
                new_id = self._new_id(mode, m.id, "messages", id_maps)
                self.db.add(Message(
                    id=new_id, conversation_id=conv_id,
                    role=m.role, content=m.content, created_at=m.created_at,
                ))
                imported.messages += 1
            except Exception as exc:
                errors.append(f"Message {m.id}: {exc}")

    async def _import_reminders(self, household_id, items, mode, id_maps, imported, skipped, errors):
        # Batch lookup for merge mode to avoid N+1 queries
        existing_ids: set = set()
        if mode == "merge" and items:
            all_ids = [r.id for r in items]
            result = await self.db.execute(
                select(Reminder.id).where(Reminder.id.in_(all_ids))
            )
            existing_ids = set(result.scalars().all())

        for r in items:
            try:
                member_id = self._map_id("members", r.family_member_id, id_maps) if r.family_member_id else None
                if mode == "merge":
                    if r.id in existing_ids:
                        skipped.reminders += 1
                        id_maps.setdefault("reminders", {})[r.id] = r.id
                        continue
                new_id = self._new_id(mode, r.id, "reminders", id_maps)
                self.db.add(Reminder(
                    id=new_id, household_id=household_id,
                    family_member_id=member_id, reminder_type=r.reminder_type,
                    title=r.title, description=r.description,
                    schedule_type=r.schedule_type, schedule_interval=r.schedule_interval,
                    start_datetime=r.start_datetime, end_datetime=r.end_datetime,
                    is_active=r.is_active, created_at=r.created_at,
                ))
                imported.reminders += 1
            except Exception as exc:
                errors.append(f"Reminder {r.title}: {exc}")

    async def _import_notifications(self, items, mode, id_maps, imported, skipped, errors):
        # Batch lookup for merge mode to avoid N+1 queries
        existing_ids: set = set()
        if mode == "merge" and items:
            all_ids = [n.id for n in items]
            result = await self.db.execute(
                select(Notification.id).where(Notification.id.in_(all_ids))
            )
            existing_ids = set(result.scalars().all())

        for n in items:
            try:
                reminder_id = self._map_id("reminders", n.reminder_id, id_maps)
                if mode == "merge":
                    if n.id in existing_ids:
                        skipped.notifications += 1
                        continue
                new_id = self._new_id(mode, n.id, "notifications", id_maps)
                # Need household_id for notification
                # Get it from the reminder's household
                self.db.add(Notification(
                    id=new_id, reminder_id=reminder_id,
                    household_id=(await self._get_reminder_household(reminder_id)),
                    title=n.title, message=n.message,
                    is_read=n.is_read, created_at=n.created_at, read_at=n.read_at,
                ))
                imported.notifications += 1
            except Exception as exc:
                errors.append(f"Notification {n.id}: {exc}")

    async def _get_reminder_household(self, reminder_id: UUID) -> UUID:
        result = await self.db.execute(select(Reminder.household_id).where(Reminder.id == reminder_id))
        row = result.first()
        if row:
            return row[0]
        # Fallback: shouldn't happen but return a dummy that will fail FK
        return reminder_id

    # ── Data loading helpers ──────────────────────────────────────

    async def _get_household(self, household_id: UUID) -> Household:
        result = await self.db.execute(select(Household).where(Household.id == household_id))
        household = result.scalar_one_or_none()
        if not household:
            raise ValueError("Household not found")
        return household

    async def _load_members(self, household_id: UUID) -> list[FamilyMember]:
        result = await self.db.execute(
            select(FamilyMember).where(FamilyMember.household_id == household_id)
        )
        return list(result.scalars().all())

    async def _load_providers(self, household_id: UUID) -> list[Provider]:
        result = await self.db.execute(
            select(Provider).where(Provider.household_id == household_id)
        )
        return list(result.scalars().all())

    async def _load_assignments(self, member_ids: set, provider_ids: set) -> list[ProviderAssignment]:
        if not member_ids:
            return []
        result = await self.db.execute(
            select(ProviderAssignment).where(ProviderAssignment.family_member_id.in_(member_ids))
        )
        return list(result.scalars().all())

    async def _load_records(self, member_ids: set) -> list[HealthRecord]:
        if not member_ids:
            return []
        result = await self.db.execute(
            select(HealthRecord).where(HealthRecord.family_member_id.in_(member_ids))
        )
        return list(result.scalars().all())

    async def _load_attachments(self, record_ids: set) -> list[Attachment]:
        if not record_ids:
            return []
        result = await self.db.execute(
            select(Attachment).where(Attachment.health_record_id.in_(record_ids))
        )
        return list(result.scalars().all())

    async def _load_insights(self, record_ids: set) -> list[AIInsight]:
        if not record_ids:
            return []
        result = await self.db.execute(
            select(AIInsight).where(AIInsight.health_record_id.in_(record_ids))
        )
        return list(result.scalars().all())

    async def _load_conversations(self, household_id: UUID) -> list[Conversation]:
        result = await self.db.execute(
            select(Conversation).where(Conversation.household_id == household_id)
        )
        return list(result.scalars().all())

    async def _load_messages(self, conv_ids: set) -> list[Message]:
        if not conv_ids:
            return []
        result = await self.db.execute(
            select(Message).where(Message.conversation_id.in_(conv_ids))
        )
        return list(result.scalars().all())

    async def _load_reminders(self, household_id: UUID) -> list[Reminder]:
        result = await self.db.execute(
            select(Reminder).where(Reminder.household_id == household_id)
        )
        return list(result.scalars().all())

    async def _load_notifications(self, reminder_ids: set) -> list[Notification]:
        if not reminder_ids:
            return []
        result = await self.db.execute(
            select(Notification).where(Notification.reminder_id.in_(reminder_ids))
        )
        return list(result.scalars().all())
