"""User model."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import String, DateTime, Boolean, Text
from app.models.base import Base


@dataclass
class User(Base):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    totp_secret: Mapped[str | None] = mapped_column(String(32), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    backup_codes: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)

    households: Mapped[list["Household"]] = relationship(back_populates="primary_user")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")
