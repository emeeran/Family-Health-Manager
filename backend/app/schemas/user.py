"""User schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID


class UserCreate(BaseModel):
    """User registration request."""

    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    password: str = Field(
        ..., min_length=8, max_length=128, description="Password with strength requirements"
    )


class UserUpdate(BaseModel):
    """User update request."""

    password: str | None = Field(None, min_length=8, max_length=128, description="New password")
    is_active: bool | None = Field(None, description="Active status")


class UserResponse(BaseModel):
    """User response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    is_active: bool = Field(..., description="Active status")
    totp_enabled: bool = Field(False, description="2FA enabled")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_login: datetime | None = Field(None, description="Last login timestamp")
