"""AI service package -- AIService facade that delegates to sub-modules.

Public API is identical to the original monolithic ai_service.py.
"""
import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import date
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.base import AIInsight, Message, MessageRole

# Re-export sub-module constants used by tests / callers
from app.services.ai.document_extractor import EXTRACTION_PROMPT  # noqa: F401

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


class AIService:
    """AI health intelligence service with provider failover.

    This class preserves the original public API. Tests patch methods via
    ``patch.object(ai_service, "_call_ollama_insight", ...)`` etc.
    """

    # ---- Class-level attributes preserved for test compatibility ----
    _member_context_cache: dict[str, str] = {}
    _MAX_CACHE_SIZE = 64
    _cloud_client: httpx.AsyncClient | None = None
    _ollama_client: httpx.AsyncClient | None = None
    _client_lock: asyncio.Lock | None = None

    # ---- Lazy lock / shared client accessors (delegate to base module) ----

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        from app.services.ai import base as _base
        return _base.get_lock()

    @classmethod
    async def _get_cloud_client(cls) -> httpx.AsyncClient:
        from app.services.ai import base as _base
        client = await _base.get_cloud_client()
        cls._cloud_client = _base.cloud_client
        return client

    @classmethod
    async def _get_ollama_client(cls) -> httpx.AsyncClient:
        from app.services.ai import base as _base
        client = await _base.get_ollama_client()
        cls._ollama_client = _base.ollama_client
        return client

    @classmethod
    def invalidate_member_cache(cls, member_id: "UUID | str") -> None:  # noqa: F821
        from app.services.ai import base as _base
        _base.invalidate_member_cache(member_id)
        cls._member_context_cache = _base.member_context_cache

    @classmethod
    def _put_cache(cls, key: str, value: str) -> None:
        from app.services.ai import base as _base
        _base.put_cache(key, value)
        cls._member_context_cache = _base.member_context_cache

    @classmethod
    def _get_cache(cls, key: str) -> str | None:
        from app.services.ai import base as _base
        return _base.get_cache(key)

    # ---- Static helper re-exports (test compatibility) ----

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        from app.services.ai.document_extractor import strip_markdown_fences
        return strip_markdown_fences(text)

    @staticmethod
    def _summarize_clinical_data(raw: str | None) -> str:
        from app.services.ai.context_builder import summarize_clinical_data
        return summarize_clinical_data(raw)

    @staticmethod
    def _build_lab_trends_from_records(records: list) -> str:
        from app.services.ai.context_builder import build_lab_trends_from_records
        return build_lab_trends_from_records(records)

    @staticmethod
    def _fmt_date(d: object) -> str:
        from app.services.ai.context_builder import fmt_date
        return fmt_date(d)

    # ---- Constructor ----

    def __init__(self, db: AsyncSession):
        self.db = db
        self.last_provider: str = ""
        self._last_provider_ref: list[str] = [""]

    # ---- Insight generation (kept inline for test patching) ----

    async def generate_insight(
        self,
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
            cached = self._get_cache(cache_key)
            if cached:
                context = cached
            else:
                context = await self._build_member_context(member_id, comprehensive=comprehensive)
                self._put_cache(cache_key, context)
            if health_record_id:
                context += await self._build_record_context(health_record_id)
        elif health_record_id:
            context = await self._build_record_context(health_record_id)

        response, provider = await self._call_ollama_insight(prompt, context)

        insight = AIInsight(
            health_record_id=health_record_id,
            conversation_id=conversation_id,
            prompt=prompt,
            response=response,
            provider_used=provider,
        )
        self.db.add(insight)
        await self.db.flush()

        return insight

    async def generate_insight_stream(
        self,
        prompt: str,
        health_record_id: UUID | None = None,
        conversation_id: UUID | None = None,
        member_id: UUID | None = None,
        comprehensive: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Generate AI insight with SSE progress events."""
        def sse(data: dict) -> str:
            return json.dumps(data)

        # Stage 1: Build context
        context = ""
        if member_id:
            cache_key = str(member_id)
            cached = self._get_cache(cache_key)
            if cached:
                context = cached
            else:
                yield sse({"stage": "context", "message": "Loading patient records..."})
                context = await self._build_member_context(member_id, comprehensive=comprehensive)
                self._put_cache(cache_key, context)
            if health_record_id:
                yield sse({"stage": "context", "message": "Loading health record..."})
                context += await self._build_record_context(health_record_id)
        elif health_record_id:
            yield sse({"stage": "context", "message": "Loading health record..."})
            context = await self._build_record_context(health_record_id)

        # Stage 2: Generate — Ollama first (streaming), cloud as fallback
        system_note = _CLINICAL_SYSTEM_NOTE.format(today=self._fmt_date(date.today()))
        full_prompt = f"{system_note}{context}\n\nUser: {prompt}\n\nAssistant:" if context else prompt

        full_response = ""
        provider = ""

        # Primary: Ollama models (local streaming)
        ollama_models = [(settings.OLLAMA_MODEL, f"Ollama {settings.OLLAMA_MODEL}")]
        if settings.OLLAMA_TEXT_MODEL != settings.OLLAMA_MODEL:
            ollama_models.append((settings.OLLAMA_TEXT_MODEL, f"Ollama {settings.OLLAMA_TEXT_MODEL}"))
        for model, label in ollama_models:
            try:
                yield sse({"stage": "provider", "provider": label})
                chunks = []
                async for chunk in self._ollama_chat_stream(model, full_prompt):
                    chunks.append(chunk)
                    yield sse({"stage": "token", "content": chunk})
                result = "".join(chunks)
                if result:
                    full_response = result
                    provider = label
                    break
            except Exception as exc:
                logger.warning("Ollama streaming model %s failed: %s", label, exc)

        # Fallback: cloud providers (non-streaming)
        if not full_response:
            cloud_providers: list[tuple] = []
            if settings.GEMINI_API_KEY:
                cloud_providers.append((self._call_gemini_text, "Google Gemini 2.5 Flash"))
            if settings.OPENROUTER_API_KEY:
                cloud_providers.append((self._call_openrouter_text, "OpenRouter DeepSeek V4 Flash"))
            if settings.GROQ_API_KEY:
                cloud_providers.append((self._call_groq_text, "Groq Llama-4-Scout"))

            if cloud_providers:
                try:
                    yield sse({"stage": "provider", "provider": "Cloud AI"})
                    full_response, provider = await self._race_providers(full_prompt, cloud_providers)
                    if full_response:
                        for i in range(0, len(full_response), 40):
                            yield sse({"stage": "token", "content": full_response[i:i+40]})
                except Exception as exc:
                    logger.warning("Cloud providers failed for streaming insight: %s", exc)

        # Stage 3: Save
        yield sse({"stage": "context", "message": "Saving insight..."})
        insight = AIInsight(
            health_record_id=health_record_id,
            conversation_id=conversation_id,
            prompt=prompt,
            response=full_response,
            provider_used=provider,
        )
        self.db.add(insight)
        await self.db.flush()

        complete_event = {"stage": "complete", "insight_id": str(insight.id), "provider": provider}
        if member_id:
            complete_event["member_id"] = str(member_id)
        yield sse(complete_event)

    # ---- Chat (kept inline for test patching) ----

    async def chat_stream(
        self,
        conversation_id: UUID,
        user_message: str,
        member_id: UUID | None = None,
        household_id: UUID | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream AI chat response with SSE progress events."""
        def sse(data: dict) -> str:
            return json.dumps(data)

        user_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=user_message,
        )
        self.db.add(user_msg)
        await self.db.flush()

        yield sse({
            "stage": "user_message",
            "id": str(user_msg.id),
            "content": user_message,
            "created_at": user_msg.created_at.isoformat(),
        })

        health_context = ""
        if member_id:
            cache_key = str(member_id)
            if not self._get_cache(cache_key):
                yield sse({"stage": "context", "message": "Loading health context..."})
                self._put_cache(cache_key, await self._build_member_context(
                    member_id, comprehensive=True
                ))
            health_context = self._get_cache(cache_key) or ""
        elif household_id:
            cache_key = f"hh:{household_id}"
            if not self._get_cache(cache_key):
                yield sse({"stage": "context", "message": "Loading health context..."})
                self._put_cache(cache_key, await self._build_household_context(
                    household_id
                ))
            health_context = self._get_cache(cache_key) or ""

        history = await self._get_conversation_history(conversation_id, limit=10)
        full_context = f"{health_context}\n{history}" if health_context else history

        system_note = _CLINICAL_SYSTEM_NOTE.format(today=self._fmt_date(date.today()))
        full_prompt = f"{system_note}{full_context}\n\nUser: {user_message}\n\nAssistant:" if full_context else user_message

        full_response = ""
        provider = ""

        for model, label in [
            (settings.OLLAMA_MODEL, f"Ollama {settings.OLLAMA_MODEL}"),
        ]:
            try:
                yield sse({"stage": "provider", "provider": label})
                chunks = []
                async for chunk in self._ollama_chat_stream(model, full_prompt):
                    chunks.append(chunk)
                    yield sse({"stage": "token", "content": chunk})
                result = "".join(chunks)
                if result:
                    full_response = result
                    provider = label
                    break
            except Exception as exc:
                logger.warning("Ollama streaming model %s failed: %s", label, exc)

        if not full_response:
            for model, label in [
                (settings.OLLAMA_TEXT_MODEL, f"Ollama {settings.OLLAMA_TEXT_MODEL}"),
            ]:
                try:
                    yield sse({"stage": "provider", "provider": label})
                    chunks = []
                    async for chunk in self._ollama_chat_stream(model, full_prompt):
                        chunks.append(chunk)
                        yield sse({"stage": "token", "content": chunk})
                    result = "".join(chunks)
                    if result:
                        full_response = result
                        provider = label
                        break
                except Exception as exc:
                    logger.warning("Ollama streaming model %s failed: %s", label, exc)

        if not full_response:
            cloud_providers: list[tuple] = []
            if settings.OPENROUTER_API_KEY:
                cloud_providers.append((self._call_openrouter_text, "OpenRouter DeepSeek V4 Flash"))
            if settings.GROQ_API_KEY:
                cloud_providers.append((self._call_groq_text, "Groq Llama-4-Scout"))
            if settings.GEMINI_API_KEY:
                cloud_providers.append((self._call_gemini_text, "Google Gemini 2.5 Flash"))

            if cloud_providers:
                try:
                    yield sse({"stage": "provider", "provider": "Cloud AI"})
                    full_response, provider = await self._race_providers(full_prompt, cloud_providers)
                    if full_response:
                        yield sse({"stage": "token", "content": full_response})
                except Exception as exc:
                    logger.warning("Cloud providers failed for streaming chat: %s", exc)

        if not full_response:
            yield sse({"stage": "error", "message": "All AI providers failed. Please try again."})
            return

        assistant_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=full_response,
        )
        self.db.add(assistant_msg)

        insight = AIInsight(
            conversation_id=conversation_id,
            prompt=user_message,
            response=full_response,
            provider_used=provider,
        )
        self.db.add(insight)
        await self.db.flush()

        yield sse({
            "stage": "complete",
            "assistant_message": {
                "id": str(assistant_msg.id),
                "conversation_id": str(conversation_id),
                "role": "assistant",
                "content": full_response,
                "created_at": assistant_msg.created_at.isoformat(),
                "disclaimer": "This is not medical advice. Consult a healthcare professional.",
            },
            "provider": provider,
            "health_context": health_context,
        })

    async def chat(
        self,
        conversation_id: UUID,
        user_message: str,
        member_id: UUID | None = None,
        household_id: UUID | None = None,
    ) -> tuple[Message, Message, str, str]:
        """Send message and get AI response with conversation history."""
        user_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=user_message,
        )
        self.db.add(user_msg)
        await self.db.flush()

        history = await self._get_conversation_history(conversation_id, limit=10)

        health_context = ""
        if member_id:
            cache_key = str(member_id)
            if not self._get_cache(cache_key):
                self._put_cache(cache_key, await self._build_member_context(
                    member_id, comprehensive=True
                ))
            health_context = self._get_cache(cache_key) or ""
        elif household_id:
            cache_key = f"hh:{household_id}"
            if not self._get_cache(cache_key):
                self._put_cache(cache_key, await self._build_household_context(
                    household_id
                ))
            health_context = self._get_cache(cache_key) or ""

        full_context = f"{health_context}\n{history}" if health_context else history

        response_text, provider = await self._call_ai(user_message, full_context)

        assistant_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=response_text,
        )
        self.db.add(assistant_msg)

        insight = AIInsight(
            conversation_id=conversation_id,
            prompt=user_message,
            response=response_text,
            provider_used=provider,
        )
        self.db.add(insight)

        await self.db.flush()
        return user_msg, assistant_msg, provider, health_context

    # ---- Drug interactions & search ----

    async def check_drug_interactions(self, medications: list[dict]) -> list[dict]:
        """Check drug interactions between a list of medications using AI."""
        from app.services.ai.insight_generator import check_drug_interactions
        return await check_drug_interactions(self.db, medications, self._call_ai)

    async def parse_natural_language(self, text: str, member_list: str) -> dict:
        """Parse natural language health text into structured record data."""
        from app.services.ai.insight_generator import parse_natural_language
        return await parse_natural_language(text, member_list, self._call_ai)

    async def parse_search_query(self, query: str, member_list: str) -> dict | None:
        """Parse a natural language search query into structured search filters."""
        from app.services.ai.insight_generator import parse_search_query
        return await parse_search_query(query, member_list, self._call_ai)

    # ---- Document extraction ----

    async def classify_document(self, file_path: str, mime_type: str):
        """Classify a document into a record type using AI with keyword fallback."""
        from app.services.ai.document_extractor import classify_document
        return await classify_document(file_path, mime_type, self._call_ai)

    async def extract_medical_data(self, file_path: str, mime_type: str):
        """Extract structured medical data from a document file via vision AI."""
        from app.services.ai.document_extractor import extract_medical_data
        return await extract_medical_data(
            self.db, file_path, mime_type, self._last_provider_ref
        )

    async def generate_consultation_summary(self, extracted_data: dict) -> str:
        """Generate a human-readable consultation summary from extracted fields.

        Uses the AI provider failover chain. Falls back to a basic template
        if all providers fail.
        """
        from pathlib import Path

        # Build context from extracted data
        parts: list[str] = []
        field_labels = {
            "record_type": "Record Type",
            "record_date": "Visit Date",
            "record_time": "Visit Time",
            "provider_name": "Provider",
            "chief_complaint": "Chief Complaint",
            "diagnosis": "Diagnosis",
            "existing_conditions": "Existing Conditions",
            "investigations": "Investigations Ordered",
            "prescription_text": "Prescription Text",
            "next_review_date": "Next Review Date",
            "clinical_data": "Clinical Notes",
        }
        for key, label in field_labels.items():
            val = extracted_data.get(key)
            if val:
                parts.append(f"**{label}:** {val}")

        # Always include record type and date even without other data
        if not parts:
            rt = extracted_data.get("record_type", "")
            rd = extracted_data.get("record_date", "")
            if rt or rd:
                parts.append(f"**Record:** {rt} on {rd}")

        # Structured tables
        prescriptions = extracted_data.get("prescriptions")
        if prescriptions and isinstance(prescriptions, list):
            parts.append("\n**Prescriptions:**")
            for rx in prescriptions:
                parts.append(
                    f"- {rx.get('type', '')} {rx.get('medicine', '')} "
                    f"{rx.get('dosage', '')} {rx.get('timing', '')} "
                    f"× {rx.get('duration', '')} {rx.get('note', '')}".strip()
                )

        lab_tests = extracted_data.get("lab_tests")
        if lab_tests and isinstance(lab_tests, list):
            parts.append("\n**Lab Tests:**")
            for lt in lab_tests:
                parts.append(
                    f"- {lt.get('test_name', '')}: {lt.get('result', '')} "
                    f"{lt.get('units', '')} (ref: {lt.get('ref_value', '')}) "
                    f"— {lt.get('note', '')}".strip()
                )

        if not parts:
            return ""

        context_str = "\n".join(parts)

        # Load prompt template
        prompt_path = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "consultation_summary.md"
        try:
            prompt_template = prompt_path.read_text()
        except FileNotFoundError:
            prompt_template = (
                "Generate a clear consultation summary from this medical data.\n\n"
                "{extracted_data}"
            )

        prompt = prompt_template.replace("{extracted_data}", context_str)

        # Try AI providers
        try:
            result, provider = await self._call_ai(prompt, "")
            if result:
                logger.info("Consultation summary generated via %s", provider)
                return self._strip_markdown_fences(result)
        except Exception as exc:
            logger.warning("AI summary generation failed, using template: %s", exc)

        # Fallback: basic template from structured fields
        return self._build_template_summary(extracted_data)

    @staticmethod
    def _build_template_summary(data: dict) -> str:
        """Build a basic summary template without AI — used as fallback."""
        lines: list[str] = ["## Consultation Summary\n"]

        # Visit overview
        parts = []
        if data.get("record_date"):
            parts.append(f"**Date:** {data['record_date']}")
        if data.get("record_time"):
            parts.append(f"**Time:** {data['record_time']}")
        if data.get("provider_name"):
            parts.append(f"**Provider:** {data['provider_name']}")
        if data.get("chief_complaint"):
            parts.append(f"**Chief Complaint:** {data['chief_complaint']}")
        if parts:
            lines.append("\n".join(parts))

        # Diagnosis
        if data.get("diagnosis"):
            lines.append(f"\n### Diagnosis\n{data['diagnosis']}")
        if data.get("existing_conditions"):
            lines.append(f"\n### Existing Conditions\n{data['existing_conditions']}")

        # Lab results table
        lab_tests = data.get("lab_tests")
        if lab_tests and isinstance(lab_tests, list):
            lines.append("\n### Lab Results\n")
            lines.append("| Test | Result | Reference | Status |")
            lines.append("|------|--------|-----------|--------|")
            for lt in lab_tests:
                lines.append(
                    f"| {lt.get('test_name', '')} "
                    f"| {lt.get('result', '')} {lt.get('units', '')} "
                    f"| {lt.get('ref_value', '')} "
                    f"| {lt.get('note', '')} |"
                )

        # Prescriptions table
        prescriptions = data.get("prescriptions")
        if prescriptions and isinstance(prescriptions, list):
            lines.append("\n### Prescribed Medications\n")
            lines.append("| Medicine | Dosage | Timing | Duration | Notes |")
            lines.append("|----------|--------|--------|----------|-------|")
            for rx in prescriptions:
                lines.append(
                    f"| {rx.get('type', '')} {rx.get('medicine', '')} "
                    f"| {rx.get('dosage', '')} "
                    f"| {rx.get('timing', '')} "
                    f"| {rx.get('duration', '')} "
                    f"| {rx.get('note', '')} |"
                )

        # Clinical notes
        if data.get("clinical_data"):
            lines.append(f"\n### Notes\n{data['clinical_data']}")

        # Follow-up
        followup_parts = []
        if data.get("next_review_date"):
            followup_parts.append(f"**Next Review:** {data['next_review_date']}")
        if data.get("investigations"):
            followup_parts.append(f"**Investigations:** {data['investigations']}")
        if followup_parts:
            lines.append("\n### Follow-up\n" + "\n".join(followup_parts))

        return "\n".join(lines)

    # ---- Provider methods (delegate to providers/) ----

    async def _call_ollama_text(self, prompt: str) -> str | None:
        from app.services.ai.providers.ollama import call_ollama_text
        return await call_ollama_text(prompt)

    async def _call_gemini_text(self, prompt: str) -> str | None:
        from app.services.ai.providers.gemini import call_gemini_text
        return await call_gemini_text(prompt)

    async def _call_openai_text(self, prompt: str) -> str | None:
        from app.services.ai.providers.openai import call_openai_text
        return await call_openai_text(prompt)

    async def _call_groq_text(self, prompt: str) -> str | None:
        from app.services.ai.providers.groq import call_groq_text
        return await call_groq_text(prompt)

    async def _call_openrouter_text(self, prompt: str) -> str | None:
        from app.services.ai.providers.openrouter import call_openrouter_text
        return await call_openrouter_text(prompt)

    async def _ollama_chat(self, model: str, prompt: str) -> str | None:
        from app.services.ai.providers.ollama import ollama_chat
        return await ollama_chat(model, prompt)

    async def _ollama_chat_stream(self, model: str, prompt: str) -> AsyncGenerator[str, None]:
        from app.services.ai.providers.ollama import ollama_chat_stream
        async for chunk in ollama_chat_stream(model, prompt):
            yield chunk

    # ---- Internal AI call routing ----

    async def _call_ai(self, prompt: str, context: str) -> tuple[str, str]:
        """Call AI provider with failover chain — Ollama first, cloud as fallback."""
        system_note = _CLINICAL_SYSTEM_NOTE.format(today=self._fmt_date(date.today()))
        full_prompt = f"{system_note}{context}\n\nUser: {prompt}\n\nAssistant:" if context else prompt

        providers = [
            (self._call_ollama_text, "Ollama (local)"),
            (self._call_openrouter_text, "OpenRouter DeepSeek V4 Flash"),
            (self._call_groq_text, "Groq Llama-4-Scout"),
            (self._call_gemini_text, "Google Gemini 2.5 Flash"),
        ]
        for provider_fn, label in providers:
            try:
                result = await provider_fn(full_prompt)
                if result:
                    logger.info("AI text call succeeded via %s", label)
                    return result, label
            except Exception as exc:
                logger.warning("Provider %s failed: %s", label, exc)
                continue
        raise ValueError("All AI providers failed")

    async def _call_ai_excluding(
        self, prompt: str, exclude_provider: str
    ) -> tuple[str, str]:
        """Call AI provider with failover, skipping the excluded provider."""
        providers = [
            (self._call_ollama_text, "Ollama (local)"),
            (self._call_openrouter_text, "OpenRouter DeepSeek V4 Flash"),
            (self._call_groq_text, "Groq Llama-4-Scout"),
            (self._call_gemini_text, "Google Gemini 2.5 Flash"),
            (self._call_ollama_text, "Ollama (local)"),
        ]
        for provider_fn, label in providers:
            if label == exclude_provider:
                continue
            try:
                result = await provider_fn(prompt)
                if result:
                    logger.info("Verification AI call succeeded via %s", label)
                    return result, label
            except Exception as exc:
                logger.warning("Verification provider %s failed: %s", label, exc)
                continue
        raise ValueError("All verification providers failed")

    async def _call_ollama_insight(self, prompt: str, context: str) -> tuple[str, str]:
        """Generate insight — Ollama first, cloud providers as fallback."""
        system_note = _CLINICAL_SYSTEM_NOTE.format(today=self._fmt_date(date.today()))
        full_prompt = f"{system_note}{context}\n\nUser: {prompt}\n\nAssistant:" if context else prompt

        # Primary: Ollama models (local first for privacy and speed)
        ollama_models = [(settings.OLLAMA_MODEL, f"Ollama {settings.OLLAMA_MODEL}")]
        if settings.OLLAMA_TEXT_MODEL != settings.OLLAMA_MODEL:
            ollama_models.append((settings.OLLAMA_TEXT_MODEL, f"Ollama {settings.OLLAMA_TEXT_MODEL}"))
        for model, label in ollama_models:
            try:
                result = await self._ollama_chat(model, full_prompt)
                if result:
                    return result, label
            except Exception as exc:
                logger.debug("Ollama model %s failed: %s", label, exc)

        # Fallback: cloud providers
        cloud_providers: list[tuple] = []
        if settings.OPENROUTER_API_KEY:
            cloud_providers.append((self._call_openrouter_text, "OpenRouter DeepSeek V4 Flash"))
        if settings.GROQ_API_KEY:
            cloud_providers.append((self._call_groq_text, "Groq Llama-4-Scout"))
        if settings.GEMINI_API_KEY:
            cloud_providers.append((self._call_gemini_text, "Google Gemini 2.5 Flash"))

        if cloud_providers:
            try:
                result, provider = await self._race_providers(full_prompt, cloud_providers)
                if result:
                    return result, provider
            except Exception as exc:
                logger.debug("All cloud providers failed for insight: %s", exc)

        raise ValueError("All AI providers failed for insight generation")

    async def _race_providers(
        self, prompt: str, providers: list[tuple]
    ) -> tuple[str, str]:
        """Race multiple providers in parallel -- return the first successful result."""
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
                        for t in pending:
                            t.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        logger.info("Insight race won by %s", label)
                        return result, label
                except Exception as exc:
                    errors.append(exc)
                    logger.debug("Provider %s failed in race: %s", label, exc)

        raise ValueError(f"All providers failed: {[str(e)[:80] for e in errors]}")

    # ---- Context builder delegation ----

    async def _build_member_context(self, member_id: UUID, comprehensive: bool = False) -> str:
        from app.services.ai.context_builder import build_member_context, fmt_date
        return await build_member_context(self.db, member_id, fmt_date, comprehensive=comprehensive)

    async def _build_medication_summary(self, member_id: UUID) -> str:
        from app.services.ai.context_builder import build_medication_summary
        return await build_medication_summary(self.db, member_id)

    async def _build_household_context(self, household_id: UUID) -> str:
        from app.services.ai.context_builder import build_household_context, fmt_date
        return await build_household_context(self.db, household_id, fmt_date)

    async def _build_record_context(self, record_id: UUID) -> str:
        from app.services.ai.context_builder import build_record_context, fmt_date
        return await build_record_context(self.db, record_id, fmt_date)

    async def _get_conversation_history(self, conversation_id: UUID, limit: int = 10) -> str:
        from app.services.ai.chat_assistant import _get_conversation_history
        return await _get_conversation_history(self.db, conversation_id, limit)
