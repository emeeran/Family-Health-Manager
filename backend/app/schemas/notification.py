"""Notification schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID


class NotificationResponse(BaseModel):
    """Notification response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="Notification ID")
    reminder_id: UUID = Field(..., description="Reminder ID")
    household_id: UUID = Field(..., description="Household ID")
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification message")
    is_read: bool = Field(..., description="Read status")
    created_at: datetime = Field(..., description="Creation timestamp")
    read_at: datetime | None = Field(None, description="Read timestamp")
