"""Auth schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID


class LoginRequest(BaseModel):
    """Login request."""

    username: str = Field(..., min_length=3, max_length=50, description="Username")
    password: str = Field(..., min_length=8, max_length=128, description="Password")


class RegisterRequest(BaseModel):
    """Register request."""

    username: str = Field(..., min_length=3, max_length=50, description="Username")
    password: str = Field(..., min_length=8, max_length=128, description="Password")


class LoginResponse(BaseModel):
    """Login response."""

    access_token: str = Field(..., description="Session token")
    refresh_token: str = Field(..., description="Refresh token for rotation")
    token_type: str = Field("bearer", description="Token type")
    expires_at: datetime = Field(..., description="Token expiration")


class RefreshRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str = Field(..., description="Refresh token")


class RefreshResponse(BaseModel):
    """Refresh token response."""

    access_token: str = Field(..., description="New session token")
    refresh_token: str = Field(..., description="New refresh token")
    token_type: str = Field("bearer", description="Token type")
    expires_at: datetime = Field(..., description="Token expiration")


class UserResponse(BaseModel):
    """User response for auth endpoints."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    is_active: bool = Field(..., description="Active status")
    role: str = Field("user", description="User role")
