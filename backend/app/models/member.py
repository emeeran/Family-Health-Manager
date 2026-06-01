"""Family member model."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import String, Text, DateTime, Boolean, Date, Enum, Float
from app.models.base import Base, Gender, Relationship


@dataclass
class FamilyMember(Base):
    """Family member profile."""

    __tablename__ = "family_members"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[Gender] = mapped_column(Enum(Gender), nullable=False)
    relationship_type: Mapped[Relationship] = mapped_column(Enum(Relationship), nullable=False)
    medical_history_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    blood_group: Mapped[str | None] = mapped_column(String(10), nullable=True)
    family_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    allergies_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    household: Mapped["Household"] = relationship(back_populates="members")
    health_records: Mapped[list["HealthRecord"]] = relationship(
        back_populates="family_member", cascade="all, delete-orphan"
    )
    provider_assignments: Mapped[list["ProviderAssignment"]] = relationship(
        back_populates="family_member", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="family_member")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="family_member")
    vaccinations: Mapped[list["Vaccination"]] = relationship(back_populates="family_member", cascade="all, delete-orphan")
    medications: Mapped[list["Medication"]] = relationship(back_populates="family_member", cascade="all, delete-orphan")
    lab_results: Mapped[list["LabResult"]] = relationship(back_populates="family_member", cascade="all, delete-orphan")
