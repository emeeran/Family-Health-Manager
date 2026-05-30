"""Dependency injection for routers."""
import base64
import json
from typing import Annotated
from uuid import UUID
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.base import User, Household, FamilyMember
from app.services.member_service import MemberService

security = HTTPBearer(auto_error=False)


def decode_cursor(cursor: str | None) -> dict | None:
    """Decode a base64-encoded pagination cursor. Raises 400 on invalid input."""
    if not cursor:
        return None
    try:
        return json.loads(base64.b64decode(cursor))
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid cursor parameter")


def _resolve_token(
    credentials: HTTPAuthorizationCredentials | None,
    request: Request,
) -> str:
    """Extract JWT token from cookie, Authorization header, or raise 401."""
    # Prefer httpOnly cookie
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token
    # Fallback to Authorization header
    if credentials:
        return credentials.credentials
    raise HTTPException(status_code=401, detail="Not authenticated")


async def get_household_from_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    db: AsyncSession = Depends(get_db),
) -> Household:
    """Get household from authenticated user."""
    jwt_token = _resolve_token(credentials, request)

    user_id = await decode_access_token(jwt_token, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(Household).where(Household.primary_user_id == user_id))
    household = result.scalar_one_or_none()

    if not household:
        raise HTTPException(status_code=404, detail="Household not found")

    return household


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT token."""
    jwt_token = _resolve_token(credentials, request)

    user_id = await decode_access_token(jwt_token, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """Require the current user to have admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_member_in_household(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
) -> FamilyMember:
    """Verify member belongs to the authenticated household and return it."""
    svc = MemberService(db)
    try:
        return await svc.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")
