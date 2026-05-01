"""Schemas module initialization."""
from app.schemas.common import PaginatedResponse, PaginationInfo, ErrorResponse
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.schemas.household import HouseholdCreate, HouseholdUpdate, HouseholdResponse
from app.schemas.family_member import (
    MedicalHistoryQuestionnaire,
    FamilyMemberCreate,
    FamilyMemberUpdate,
    FamilyMemberResponse,
)
from app.schemas.provider import ProviderCreate, ProviderUpdate, ProviderResponse
from app.schemas.provider_assignment import ProviderAssignmentCreate, ProviderAssignmentResponse
from app.schemas.health_record import (
    HealthRecordCreate,
    HealthRecordUpdate,
    HealthRecordResponse,
)
from app.schemas.attachment import AttachmentResponse
from app.schemas.ai_insight import AIInsightRequest, AIInsightResponse
from app.schemas.conversation import ConversationCreate, ConversationResponse
from app.schemas.message import MessageCreate, MessageResponse
from app.schemas.reminder import ReminderCreate, ReminderUpdate, ReminderResponse
from app.schemas.notification import NotificationResponse
from app.schemas.auth import LoginRequest, LoginResponse, UserResponse as AuthUserResponse

__all__ = [
    "PaginatedResponse",
    "PaginationInfo",
    "ErrorResponse",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "HouseholdCreate",
    "HouseholdUpdate",
    "HouseholdResponse",
    "MedicalHistoryQuestionnaire",
    "FamilyMemberCreate",
    "FamilyMemberUpdate",
    "FamilyMemberResponse",
    "ProviderCreate",
    "ProviderUpdate",
    "ProviderResponse",
    "ProviderAssignmentCreate",
    "ProviderAssignmentResponse",
    "HealthRecordCreate",
    "HealthRecordUpdate",
    "HealthRecordResponse",
    "AttachmentResponse",
    "AIInsightRequest",
    "AIInsightResponse",
    "ConversationCreate",
    "ConversationResponse",
    "MessageCreate",
    "MessageResponse",
    "ReminderCreate",
    "ReminderUpdate",
    "ReminderResponse",
    "NotificationResponse",
    "LoginRequest",
    "LoginResponse",
    "AuthUserResponse",
]
