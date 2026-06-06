"""Security utilities for password hashing and JWT handling."""
import hashlib
import secrets as _secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID
import jwt
from jwt.exceptions import PyJWTError as JWTError
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Token expiry durations
ACCESS_TOKEN_EXPIRY = timedelta(minutes=30)
REFRESH_TOKEN_EXPIRY = timedelta(days=7)


async def revoke_token_persist(token: str, db: AsyncSession) -> None:
    """Revoke an access token by persisting its jti to the database."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        jti = payload.get("jti")
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        if jti:
            from app.models.revoked_token import RevokedToken
            db.add(RevokedToken(jti=jti, expires_at=exp))
            await db.flush()
    except (JWTError, KeyError):
        pass


async def _is_revoked(jti: str | None, db: AsyncSession) -> bool:
    """Check if a JWT jti has been revoked (DB lookup)."""
    if not jti:
        return False
    from app.models.revoked_token import RevokedToken
    result = await db.execute(select(RevokedToken).where(RevokedToken.jti == jti))
    return result.scalar_one_or_none() is not None


def hash_password(password: str) -> str:
    """Hash password using Argon2."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: UUID) -> tuple[str, datetime]:
    """Create JWT access token for user (15-minute expiry)."""
    import secrets

    expires = datetime.now(timezone.utc) + ACCESS_TOKEN_EXPIRY
    payload = {
        "sub": str(user_id),
        "exp": expires,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_urlsafe(16),
        "type": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return token, expires


async def decode_access_token(token: str, db: AsyncSession) -> UUID | None:
    """Decode and validate JWT access token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if await _is_revoked(payload.get("jti"), db):
            return None
        return UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None


def validate_password_strength(password: str) -> bool:
    """Validate password meets strength requirements."""
    if len(password) < 8:
        return False
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
    return has_upper and has_digit and has_special



def _hash_token(token: str) -> str:
    """SHA-256 hash of a refresh token for database storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_refresh_token_value() -> str:
    """Generate a cryptographically random refresh token."""
    return _secrets.token_urlsafe(48)


async def create_refresh_token(user_id: UUID, db: AsyncSession) -> str:
    """Create and persist a refresh token. Returns the raw token value."""
    from app.models.refresh_token import RefreshToken

    raw_token = create_refresh_token_value()
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)

    refresh = RefreshToken(
        user_id=str(user_id),
        token_hash=token_hash,
        expires_at=now + REFRESH_TOKEN_EXPIRY,
        created_at=now,
    )
    db.add(refresh)
    await db.flush()
    return raw_token


async def verify_and_rotate_refresh_token(
    raw_token: str, db: AsyncSession
) -> tuple[str, str, UUID] | None:
    """Verify a refresh token and rotate it.

    Returns (new_access_token, new_refresh_token, user_id) or None if invalid.
    Revokes the entire token family if replay is detected.
    """
    from app.models.refresh_token import RefreshToken

    token_hash = _hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()

    if not stored:
        return None

    now = datetime.now(timezone.utc)

    # Token expired
    if stored.expires_at.replace(tzinfo=timezone.utc) <= now:
        return None

    # Replay detection: token was already used (revoked)
    if stored.revoked_at is not None:
        # Revoke entire family for this user (tokens created before this one)
        await db.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == stored.user_id,
                RefreshToken.created_at <= stored.created_at,
                RefreshToken.revoked_at.is_(None),
            )
        )
        family = (await db.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == stored.user_id,
                RefreshToken.created_at <= stored.created_at,
                RefreshToken.revoked_at.is_(None),
            )
        )).scalars().all()
        for t in family:
            t.revoked_at = now
        await db.flush()
        return None

    # Valid token — create new pair
    user_id = UUID(stored.user_id)
    access_token, _ = create_access_token(user_id)
    new_raw = create_refresh_token_value()
    new_hash = _hash_token(new_raw)
    new_expires = now + REFRESH_TOKEN_EXPIRY

    new_refresh = RefreshToken(
        user_id=str(user_id),
        token_hash=new_hash,
        expires_at=new_expires,
        created_at=now,
    )
    db.add(new_refresh)
    await db.flush()

    # Revoke old token and link to replacement
    stored.revoked_at = now
    stored.replaced_by = new_refresh.id
    await db.flush()

    return access_token, new_raw, user_id


async def revoke_all_refresh_tokens(user_id: UUID, db: AsyncSession) -> None:
    """Revoke all active refresh tokens for a user (used on logout)."""
    from app.models.refresh_token import RefreshToken

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == str(user_id),
            RefreshToken.revoked_at.is_(None),
        )
    )
    for t in result.scalars().all():
        t.revoked_at = now
    await db.flush()


async def prune_expired_tokens(db: AsyncSession) -> int:
    """Remove expired refresh and revoked tokens. Returns count pruned."""
    from app.models.refresh_token import RefreshToken
    from app.models.revoked_token import RevokedToken
    from sqlalchemy import delete

    now = datetime.now(timezone.utc)

    # Prune expired refresh tokens
    result = await db.execute(
        delete(RefreshToken).where(RefreshToken.expires_at <= now)
    )

    # Prune expired revoked access tokens
    await db.execute(
        delete(RevokedToken).where(RevokedToken.expires_at <= now)
    )
    await db.flush()
    return result.rowcount
