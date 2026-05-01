"""Household service."""
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import Household


class HouseholdService:
    """Household management service."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def get_household_by_user(self, user_id: UUID) -> Household | None:
        """Get household for a user."""
        result = await self.db.execute(select(Household).where(Household.primary_user_id == user_id))
        return result.scalar_one_or_none()

    async def get_household(self, household_id: UUID) -> Household | None:
        """Get household by ID."""
        result = await self.db.execute(select(Household).where(Household.id == household_id))
        return result.scalar_one_or_none()

    async def update_household(self, household_id: UUID, name: str) -> Household:
        """Update household name."""
        result = await self.db.execute(
            select(Household).where(Household.id == household_id)
        )
        household = result.scalar_one()
        household.name = name
        await self.db.flush()
        return household
