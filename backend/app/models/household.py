"""Household model."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import String, DateTime, Text
from app.models.base import Base


@dataclass
class Household(Base):
    """Household aggregate root."""

    __tablename__ = "households"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    primary_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    settings_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON object for feature toggles

    primary_user: Mapped["User"] = relationship(back_populates="households")
    members: Mapped[list["FamilyMember"]] = relationship(
        back_populates="household", cascade="all, delete-orphan"
    )
    providers: Mapped[list["Provider"]] = relationship(
        back_populates="household", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="household", cascade="all, delete-orphan"
    )
    reminders: Mapped[list["Reminder"]] = relationship(
        back_populates="household", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="household", cascade="all, delete-orphan"
    )
