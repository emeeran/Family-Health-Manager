"""Authentication service."""
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import User, Household
from app.core.security import hash_password, verify_password, create_access_token, validate_password_strength


class AuthService:
    """Authentication and user management service."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def register_user(self, username: str, password: str) -> tuple[User, Household]:
        """Register new user and create household."""
        if not validate_password_strength(password):
            raise ValueError("Password does not meet strength requirements")

        # Check if user already exists
        result = await self.db.execute(select(User).where(User.username == username))
        existing_user = result.scalar_one_or_none()
        if existing_user:
            raise ValueError("Username already exists")

        user = User(username=username, password_hash=hash_password(password))
        self.db.add(user)
        await self.db.flush()

        household = Household(name=f"{username}'s Household", primary_user_id=user.id)
        self.db.add(household)
        await self.db.flush()

        return user, household

    async def authenticate(self, username: str, password: str) -> User | None:
        """Authenticate user with username and password."""
        result = await self.db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.password_hash):
            return None

        user.last_login = datetime.now(timezone.utc)
        return user

    def create_session_token(self, user_id: UUID) -> tuple[str, datetime]:
        """Create JWT session token for user."""
        return create_access_token(user_id)

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """Get user by ID."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
