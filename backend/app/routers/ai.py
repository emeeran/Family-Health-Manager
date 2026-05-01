"""AI router."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.services.ai_service import AIService
from app.schemas.ai_insight import AIInsightRequest, AIInsightResponse
from app.models.base import Household


class ExplainRequest(BaseModel):
    """Validated request body for /ai/explain."""
    prompt: str = Field("Explain these health records", max_length=2000)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Health Intelligence"])


@router.post("/insights", response_model=AIInsightResponse)
async def generate_insight(
    request: AIInsightRequest,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Generate AI insight for a health record."""
    service = AIService(db)

    try:
        insight = await service.generate_insight(
            prompt=request.prompt,
            health_record_id=request.health_record_id,
        )
    except Exception:
        logger.exception("AI insight generation failed")
        raise HTTPException(status_code=500, detail="AI service unavailable")

    return {
        "id": insight.id,
        "health_record_id": insight.health_record_id,
        "conversation_id": insight.conversation_id,
        "prompt": insight.prompt,
        "response": insight.response,
        "provider_used": insight.provider_used,
        "generated_at": insight.generated_at,
        "disclaimer": "This is not medical advice. Consult a healthcare professional.",
    }


@router.post("/explain", response_model=AIInsightResponse)
async def explain_records(
    request: ExplainRequest,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get plain-language explanation of health records."""
    service = AIService(db)

    prompt = request.prompt

    try:
        insight = await service.generate_insight(
            prompt=prompt,
        )
    except Exception:
        logger.exception("AI explain failed")
        raise HTTPException(status_code=500, detail="AI service unavailable")

    return {
        "id": insight.id,
        "health_record_id": None,
        "conversation_id": insight.conversation_id,
        "prompt": prompt,
        "response": insight.response,
        "provider_used": insight.provider_used,
        "generated_at": insight.generated_at,
        "disclaimer": "This is not medical advice. Consult a healthcare professional.",
    }
