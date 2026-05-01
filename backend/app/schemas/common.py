"""Common schemas for pagination and errors."""
from typing import Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response envelope."""

    items: list[T] = Field(..., description="List of items")
    pagination: "PaginationInfo" = Field(..., description="Pagination metadata")


class PaginationInfo(BaseModel):
    """Pagination metadata."""

    next_cursor: str | None = Field(None, description="Cursor for next page")
    has_more: bool = Field(..., description="Whether more items exist")
    total_count: int = Field(..., description="Total item count")


class ErrorResponse(BaseModel):
    """Error response schema."""

    status_code: int = Field(..., description="HTTP status code", json_schema_extra={"example": 400})
    error: str = Field(..., description="Error type", json_schema_extra={"example": "validation_error"})
    message: str = Field(..., description="Human-readable message", json_schema_extra={"example": "Invalid input data"})
    details: list[str] | None = Field(
        None, description="Additional error details", json_schema_extra={"example": ["Field 'username' is required"]}
    )


PaginatedResponse.model_rebuild()
