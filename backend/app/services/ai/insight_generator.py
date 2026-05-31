"""Insight generation — generate_insight, generate_insight_stream, check_drug_interactions, search parsing."""
import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.base import AIInsight
from app.services.ai import base as _base
from app.services.ai.context_builder import (
    build_member_context,
    build_record_context,
    fmt_date,
)
from app.services.ai.providers.gemini import call_gemini_text
from app.services.ai.providers.groq import call_groq_text
from app.services.ai.providers.openrouter import call_openrouter_text
from app.services.ai.providers.ollama import ollama_chat, ollama_chat_stream
from app.services.ai.document_extractor import strip_markdown_fences

settings = get_settings()
logger = logging.getLogger(__name__)

_CLINICAL_SYSTEM_NOTE = (
    "You are a senior clinical reviewer AI, functioning as an attending physician "
    "conducting a thorough chart review. Your role is to produce professional clinical "
    "assessment notes.\n\n"
    "WRITING DISCIPLINE:\n"
    "- Write structured clinical assessment prose, not patient-facing summaries.\n"
    "- Use precise medical terminology appropriate for a medical record.\n"
    "- Always cite the specific value, date, or medication name from the patient data "
    "to support every clinical observation.\n"
    "- Follow clinical reasoning: observation -> significance -> recommendation.\n"
    "- Never state a conclusion without citing the supporting evidence from the provided data.\n"
    "- When comparing values across time, state both the date and the value for each data point.\n"
    "- Use standard clinical abbreviations where appropriate (e.g., T2DM, HTN, BID, TDS, HbA1c).\n\n"
    "EVIDENCE RULES:\n"
    "- Never fabricate lab values, medication dosages, or diagnoses not present in the context.\n"
    "- If data is missing or silent on a topic, write 'insufficient data to assess' rather than speculating.\n"
    "- Do NOT confuse Hemoglobin (Hb) with HbA1c -- they are different tests.\n"
    "- Use ONLY the exact dates from the context. Never approximate or guess dates.\n"
    "- Do NOT mix up data between family members -- each section is clearly labeled.\n"
    "- Today's date: {today}\n\n"
)


async def generate_insight(
    db: AsyncSession,
    prompt: str,
    health_record_id: UUID | None = None,
    conversation_id: UUID | None = None,
    member_id: UUID | None = None,
    comprehensive: bool = False,
) -> AIInsight:
    """Generate AI insight using local Ollama models (medgemma/gemma4)."""
    context = ""
    if member_id:
        cache_key = str(member_id)
        cached = _base.get_cache(cache_key)
        if cached:
            context = cached
        else:
            context = await build_member_context(db, member_id, fmt_date, comprehensive=comprehensive)
            _base.put_cache(cache_key, context)
        if health_record_id:
            context += await build_record_context(db, health_record_id, fmt_date)
    elif health_record_id:
        context = await build_record_context(db, health_record_id, fmt_date)

    response, provider = await _call_ollama_insight(prompt, context)

    insight = AIInsight(
        health_record_id=health_record_id,
        conversation_id=conversation_id,
        prompt=prompt,
        response=response,
        provider_used=provider,
    )
    db.add(insight)
    await db.flush()

    return insight


async def generate_insight_stream(
    db: AsyncSession,
    prompt: str,
    health_record_id: UUID | None = None,
    conversation_id: UUID | None = None,
    member_id: UUID | None = None,
    comprehensive: bool = False,
) -> AsyncGenerator[str, None]:
    """Generate AI insight with SSE progress events.

    Yields JSON strings suitable for SSE data lines:
    - {"stage":"context","message":"Loading patient records..."}
    - {"stage":"provider","provider":"Ollama medgemma"}
    - {"stage":"token","content":"..."}
    - {"stage":"complete","insight_id":"..."}
    - {"stage":"error","message":"..."}
    """
    def sse(data: dict) -> str:
        return json.dumps(data)

    # Stage 1: Build context (parallel when both member + record needed)
    context = ""
    if member_id:
        cache_key = str(member_id)
        cached = _base.get_cache(cache_key)
        if cached:
            context = cached
        else:
            yield sse({"stage": "context", "message": "Loading patient records..."})
            context = await build_member_context(db, member_id, fmt_date, comprehensive=comprehensive)
            _base.put_cache(cache_key, context)
        if health_record_id:
            yield sse({"stage": "context", "message": "Loading health record..."})
            context += await build_record_context(db, health_record_id, fmt_date)
    elif health_record_id:
        yield sse({"stage": "context", "message": "Loading health record..."})
        context = await build_record_context(db, health_record_id, fmt_date)

    # Stage 2: Generate — cloud first (more capable), Ollama as fallback
    system_note = _CLINICAL_SYSTEM_NOTE.format(today=fmt_date(date.today()))
    full_prompt = f"{system_note}{context}\n\nUser: {prompt}\n\nAssistant:" if context else prompt

    full_response = ""
    provider = ""

    # Preferred: cloud providers (streaming-capable, large context)
    cloud_providers: list[tuple] = []
    if settings.GEMINI_API_KEY:
        cloud_providers.append((call_gemini_text, "Google Gemini 2.5 Flash"))
    if settings.OPENROUTER_API_KEY:
        cloud_providers.append((call_openrouter_text, "OpenRouter DeepSeek V4 Flash"))
    if settings.GROQ_API_KEY:
        cloud_providers.append((call_groq_text, "Groq Llama-4-Scout"))

    if cloud_providers:
        try:
            yield sse({"stage": "provider", "provider": "Cloud AI"})
            full_response, provider = await _race_providers(full_prompt, cloud_providers)
            if full_response:
                # Stream the complete response token by token for UX
                for i in range(0, len(full_response), 40):
                    yield sse({"stage": "token", "content": full_response[i:i+40]})
        except Exception as exc:
            logger.warning("Cloud providers failed for streaming insight: %s", exc)

    # Fallback: Ollama models — prefer capable cloud-routed models over small local ones
    if not full_response:
        ollama_models = []
        # Capable cloud-routed models via Ollama (much better quality)
        for m in ["gemma4:31b-cloud"]:
            ollama_models.append((m, f"Ollama {m}"))
        # Then the configured models
        ollama_models.append((settings.OLLAMA_MODEL, f"Ollama {settings.OLLAMA_MODEL}"))
        ollama_models.append((settings.OLLAMA_TEXT_MODEL, f"Ollama {settings.OLLAMA_TEXT_MODEL}"))
        for model, label in ollama_models:
            try:
                yield sse({"stage": "provider", "provider": label})
                chunks = []
                async for chunk in ollama_chat_stream(model, full_prompt):
                    chunks.append(chunk)
                    yield sse({"stage": "token", "content": chunk})
                result = "".join(chunks)
                if result:
                    full_response = result
                    provider = label
                    break
            except Exception as exc:
                logger.warning("Ollama streaming model %s failed: %s", label, exc)

    # Stage 3: Save to DB
    yield sse({"stage": "context", "message": "Saving insight..."})
    insight = AIInsight(
        health_record_id=health_record_id,
        conversation_id=conversation_id,
        prompt=prompt,
        response=full_response,
        provider_used=provider,
    )
    db.add(insight)
    await db.flush()

    complete_event = {"stage": "complete", "insight_id": str(insight.id), "provider": provider}
    if member_id:
        complete_event["member_id"] = str(member_id)
    yield sse(complete_event)


async def _call_ollama_insight(prompt: str, context: str) -> tuple[str, str]:
    """Generate insight — races cloud providers in parallel for speed, Ollama as fallback."""
    system_note = _CLINICAL_SYSTEM_NOTE.format(today=fmt_date(date.today()))
    full_prompt = f"{system_note}{context}\n\nUser: {prompt}\n\nAssistant:" if context else prompt

    # Race cloud providers in parallel — OpenRouter DeepSeek first
    cloud_providers: list[tuple] = []
    if settings.OPENROUTER_API_KEY:
        cloud_providers.append((call_openrouter_text, "OpenRouter DeepSeek V4 Flash"))
    if settings.GROQ_API_KEY:
        cloud_providers.append((call_groq_text, "Groq Llama-4-Scout"))
    if settings.GEMINI_API_KEY:
        cloud_providers.append((call_gemini_text, "Google Gemini 2.5 Flash"))

    if cloud_providers:
        try:
            result, provider = await _race_providers(full_prompt, cloud_providers)
            if result:
                return result, provider
        except Exception as exc:
            logger.debug("All cloud providers failed for insight: %s", exc)

    # Fallback: try Ollama models — prefer capable cloud-routed models
    ollama_models = [("gemma4:31b-cloud", "Ollama gemma4:31b-cloud")]
    ollama_models.append((settings.OLLAMA_MODEL, f"Ollama {settings.OLLAMA_MODEL}"))
    ollama_models.append((settings.OLLAMA_TEXT_MODEL, f"Ollama {settings.OLLAMA_TEXT_MODEL}"))
    for model, label in ollama_models:
        try:
            result = await ollama_chat(model, full_prompt)
            if result:
                return result, label
        except Exception as exc:
            logger.warning("Ollama model %s failed: %s", label, exc)

    raise ValueError("All AI providers failed for insight generation")


async def _race_providers(
    prompt: str, providers: list[tuple]
) -> tuple[str, str]:
    """Race multiple providers in parallel — return the first successful result."""
    tasks: dict[asyncio.Task, str] = {}
    for provider_fn, label in providers:
        task = asyncio.create_task(provider_fn(prompt))
        tasks[task] = label

    pending = set(tasks.keys())
    errors: list[Exception] = []

    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            label = tasks[task]
            try:
                result = task.result()
                if result:
                    # Cancel remaining tasks and await cleanup
                    for t in pending:
                        t.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    logger.info("Insight race won by %s", label)
                    return result, label
            except Exception as exc:
                errors.append(exc)
                logger.debug("Provider %s failed in race: %s", label, exc)

    raise ValueError(f"All providers failed: {[str(e)[:80] for e in errors]}")


async def check_drug_interactions(
    db: AsyncSession, medications: list[dict], call_ai_fn
) -> list[dict]:
    """Check drug interactions between a list of medications using AI."""
    if len(medications) < 2:
        return []

    med_list = "\n".join(
        f"{i+1}. {m.get('medicine', 'Unknown')}"
        f" (type: {m.get('type', 'N/A')}, dosage: {m.get('dosage', 'N/A')})"
        for i, m in enumerate(medications)
    )

    prompt = f"""You are a clinical pharmacist AI. Analyze the following medication list for potential drug-drug interactions.

Medications:
{med_list}

IMPORTANT: Return ONLY valid JSON -- no markdown, no explanation, no code fences.

Return a JSON array of interactions found. Each interaction object must have:
- "drugs": array of the two drug names involved (strings)
- "severity": one of "high", "moderate", "low"
- "description": brief clinical description of the interaction (1-2 sentences)
- "recommendation": what the prescribing doctor should consider (1 sentence)

If there are no clinically significant interactions, return an empty array: []

Focus only on well-documented, clinically meaningful interactions. Do not flag trivial or theoretical risks."""

    response, _provider = await call_ai_fn(prompt, "")

    # Parse the JSON response
    if not response:
        return []

    try:
        # Strip markdown fences
        cleaned = strip_markdown_fences(response)

        # Find JSON array
        start = cleaned.find("[")
        if start == -1:
            return []
        depth = 0
        end = start
        for i in range(start, len(cleaned)):
            if cleaned[i] == "[":
                depth += 1
            elif cleaned[i] == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        parsed = json.loads(cleaned[start:end])
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    return []


async def parse_natural_language(
    text: str, member_list: str, call_ai_fn
) -> dict:
    """Parse natural language health text into structured record data."""
    prompt = f"""You are a health data extraction assistant. Parse the following natural language input into structured health record fields.

FAMILY MEMBERS:
{member_list}

USER INPUT: "{text}"

INSTRUCTIONS:
1. Return ONLY valid JSON -- no markdown, no explanation, no code fences.
2. Identify which family member the record is for using name or relationship (dad, mom, son, etc.).
3. Determine the record type from context.
4. Extract any relevant health data.
5. Today's date is {datetime.now().strftime('%Y-%m-%d')} -- use it to resolve relative dates like "yesterday", "last week".
6. For glucose/blood sugar mentions, include glucose_value and meal_timing.
7. For vitals mentions (weight, BP, heart rate, temperature), include individual fields.

RECORD TYPES: doctor_visit, lab_report, rx_eyeglass, blood_glucose, vitals, misc_record

Return this JSON:
{{
  "member_name": "matched name or relationship from text, lowercase" or null,
  "record_type": "doctor_visit" or null,
  "record_date": "YYYY-MM-DD" or null,
  "record_time": "HH:MM" or null,
  "diagnosis": "extracted diagnosis" or null,
  "prescription_text": "extracted prescriptions text" or null,
  "clinical_notes": "any other relevant notes" or null,
  "next_review_date": "YYYY-MM-DD" or null,
  "glucose_value": "number" or null,
  "meal_timing": "before_food|after_food" or null,
  "weight": "value" or null,
  "blood_pressure": "systolic/diastolic" or null,
  "heart_rate": "number" or null,
  "temperature": "value" or null,
  "confidence": "high|medium|low"
}}"""

    try:
        response, _ = await call_ai_fn(prompt, "")
        if not response:
            return {}
        cleaned = strip_markdown_fences(response)
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("NL parse failed: %s", exc)
        return {}


async def parse_search_query(
    query: str, member_list: str, call_ai_fn
) -> dict | None:
    """Parse a natural language search query into structured search filters."""
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""You are a search query parser for a family health records app.

FAMILY MEMBERS: {member_list}
TODAY: {today}

USER QUERY: "{query}"

Return ONLY valid JSON (no markdown, no code fences) with these fields:
{{
  "member_name": "name or relationship keyword from query, lowercase" or null,
  "record_types": ["doctor_visit"] or null,
  "date_from": "YYYY-MM-DD" or null,
  "date_to": "YYYY-MM-DD" or null,
  "keywords": ["word1", "word2"] or null
}}

Rules:
- Resolve "last", "recent", "latest" to a date_from ~30 days ago
- "this week" = 7 days ago
- "this month" = 30 days ago
- Only set record_types if the query clearly specifies a type (e.g. "blood test" = lab_report, "bp reading" = vitals, "prescription" = doctor_visit)
- keywords should capture specific medical terms, medicine names, conditions
- Keep it simple -- return null for fields you can't determine"""

    try:
        response, _ = await call_ai_fn(prompt, "")
        if not response:
            return None
        cleaned = strip_markdown_fences(response)
        parsed = json.loads(cleaned)
        # Remove null values
        return {k: v for k, v in parsed.items() if v is not None}
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Search query parse failed: %s", exc)
        return None
