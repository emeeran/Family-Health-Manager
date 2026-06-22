"""User schemas."""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID


class UserResponse(BaseModel):
    """User response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    is_active: bool = Field(..., description="Active status")
    role: str = Field("user", description="User role")
    totp_enabled: bool = Field(False, description="2FA enabled")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_login: datetime | None = Field(None, description="Last login timestamp")
