"""Provider and provider assignment models."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import String, Text, DateTime
from app.models.base import Base


@dataclass
class Provider(Base):
    """Healthcare provider directory entry."""

    __tablename__ = "providers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    speciality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    household: Mapped["Household"] = relationship(back_populates="providers")
    assignments: Mapped[list["ProviderAssignment"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
    health_records: Mapped[list["HealthRecord"]] = relationship(back_populates="provider")


@dataclass
class ProviderAssignment(Base):
    """Provider-to-member assignment with UHID."""

    __tablename__ = "provider_assignments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(ForeignKey("providers.id"), nullable=False)
    family_member_id: Mapped[UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False)
    uhid: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    provider: Mapped["Provider"] = relationship(back_populates="assignments")
    family_member: Mapped["FamilyMember"] = relationship(back_populates="provider_assignments")
