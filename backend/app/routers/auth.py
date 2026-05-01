"""Authentication router."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    validate_password_strength,
    revoke_token_persist,
    create_refresh_token,
    verify_and_rotate_refresh_token,
    revoke_all_refresh_tokens,
)
from app.core.deps import get_current_user
from app.services.auth_service import AuthService
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    UserResponse,
)
from app.schemas.user import UserResponse as FullUserResponse
from app.models.base import User

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Cookie settings
_COOKIE_SECURE = settings.APP_ENV == "production"
_COOKIE_SAMESITE = "strict"
_COOKIE_PATH = "/"
_ACCESS_COOKIE_MAX_AGE = 15 * 60  # 15 minutes
_REFRESH_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set httpOnly cookies for access and refresh tokens."""
    response.set_cookie(
        "access_token",
        access_token,
        max_age=_ACCESS_COOKIE_MAX_AGE,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        path=_COOKIE_PATH,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=_REFRESH_COOKIE_MAX_AGE,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        path="/api/v1/auth",  # Only sent to auth endpoints
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear auth cookies."""
    response.delete_cookie("access_token", path=_COOKIE_PATH)
    response.delete_cookie("refresh_token", path="/api/v1/auth")


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user and create household."""
    if not validate_password_strength(request.password):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters with uppercase, digit, and special character",
        )

    auth_service = AuthService(db)

    try:
        user, household = await auth_service.register_user(request.username, request.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return user


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate and receive session token via httpOnly cookie."""
    auth_service = AuthService(db)

    user = await auth_service.authenticate(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token, expires = auth_service.create_session_token(user.id)
    refresh_token = await create_refresh_token(user.id, db)

    _set_auth_cookies(response, access_token, refresh_token)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Rotate refresh token and issue new access token.

    Accepts refresh token from cookie or request body.
    """
    # Try cookie first, then body
    raw_token = request.cookies.get("refresh_token")
    if not raw_token and body:
        raw_token = body.refresh_token
    if not raw_token:
        raise HTTPException(status_code=401, detail="No refresh token provided")

    result = await verify_and_rotate_refresh_token(raw_token, db)
    if not result:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    new_access, new_refresh, user_id = result

    _set_auth_cookies(response, new_access, new_refresh)

    # Get expiry from the new access token
    from jose import jwt
    payload = jwt.decode(new_access, settings.SECRET_KEY, algorithms=["HS256"])
    from datetime import datetime, timezone
    expires = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    return RefreshResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_at=expires,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invalidate session token and clear cookies."""
    # Revoke access token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        await revoke_token_persist(auth[7:], db)

    # Revoke all refresh tokens for this user
    await revoke_all_refresh_tokens(user.id, db)

    _clear_auth_cookies(response)
    return {"message": "Logged out"}


@router.get("/me", response_model=FullUserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Get current user profile."""
    return user
