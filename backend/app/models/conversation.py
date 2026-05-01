"""Conversation and message models."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import String, Text, DateTime, Enum
from app.models.base import Base, MessageRole, ConversationScope


@dataclass
class Conversation(Base):
    """AI conversation session."""

    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), nullable=False, index=True)
    family_member_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("family_members.id"), nullable=True, index=True
    )
    scope: Mapped[ConversationScope] = mapped_column(
        Enum(ConversationScope), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    household: Mapped["Household"] = relationship(back_populates="conversations")
    family_member: Mapped["FamilyMember | None"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    ai_insights: Mapped[list["AIInsight"]] = relationship(back_populates="conversation", passive_deletes=True)


@dataclass
class Message(Base):
    """Message in a conversation."""

    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    verification: Mapped["ResponseVerification | None"] = relationship(  # noqa: F821
        back_populates="message", uselist=False
    )
