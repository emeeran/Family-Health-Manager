"""Authentication router."""
import json
import logging
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
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
from app.services.totp_service import TOTPService
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    ChangePasswordRequest,
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


@router.post("/login")
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

    # If 2FA is enabled, return requires_2fa flag instead of tokens
    if user.totp_enabled:
        return {"requires_2fa": True, "username": user.username}

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
    import jwt as _jwt
    from datetime import datetime, timezone
    payload = _jwt.decode(new_access, settings.SECRET_KEY, algorithms=["HS256"])
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


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    from app.core.security import verify_password, hash_password, validate_password_strength

    # Re-fetch user on this session — the object from get_current_user
    # is bound to a different DB session (FastAPI creates one per Depends(get_db))
    result = await db.execute(select(User).where(User.id == user.id))
    user = result.scalar_one()

    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if request.current_password == request.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")

    if not validate_password_strength(request.new_password):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters with uppercase, digit, and special character",
        )

    user.password_hash = hash_password(request.new_password)
    await db.flush()
    await db.commit()

    logger.info("Password changed for user %s", user.username)
    return {"message": "Password changed successfully"}


# ── 2FA endpoints ──


class TwoFASetupResponse(BaseModel):
    secret: str
    qr_code_base64: str
    backup_codes: list[str]


class TwoFAVerifyRequest(BaseModel):
    code: str


class TwoFALoginRequest(BaseModel):
    username: str
    code: str


@router.post("/2fa/setup", response_model=TwoFASetupResponse)
async def setup_2fa(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Begin 2FA setup — generates secret, QR code, and backup codes."""
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is already enabled")

    secret = TOTPService.generate_secret()
    qr_base64 = TOTPService.generate_qr_code_base64(secret, user.username)
    backup_codes = TOTPService.generate_backup_codes()

    # Store secret and backup codes (not yet enabled)
    user.totp_secret = secret
    user.backup_codes = json.dumps(backup_codes)
    await db.flush()

    return TwoFASetupResponse(
        secret=secret,
        qr_code_base64=qr_base64,
        backup_codes=backup_codes,
    )


@router.post("/2fa/verify")
async def verify_2fa_setup(
    request: TwoFAVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify first TOTP code during setup to enable 2FA."""
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA setup not initiated")
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is already enabled")

    if not TOTPService.verify_code(user.totp_secret, request.code):
        raise HTTPException(status_code=400, detail="Invalid code")

    user.totp_enabled = True
    await db.flush()

    return {"enabled": True}


@router.post("/2fa/disable")
async def disable_2fa(
    request: TwoFAVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable 2FA — requires current password or TOTP code."""
    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    # Accept either TOTP code or a backup code
    if user.totp_secret and TOTPService.verify_code(user.totp_secret, request.code):
        pass  # Valid TOTP code
    else:
        # Try backup code
        valid, updated_codes = TOTPService.verify_backup_code(user.backup_codes, request.code)
        if not valid:
            raise HTTPException(status_code=400, detail="Invalid code")
        user.backup_codes = updated_codes

    user.totp_enabled = False
    user.totp_secret = None
    user.backup_codes = None
    await db.flush()

    return {"enabled": False}


@router.post("/login/2fa")
async def login_2fa(
    request: TwoFALoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Complete login with 2FA code."""
    result = await db.execute(
        select(User).where(User.username == request.username, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()

    if not user or not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=401, detail="Invalid request")

    # Verify TOTP code or backup code
    if TOTPService.verify_code(user.totp_secret, request.code):
        pass
    else:
        valid, updated_codes = TOTPService.verify_backup_code(user.backup_codes, request.code)
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid 2FA code")
        user.backup_codes = updated_codes

    auth_service = AuthService(db)
    access_token, expires = auth_service.create_session_token(user.id)
    refresh_token = await create_refresh_token(user.id, db)

    _set_auth_cookies(response, access_token, refresh_token)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires,
    )
