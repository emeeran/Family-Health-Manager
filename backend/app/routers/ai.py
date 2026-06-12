"""AI router."""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import get_settings
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
    """Check AI provider availability by sending a tiny test prompt to each."""
    import json
    from app.schemas.ai_provider_config import PROVIDER_LABELS, default_provider_config
    from app.schemas.household import FeatureSettings

    settings = get_settings()
    test_prompt = "Reply with only the word OK."

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

    providers: list[dict] = []

    def _friendly_error(exc: Exception) -> str:
        """Translate provider HTTP errors into user-friendly messages."""
        import httpx
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            messages = {
                401: "Invalid API key",
                402: "Insufficient credits — top up your account",
                403: "API key lacks permission or API not enabled",
                404: "Model not found — check model name",
                429: "Rate limited — try again later",
            }
            return messages.get(status, f"HTTP {status}: {exc.response.text[:60]}")
        if isinstance(exc, httpx.TimeoutException):
            return "Request timed out"
        if isinstance(exc, httpx.ConnectError):
            return "Connection refused — is the service running?"
        return str(exc)[:100]

    for prov in config.providers:
        label = PROVIDER_LABELS.get(prov.id, prov.id)
        model = prov.model

        try:
            if prov.id == "ollama":
                from app.services.ai.providers.ollama import call_ollama_text
                start = time.monotonic()
                result = await call_ollama_text(test_prompt, model=model or None)
                elapsed = time.monotonic() - start
                providers.append({"name": label, "id": prov.id, "model": model, "available": bool(result), "response_ms": round(elapsed * 1000)})
            elif prov.id == "gemini":
                if not settings.GEMINI_API_KEY:
                    providers.append({"name": label, "id": prov.id, "model": model, "available": False, "error": "No API key"})
                    continue
                from app.services.ai.providers.gemini import call_gemini_text
                start = time.monotonic()
                result = await call_gemini_text(test_prompt, model=model)
                elapsed = time.monotonic() - start
                providers.append({"name": label, "id": prov.id, "model": model, "available": bool(result), "response_ms": round(elapsed * 1000)})
            elif prov.id == "openrouter":
                if not settings.OPENROUTER_API_KEY:
                    providers.append({"name": label, "id": prov.id, "model": model, "available": False, "error": "No API key"})
                    continue
                from app.services.ai.providers.openrouter import call_openrouter_text
                start = time.monotonic()
                result = await call_openrouter_text(test_prompt, model=model)
                elapsed = time.monotonic() - start
                providers.append({"name": label, "id": prov.id, "model": model, "available": bool(result), "response_ms": round(elapsed * 1000)})
            elif prov.id == "groq":
                if not settings.GROQ_API_KEY:
                    providers.append({"name": label, "id": prov.id, "model": model, "available": False, "error": "No API key"})
                    continue
                from app.services.ai.providers.groq import call_groq_text
                start = time.monotonic()
                result = await call_groq_text(test_prompt, model=model)
                elapsed = time.monotonic() - start
                providers.append({"name": label, "id": prov.id, "model": model, "available": bool(result), "response_ms": round(elapsed * 1000)})
            elif prov.id == "openai":
                if not settings.OPENAI_API_KEY:
                    providers.append({"name": label, "id": prov.id, "model": model, "available": False, "error": "No API key"})
                    continue
                from app.services.ai.providers.openai import call_openai_text
                start = time.monotonic()
                result = await call_openai_text(test_prompt, model=model)
                elapsed = time.monotonic() - start
                providers.append({"name": label, "id": prov.id, "model": model, "available": bool(result), "response_ms": round(elapsed * 1000)})
        except Exception as exc:
            providers.append({"name": label, "id": prov.id, "model": model, "available": False, "error": _friendly_error(exc)})

    return {"providers": providers}
