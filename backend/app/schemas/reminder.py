"""Reminder schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID
from app.models.base import ReminderType, ScheduleType


class ReminderCreate(BaseModel):
    """Reminder creation request."""

    family_member_id: UUID | None = Field(None, description="Family member ID")
    reminder_type: ReminderType = Field(..., description="Reminder type")
    title: str = Field(..., min_length=1, max_length=100, description="Reminder title")
    description: str | None = Field(None, description="Reminder description")
    schedule_type: ScheduleType = Field(..., description="Schedule type")
    schedule_interval: int | None = Field(
        None, ge=1, le=365, description="Interval for CUSTOM schedule"
    )
    start_datetime: datetime = Field(..., description="Start datetime")
    end_datetime: datetime | None = Field(None, description="End datetime")


class ReminderUpdate(BaseModel):
    """Reminder update request."""

    title: str | None = Field(None, min_length=1, max_length=100, description="Reminder title")
    description: str | None = Field(None, description="Reminder description")
    schedule_type: ScheduleType | None = Field(None, description="Schedule type")
    schedule_interval: int | None = Field(
        None, ge=1, le=365, description="Interval for CUSTOM schedule"
    )
    start_datetime: datetime | None = Field(None, description="Start datetime")
    end_datetime: datetime | None = Field(None, description="End datetime")
    is_active: bool | None = Field(None, description="Active status")


class ReminderResponse(BaseModel):
    """Reminder response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="Reminder ID")
    household_id: UUID = Field(..., description="Household ID")
    family_member_id: UUID | None = Field(None, description="Family member ID")
    reminder_type: ReminderType = Field(..., description="Reminder type")
    title: str = Field(..., description="Reminder title")
    description: str | None = Field(None, description="Reminder description")
    schedule_type: ScheduleType = Field(..., description="Schedule type")
    schedule_interval: int | None = Field(None, description="Interval for CUSTOM schedule")
    start_datetime: datetime = Field(..., description="Start datetime")
    end_datetime: datetime | None = Field(None, description="End datetime")
    is_active: bool = Field(..., description="Active status")
    created_at: datetime = Field(..., description="Creation timestamp")
