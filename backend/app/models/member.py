"""Family member model."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import String, DateTime, Boolean, Date, Enum, Float
from app.db_types import EncryptedText
from app.models.base import Base, Gender, Relationship


@dataclass
class FamilyMember(Base):
    """Family member profile."""

    __tablename__ = "family_members"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[Gender] = mapped_column(Enum(Gender), nullable=False)
    relationship_type: Mapped[Relationship] = mapped_column(Enum(Relationship), nullable=False)
    medical_history_summary: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    blood_group: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Demographics used to populate the patient-identification header of a
    # "Medical Records Transcription Report" (see prompts/transcription_report.md).
    patient_id: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    phone: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    address: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    family_history: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    allergies_json: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    notes: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    # Per-member cloud-AI consent. When False, AI work for this member is forced
    # local-only (Ollama) so their PHI never egresses to a cloud provider.
    # Defaults True (legacy behaviour); opt out for sensitive members.
    cloud_ai_consent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        server_default="CURRENT_TIMESTAMP",
        nullable=False,
    )

    # Optional profile photo. The full image is stored content-addressed and
    # encrypted at rest (core/storage.save_file_hashed); a 300px WebP thumbnail
    # (photo_thumbnail_path) is what the UI renders. photo_content_hash enables
    # dedup + reference-counted deletion; photo_updated_at busts the client
    # <img> cache when the photo changes.
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    photo_thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    household: Mapped["Household"] = relationship(back_populates="members")
    health_records: Mapped[list["HealthRecord"]] = relationship(
        back_populates="family_member", cascade="all, delete-orphan"
    )
    provider_assignments: Mapped[list["ProviderAssignment"]] = relationship(
        back_populates="family_member", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="family_member")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="family_member")
    vaccinations: Mapped[list["Vaccination"]] = relationship(
        back_populates="family_member", cascade="all, delete-orphan"
    )
    medications: Mapped[list["Medication"]] = relationship(
        back_populates="family_member", cascade="all, delete-orphan"
    )
    lab_results: Mapped[list["LabResult"]] = relationship(
        back_populates="family_member", cascade="all, delete-orphan"
    )
