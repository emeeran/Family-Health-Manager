"""Chat assistant — chat and chat_stream methods with conversation history."""
import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.base import AIInsight, Message, MessageRole
from app.services.ai import base as _base
from app.services.ai.context_builder import (
    build_member_context,
    build_household_context,
    fmt_date,
)
from app.services.ai.providers.gemini import call_gemini_text
from app.services.ai.providers.groq import call_groq_text
from app.services.ai.providers.openrouter import call_openrouter_text
from app.services.ai.providers.ollama import ollama_chat_stream

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


async def chat_stream(
    db: AsyncSession,
    conversation_id: UUID,
    user_message: str,
    member_id: UUID | None = None,
    household_id: UUID | None = None,
    call_ai_fn=None,
) -> AsyncGenerator[str, None]:
    """Stream AI chat response with SSE progress events.

    Yields JSON strings suitable for SSE data lines:
    - {"stage":"user_message","id":"...","content":"..."}
    - {"stage":"context","message":"Loading health context..."}
    - {"stage":"provider","provider":"..."}
    - {"stage":"token","content":"..."}
    - {"stage":"complete","assistant_message":{...}}
    - {"stage":"error","message":"..."}
    """
    def sse(data: dict) -> str:
        return json.dumps(data)

    # Save user message
    user_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=user_message,
    )
    db.add(user_msg)
    await db.flush()

    yield sse({
        "stage": "user_message",
        "id": str(user_msg.id),
        "content": user_message,
        "created_at": user_msg.created_at.isoformat(),
    })

    # Build health context and start history query in parallel
    health_context = ""
    history_task = asyncio.create_task(
        _get_conversation_history(db, conversation_id, limit=10)
    )
    if member_id:
        cache_key = str(member_id)
        if not _base.get_cache(cache_key):
            yield sse({"stage": "context", "message": "Loading health context..."})
            _base.put_cache(cache_key, await build_member_context(
                db, member_id, fmt_date, comprehensive=True
            ))
        health_context = _base.get_cache(cache_key) or ""
    elif household_id:
        cache_key = f"hh:{household_id}"
        if not _base.get_cache(cache_key):
            yield sse({"stage": "context", "message": "Loading health context..."})
            _base.put_cache(cache_key, await build_household_context(
                db, household_id, fmt_date
            ))
        health_context = _base.get_cache(cache_key) or ""

    history = await history_task
    full_context = f"{health_context}\n{history}" if health_context else history

    system_note = _CLINICAL_SYSTEM_NOTE.format(today=fmt_date(date.today()))
    full_prompt = f"{system_note}{full_context}\n\nUser: {user_message}\n\nAssistant:" if full_context else user_message

    full_response = ""
    provider = ""

    # Try Ollama streaming first
    for model, label in [
        (settings.OLLAMA_MODEL, f"Ollama {settings.OLLAMA_MODEL}"),
    ]:
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

    # Fallback: other Ollama models
    if not full_response:
        for model, label in [
            (settings.OLLAMA_TEXT_MODEL, f"Ollama {settings.OLLAMA_TEXT_MODEL}"),
        ]:
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

    # Fallback: cloud providers (non-streaming, sent as single token)
    if not full_response:
        cloud_providers: list[tuple] = []
        if settings.OPENROUTER_API_KEY:
            cloud_providers.append((call_openrouter_text, "OpenRouter DeepSeek V4 Flash"))
        if settings.GROQ_API_KEY:
            cloud_providers.append((call_groq_text, "Groq Llama-4-Scout"))
        if settings.GEMINI_API_KEY:
            cloud_providers.append((call_gemini_text, "Google Gemini 2.5 Flash"))

        if cloud_providers:
            try:
                yield sse({"stage": "provider", "provider": "Cloud AI"})
                full_response, provider = await _race_providers(full_prompt, cloud_providers)
                if full_response:
                    yield sse({"stage": "token", "content": full_response})
            except Exception as exc:
                logger.warning("Cloud providers failed for streaming chat: %s", exc)

    if not full_response:
        yield sse({"stage": "error", "message": "All AI providers failed. Please try again."})
        return

    # Save assistant message
    assistant_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=full_response,
    )
    db.add(assistant_msg)

    insight = AIInsight(
        conversation_id=conversation_id,
        prompt=user_message,
        response=full_response,
        provider_used=provider,
    )
    db.add(insight)
    await db.flush()

    yield sse({
        "stage": "complete",
        "assistant_message": {
            "id": str(assistant_msg.id),
            "role": "assistant",
            "content": full_response,
            "created_at": assistant_msg.created_at.isoformat(),
            "disclaimer": "This is not medical advice. Consult a healthcare professional.",
        },
        "provider": provider,
        "health_context": health_context,
    })


async def chat(
    db: AsyncSession,
    conversation_id: UUID,
    user_message: str,
    member_id: UUID | None = None,
    household_id: UUID | None = None,
    call_ai_fn=None,
) -> tuple[Message, Message, str, str]:
    """Send message and get AI response with conversation history.

    Returns (user_msg, assistant_msg, provider, health_context).
    """
    user_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=user_message,
    )
    db.add(user_msg)
    await db.flush()

    # Build health context and history in parallel
    async def _build_context() -> str:
        ctx = ""
        if member_id:
            cache_key = str(member_id)
            if not _base.get_cache(cache_key):
                _base.put_cache(cache_key, await build_member_context(
                    db, member_id, fmt_date, comprehensive=True
                ))
            ctx = _base.get_cache(cache_key) or ""
        elif household_id:
            cache_key = f"hh:{household_id}"
            if not _base.get_cache(cache_key):
                _base.put_cache(cache_key, await build_household_context(
                    db, household_id, fmt_date
                ))
            ctx = _base.get_cache(cache_key) or ""
        return ctx

    health_context, history = await asyncio.gather(
        _build_context(),
        _get_conversation_history(db, conversation_id, limit=10),
    )

    full_context = f"{health_context}\n{history}" if health_context else history

    response_text, provider = await call_ai_fn(user_message, full_context)

    assistant_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=response_text,
    )
    db.add(assistant_msg)

    insight = AIInsight(
        conversation_id=conversation_id,
        prompt=user_message,
        response=response_text,
        provider_used=provider,
    )
    db.add(insight)

    await db.flush()
    return user_msg, assistant_msg, provider, health_context


async def _get_conversation_history(db: AsyncSession, conversation_id: UUID, limit: int = 10) -> str:
    """Get recent conversation history."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()

    history = ""
    for msg in messages:
        role = "User" if msg.role == MessageRole.USER else "Assistant"
        history += f"{role}: {msg.content}\n"
    return history


async def _race_providers(
    prompt: str, providers: list[tuple]
) -> tuple[str, str]:
    """Race multiple providers in parallel — return the first successful result."""
    import asyncio
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
