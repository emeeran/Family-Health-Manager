"""AI router."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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
    service = AIService(db, household_id=household.id)

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
    service = AIService(db, household_id=household.id)

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


@router.get("/status")
async def get_ai_status(
    db: AsyncSession = Depends(get_db),
    household: Household = Depends(get_household_from_token),
):
    """Check AI provider availability by sending a tiny test prompt to each.

    Shares :func:`provider_health.status_for_endpoint` with the extraction
    pre-flight, so opening this panel also warms the negative cache that prunes
    dead providers from the extraction chain — fewer "stuck at 45%" reports
    caused by dead keys silently stalling the failover.
    """
    import json
    from app.schemas.ai_provider_config import default_provider_config
    from app.schemas.household import FeatureSettings
    from app.services.ai.provider_health import status_for_endpoint

    # Load provider config from household settings
    config = None
    try:
        result = await db.execute(select(Household).where(Household.id == household.id))
        db_hh = result.scalar_one_or_none()
        if db_hh and db_hh.settings_json:
            fs = FeatureSettings(**json.loads(db_hh.settings_json))
            config = fs.ai_providers
    except Exception:
        pass  # Non-fatal — fall back to default provider config
    if config is None:
        config = default_provider_config()

    providers = await status_for_endpoint(config)
    return {"providers": providers}


@router.get("/extraction-metrics")
async def get_extraction_metrics(
    household: Household = Depends(get_household_from_token),
):
    """Per-extraction metrics summary (measurement harness).

    Returns an aggregate of recent extractions: latency p50/p95/max, cache hit
    rate, data rate, pruned rate, and distributions by provider/mime, plus the
    last ~10 raw records. Process-wide and in-memory (resets on restart).

    Lets prompt-trim / fast-model / image-downscale / concurrency changes be
    validated against real per-doc behaviour — the eval gate that previously
    blocked the deferred prompt-trim and fast-model work. Read-only; no PII (no
    file content, hashes, or member ids are recorded).
    """
    from app.services.ai.extraction_metrics import metrics_summary

    return metrics_summary()
