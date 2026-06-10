"""Reminder and notification models."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import String, Text, Integer, DateTime, Boolean, Enum
from app.models.base import Base, ReminderType, ScheduleType


@dataclass
class Reminder(Base):
    """Health reminder for family member."""

    __tablename__ = "reminders"
    __table_args__ = (
        Index("ix_reminders_active_start", "is_active", "start_datetime"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), nullable=False, index=True)
    family_member_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("family_members.id"), nullable=True, index=True
    )
    reminder_type: Mapped[ReminderType] = mapped_column(Enum(ReminderType), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_type: Mapped[ScheduleType] = mapped_column(Enum(ScheduleType), nullable=False)
    schedule_interval: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_datetime: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    household: Mapped["Household"] = relationship(back_populates="reminders")
    family_member: Mapped["FamilyMember | None"] = relationship(back_populates="reminders")
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="reminder", cascade="all, delete-orphan"
    )


@dataclass
class Notification(Base):
    """In-app notification for reminder."""

    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    reminder_id: Mapped[UUID] = mapped_column(ForeignKey("reminders.id"), nullable=False, index=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    reminder: Mapped["Reminder"] = relationship(back_populates="notifications")
    household: Mapped["Household"] = relationship(back_populates="notifications")
