"""SQLAlchemy models — Base class, enums, and re-exports.

Model classes are defined in domain-specific files under app/models/.
They are re-exported here for backward compatibility with existing imports:
    from app.models.base import User, Household, ...
"""
import enum
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


# ── Enums ──────────────────────────────────────────────────────────


class Gender(str, enum.Enum):
    """Gender identity options."""

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class Relationship(str, enum.Enum):
    """Relationship to household primary."""

    SELF = "self"
    WIFE = "wife"
    SON = "son"
    DAUGHTER = "daughter"
    GRAND_SON = "grand_son"
    GRAND_DAUGHTER = "grand_daughter"
    DAUGHTER_IN_LAW = "daughter_in_law"
    SON_IN_LAW = "son_in_law"
    OTHERS = "others"


class RecordType(str, enum.Enum):
    """Health record types."""

    DOCTOR_VISIT = "doctor_visit"
    LAB_REPORT = "lab_report"
    RX_EYEGLASS = "rx_eyeglass"
    BLOOD_GLUCOSE = "blood_glucose"
    HBA1C = "hba1c"
    MISC_RECORD = "misc_record"
    VITALS = "vitals"
    PARKINSONS_LOG = "parkinsons_log"


class ReminderType(str, enum.Enum):
    """Reminder types."""

    APPOINTMENT = "appointment"
    MEDICATION = "medication"
    FOLLOW_UP = "follow_up"
    CHECK_UP = "check_up"
    PRESCRIPTION_REFILL = "prescription_refill"


class ScheduleType(str, enum.Enum):
    """Reminder schedule types."""

    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    CUSTOM = "custom"


class MessageRole(str, enum.Enum):
    """Message role in conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationScope(str, enum.Enum):
    """Conversation scope type."""

    MEMBER = "member"
    GENERAL = "general"


# ── Re-export models for backward compatibility ────────────────────
# Models import Base + enums from this file, so we import them
# at the bottom to avoid circular dependencies.

from app.models.user import User  # noqa: E402
from app.models.household import Household  # noqa: E402
from app.models.refresh_token import RefreshToken  # noqa: E402
from app.models.member import FamilyMember  # noqa: E402
from app.models.provider import Provider, ProviderAssignment  # noqa: E402
from app.models.record import HealthRecord  # noqa: E402
from app.models.attachment import Attachment  # noqa: E402
from app.models.ai import AIInsight  # noqa: E402
from app.models.conversation import Conversation, Message  # noqa: E402
from app.models.reminder import Reminder, Notification  # noqa: E402
from app.models.vaccination import Vaccination  # noqa: E402
from app.models.verification import ResponseVerification  # noqa: E402
from app.models.health_alert import HealthAlert, AlertType, AlertSeverity  # noqa: E402

__all__ = [
    "Base",
    "Gender",
    "Relationship",
    "RecordType",
    "ReminderType",
    "ScheduleType",
    "MessageRole",
    "ConversationScope",
    "User",
    "Household",
    "RefreshToken",
    "FamilyMember",
    "Provider",
    "ProviderAssignment",
    "HealthRecord",
    "Attachment",
    "AIInsight",
    "Conversation",
    "Message",
    "Reminder",
    "Notification",
    "Vaccination",
    "ResponseVerification",
    "HealthAlert",
    "AlertType",
    "AlertSeverity",
]
