"""Backup and restore schemas."""
from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from app.models.base import (
    ConversationScope,
    Gender,
    MessageRole,
    RecordType,
    Relationship,
    ReminderType,
    ScheduleType,
)


# --- Per-entity backup models (serialized from ORM) ---


class MemberBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Gender
    relationship_type: Relationship
    medical_history_summary: str | None = None
    is_active: bool = True
    created_at: datetime


class ProviderBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    speciality: str | None = None
    phone: str | None = None
    address: str | None = None
    created_at: datetime


class ProviderAssignmentBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    provider_id: UUID
    family_member_id: UUID
    uhid: str | None = None
    created_at: datetime


class HealthRecordBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    family_member_id: UUID
    provider_id: UUID | None = None
    record_type: RecordType
    record_date: date
    record_time: time | None = None
    clinical_data: str
    diagnosis: str | None = None
    prescription_text: str | None = None
    next_review_date: date | None = None
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime


class AttachmentBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    health_record_id: UUID
    file_name: str
    mime_type: str
    file_size: int
    uploaded_at: datetime
    file_name_in_zip: str  # path inside the ZIP, e.g. "files/<uuid>.pdf"


class AIInsightBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    health_record_id: UUID | None = None
    conversation_id: UUID | None = None
    prompt: str
    response: str
    provider_used: str
    generated_at: datetime


class ConversationBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    family_member_id: UUID | None = None
    scope: ConversationScope
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    created_at: datetime


class ReminderBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    family_member_id: UUID | None = None
    reminder_type: ReminderType
    title: str
    description: str | None = None
    schedule_type: ScheduleType
    schedule_interval: int | None = None
    start_datetime: datetime
    end_datetime: datetime | None = None
    is_active: bool = True
    created_at: datetime


class NotificationBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    reminder_id: UUID
    title: str
    message: str
    is_read: bool = False
    created_at: datetime
    read_at: datetime | None = None


# --- Archive structure ---


class BackupCounts(BaseModel):
    members: int = 0
    providers: int = 0
    provider_assignments: int = 0
    health_records: int = 0
    attachments: int = 0
    ai_insights: int = 0
    conversations: int = 0
    messages: int = 0
    reminders: int = 0
    notifications: int = 0


class BackupManifest(BaseModel):
    version: str = "1.0"
    app_version: str
    created_at: datetime
    household_name: str
    household_id: UUID
    counts: BackupCounts


class BackupData(BaseModel):
    members: list[MemberBackup] = []
    providers: list[ProviderBackup] = []
    provider_assignments: list[ProviderAssignmentBackup] = []
    health_records: list[HealthRecordBackup] = []
    attachments: list[AttachmentBackup] = []
    ai_insights: list[AIInsightBackup] = []
    conversations: list[ConversationBackup] = []
    messages: list[MessageBackup] = []
    reminders: list[ReminderBackup] = []
    notifications: list[NotificationBackup] = []


# --- API request/response ---


class BackupValidationResponse(BaseModel):
    validation_id: str
    valid: bool
    manifest: BackupManifest | None = None
    warnings: list[str] = []
    errors: list[str] = []


class BackupImportRequest(BaseModel):
    validation_id: str
    mode: Literal["merge", "replace"]


class BackupImportResponse(BaseModel):
    imported: BackupCounts
    skipped: BackupCounts
    failed: int = 0
    errors: list[str] = []
