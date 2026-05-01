"""Health alert model — proactive AI-driven health notifications."""
import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import ForeignKey, String, Text, DateTime, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class AlertType(str, enum.Enum):
    """Health alert type."""
    LAB_CRITICAL = "lab_critical"
    LAB_WARNING = "lab_warning"
    TREND_DECLINING = "trend_declining"
    TREND_IMPROVING = "trend_improving"
    PREVENTIVE_DUE = "preventive_due"


class AlertSeverity(str, enum.Enum):
    """Alert severity level."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class HealthAlert(Base):
    """Proactive health alert generated from anomaly detection or trend analysis."""

    __tablename__ = "health_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    household_id: Mapped[str] = mapped_column(String(36), ForeignKey("households.id"), nullable=False)
    family_member_id: Mapped[str] = mapped_column(String(36), ForeignKey("family_members.id"), nullable=False)
    record_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("health_records.id"), nullable=True)
    alert_type: Mapped[AlertType] = mapped_column(String(20), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    test_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    value: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    member: Mapped["FamilyMember"] = relationship(backref="health_alerts")  # noqa: F821

    __table_args__ = (
        Index("ix_health_alerts_household_dismissed", "household_id", "is_dismissed"),
        Index("ix_health_alerts_member_dismissed", "family_member_id", "is_dismissed"),
    )
