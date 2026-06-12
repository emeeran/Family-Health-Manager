"""Smart search router — NL-powered record search."""
import json
import logging
from datetime import date
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.base import Household, FamilyMember, HealthRecord, RecordType
from app.services.ai_service import AIService

router = APIRouter(prefix="/smart-search", tags=["Smart Search"])
logger = logging.getLogger(__name__)


class SmartSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)


class SmartSearchResult(BaseModel):
    id: str
    member_name: str
    record_type: str
    record_date: str
    diagnosis: str | None = None
    preview: str | None = None


class SmartSearchResponse(BaseModel):
    results: list[SmartSearchResult]
    ai_powered: bool = False


@router.post("/records", response_model=SmartSearchResponse)
async def smart_search_records(
    request: SmartSearchRequest,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(12, le=50),
):
    """Smart search records using AI-powered query understanding."""
    query = request.query.strip()

    # Fetch members for context
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.household_id == household.id,
            FamilyMember.is_active.is_(True),
        )
    )
    members = list(result.scalars().all())
    member_map = {str(m.id): f"{m.first_name} {m.last_name}" for m in members}

    # Try AI parsing for complex queries
    ai_powered = False
    filters: dict = {}

    # Only use AI for queries that look like natural language (>3 words or contains special patterns)
    words = query.split()
    use_ai = len(words) > 3 or any(
        kw in query.lower() for kw in ["last", "recent", "latest", "this week", "this month", "all", "'s"]
    )

    if use_ai:
        try:
            member_list = ", ".join(f"{m.first_name} {m.last_name} ({m.relationship_type.value})" for m in members)
            ai_service = AIService(db, household_id=household.id)
            parsed = await ai_service.parse_search_query(query, member_list)
            if parsed:
                filters = parsed
                ai_powered = True
        except Exception as exc:
            logger.warning("Smart search AI failed, falling back to text: %s", exc)

    # Build query
    stmt = (
        select(HealthRecord)
        .options(selectinload(HealthRecord.provider))
        .join(FamilyMember, HealthRecord.family_member_id == FamilyMember.id)
        .where(
            FamilyMember.household_id == household.id,
            FamilyMember.is_active.is_(True),
            HealthRecord.is_deleted.is_(False),
        )
    )

    if ai_powered:
        # Apply AI-parsed filters
        if filters.get("member_name"):
            name = filters["member_name"].lower()
            member_ids = [
                m.id for m in members
                if name in f"{m.first_name} {m.last_name}".lower()
                or name in m.relationship_type.value.lower()
            ]
            if member_ids:
                stmt = stmt.where(HealthRecord.family_member_id.in_(member_ids))

        if filters.get("record_types"):
            types = []
            for rt in filters["record_types"]:
                try:
                    types.append(RecordType(rt))
                except ValueError:
                    pass
            if types:
                stmt = stmt.where(HealthRecord.record_type.in_(types))

        if filters.get("date_from"):
            try:
                stmt = stmt.where(HealthRecord.record_date >= date.fromisoformat(filters["date_from"]))
            except ValueError:
                pass

        if filters.get("date_to"):
            try:
                stmt = stmt.where(HealthRecord.record_date <= date.fromisoformat(filters["date_to"]))
            except ValueError:
                pass

        if filters.get("keywords"):
            esc_pct = "\\%"
            esc_us = "\\_"
            dbl_bs = "\\\\"
            kw_clauses = [
                HealthRecord.clinical_data.ilike(
                    f"%{kw.replace(chr(92), dbl_bs).replace('%', esc_pct).replace('_', esc_us)}%",
                    escape="\\",
                )
                for kw in filters["keywords"]
            ]
            if kw_clauses:
                stmt = stmt.where(or_(*kw_clauses))
    else:
        # Fallback: simple ILIKE search
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(
            or_(
                HealthRecord.clinical_data.ilike(f"%{escaped}%", escape="\\"),
                HealthRecord.diagnosis.ilike(f"%{escaped}%", escape="\\"),
            )
        )

    stmt = stmt.order_by(HealthRecord.record_date.desc()).limit(limit)
    result = await db.execute(stmt)
    records = list(result.scalars().all())

    # Build response
    results = []
    for r in records:
        preview = None
        if r.diagnosis:
            preview = r.diagnosis
        elif r.clinical_data:
            try:
                parsed = json.loads(r.clinical_data)
                if isinstance(parsed, dict):
                    if parsed.get("chief_complaint"):
                        preview = parsed["chief_complaint"]
                    elif parsed.get("glucose_value"):
                        preview = f"Glucose: {parsed['glucose_value']} mg/dL"
            except (json.JSONDecodeError, ValueError):
                preview = r.clinical_data[:60]

        results.append(SmartSearchResult(
            id=str(r.id),
            member_name=member_map.get(str(r.family_member_id), "Unknown"),
            record_type=r.record_type.value,
            record_date=r.record_date.isoformat(),
            diagnosis=r.diagnosis,
            preview=preview,
        ))

    return SmartSearchResponse(results=results, ai_powered=ai_powered)
