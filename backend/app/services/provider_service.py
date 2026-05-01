"""Provider service."""
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import update_model
from app.models.base import Provider, ProviderAssignment


class ProviderService:
    """Healthcare provider management service."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def create_provider(
        self,
        household_id: UUID,
        name: str,
        speciality: str | None = None,
        phone: str | None = None,
        address: str | None = None,
    ) -> Provider:
        """Create a new healthcare provider."""
        provider = Provider(
            household_id=household_id,
            name=name,
            speciality=speciality,
            phone=phone,
            address=address,
        )
        self.db.add(provider)
        await self.db.flush()
        return provider

    async def get_provider(self, household_id: UUID, provider_id: UUID) -> Provider:
        """Get provider by ID, ensuring household access."""
        result = await self.db.execute(
            select(Provider).where(
                Provider.id == provider_id,
                Provider.household_id == household_id,
            )
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise ValueError("Provider not found")
        return provider

    async def list_providers(
        self, household_id: UUID, speciality: str | None = None
    ) -> list[Provider]:
        """List all providers in household."""
        query = select(Provider).where(Provider.household_id == household_id)
        if speciality:
            query = query.where(Provider.speciality == speciality)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_provider(self, provider_id: UUID, **kwargs) -> Provider:
        """Update provider details."""
        allowed = {"name", "speciality", "phone", "address"}
        result = await self.db.execute(
            select(Provider).where(Provider.id == provider_id)
        )
        provider = result.scalar_one()
        return await update_model(self.db, provider, allowed_fields=allowed, **kwargs)

    async def delete_provider(self, household_id: UUID, provider_id: UUID) -> None:
        """Delete a provider."""
        provider = await self.get_provider(household_id, provider_id)
        await self.db.delete(provider)
        await self.db.flush()

    async def assign_provider_to_member(
        self, provider_id: UUID, member_id: UUID, uhid: str | None = None
    ) -> ProviderAssignment:
        """Assign a provider to a family member."""
        assignment = ProviderAssignment(
            provider_id=provider_id,
            family_member_id=member_id,
            uhid=uhid,
        )
        self.db.add(assignment)
        await self.db.flush()
        return assignment

    async def get_member_providers(self, member_id: UUID) -> list[tuple]:
        """Get all providers assigned to a member with provider and member info.

        Returns list of (ProviderAssignment, Provider, FamilyMember) tuples.
        """
        from app.models.base import FamilyMember

        result = await self.db.execute(
            select(ProviderAssignment, Provider, FamilyMember)
            .join(Provider, ProviderAssignment.provider_id == Provider.id)
            .join(FamilyMember, ProviderAssignment.family_member_id == FamilyMember.id)
            .where(ProviderAssignment.family_member_id == member_id)
        )
        return list(result.all())

    async def get_provider_members(self, provider_id: UUID) -> list[tuple[ProviderAssignment, str]]:
        """Get all members assigned to a provider with their names and UHIDs.

        Returns list of (assignment, member_name) tuples.
        """
        from app.models.base import FamilyMember

        result = await self.db.execute(
            select(ProviderAssignment, FamilyMember)
            .join(FamilyMember, ProviderAssignment.family_member_id == FamilyMember.id)
            .where(ProviderAssignment.provider_id == provider_id)
        )
        rows = result.all()
        return [(assignment, member) for assignment, member in rows]

    async def get_members_for_provider(self, provider_id: UUID) -> list[dict]:
        """Get members linked to a provider via assignments AND health records.

        Returns deduplicated list of dicts with:
        - family_member_id, family_member_name, uhid (nullable), visit_count
        """
        from app.models.base import FamilyMember, HealthRecord
        from sqlalchemy import func as sa_func

        members: dict[UUID, dict] = {}

        # 1. From explicit assignments (with UHID)
        result = await self.db.execute(
            select(ProviderAssignment, FamilyMember)
            .join(FamilyMember, ProviderAssignment.family_member_id == FamilyMember.id)
            .where(ProviderAssignment.provider_id == provider_id)
        )
        for assignment, member in result.all():
            members[member.id] = {
                "family_member_id": member.id,
                "family_member_name": f"{member.first_name} {member.last_name}",
                "uhid": assignment.uhid,
                "visit_count": 0,
            }

        # 2. From health records (derive visit count, don't overwrite UHID)
        result = await self.db.execute(
            select(
                FamilyMember.id,
                FamilyMember.first_name,
                FamilyMember.last_name,
                sa_func.count(HealthRecord.id),
            )
            .join(HealthRecord, HealthRecord.family_member_id == FamilyMember.id)
            .where(
                HealthRecord.provider_id == provider_id,
                HealthRecord.is_deleted.is_(False),
            )
            .group_by(FamilyMember.id, FamilyMember.first_name, FamilyMember.last_name)
        )
        for mid, first, last, count in result.all():
            if mid in members:
                members[mid]["visit_count"] = count
            else:
                members[mid] = {
                    "family_member_id": mid,
                    "family_member_name": f"{first} {last}",
                    "uhid": None,
                    "visit_count": count,
                }

        return list(members.values())

    async def remove_provider_assignment(self, assignment_id: UUID, household_id: UUID, member_id: UUID | None = None) -> None:
        """Remove provider assignment."""
        from app.models.base import FamilyMember

        query = (
            select(ProviderAssignment)
            .join(FamilyMember, ProviderAssignment.family_member_id == FamilyMember.id)
            .where(
                ProviderAssignment.id == assignment_id,
                FamilyMember.household_id == household_id,
            )
        )
        if member_id:
            query = query.where(ProviderAssignment.family_member_id == member_id)

        result = await self.db.execute(query)
        assignment = result.scalar_one_or_none()
        if assignment:
            await self.db.delete(assignment)
            await self.db.flush()

    async def update_assignment_uhid(self, assignment_id: UUID, uhid: str | None) -> ProviderAssignment:
        """Update UHID on a provider assignment."""
        result = await self.db.execute(
            select(ProviderAssignment).where(ProviderAssignment.id == assignment_id)
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            raise ValueError("Assignment not found")
        assignment.uhid = uhid
        await self.db.flush()
        return assignment
