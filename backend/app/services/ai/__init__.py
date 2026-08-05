"""AI service package -- AIService facade that delegates to sub-modules.

Public API is identical to the original monolithic ai_service.py.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Callable
from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.base import AIInsight, Message, MessageRole
from app.schemas.ai_provider_config import AIProviderConfig, ProviderConfigItem, ordered_providers

if TYPE_CHECKING:
    from app.services.ai.task_router import TaskType

settings = get_settings()
logger = logging.getLogger(__name__)

# Extraction result cache: identical file bytes yield identical extracted
# fields, so a re-upload or duplicate file is served instantly instead of
# re-running OCR + the LLM pass. Bump EXTRACTION_CACHE_VERSION to invalidate
# every cached extraction whenever the prompt or extraction logic changes.
EXTRACTION_CACHE_TTL = 604800  # seconds (7 days) — fingerprint already busts on model/prompt change
# Short TTL for NEGATIVE caching (extraction produced no usable data). Skips
# re-running the LLM on a re-uploaded non-medical file or a retry, but bounded
# so a just-fixed provider key isn't hidden behind a stale "empty" entry.
EXTRACTION_NEGATIVE_CACHE_TTL = 600  # seconds (10 minutes)
# Bumped 2 → 3: think-tag stripping + lenient parsing + /no_think change the
# extracted output, and previously-cached blank results must be discarded.
# Bumped 4 → 5: prompt hash added to cache key; old entries miss and re-extract.
EXTRACTION_CACHE_VERSION = "5"


def _record_extraction_metric(**fields: object) -> None:
    """Best-effort tap into the per-extraction metrics ring buffer.

    Wraps :func:`extraction_metrics.record_extraction` so a failure here (e.g.
    the module being unavailable) can never break extraction. Keeps the call
    sites one-liners.
    """
    try:
        from app.services.ai.extraction_metrics import record_extraction

        record_extraction(**fields)
    except Exception:  # noqa: BLE001 — metrics are best-effort
        pass


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
    _cloud_client: httpx.AsyncClient | None = None
    _ollama_client: httpx.AsyncClient | None = None
    _client_lock: asyncio.Lock | None = None

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
    def _fmt_date(d: object) -> str:
        from app.services.ai.context_builder import fmt_date

        return fmt_date(d)

    # ---- Constructor ----

    def __init__(self, db: AsyncSession, household_id: UUID | None = None):
        self.db = db
        self.household_id = household_id
        self.last_provider: str = ""
        self._last_provider_ref: list[str] = [""]
        self._provider_config: "AIProviderConfig | None" = None
        # Per-member cloud-AI consent. When False, all cloud providers are
        # dropped from the chain so that member's PHI stays local (Ollama only).
        # Set per call via :meth:`set_cloud_consent` from the member-level
        # routers. Defaults True (legacy behaviour) so existing installs are
        # unchanged until a member explicitly opts out.
        self.cloud_ai_consent: bool = True

    def set_cloud_consent(self, consent: bool) -> "AIService":
        """Restrict this service to local-only when the member opted out of cloud AI.

        Returns ``self`` so the routers can chain it off the constructor.
        """
        self.cloud_ai_consent = bool(consent)
        return self

    # ---- Insight generation (kept inline for test patching) ----

    async def generate_insight(
        self,
        prompt: str,
        health_record_id: UUID | None = None,
        conversation_id: UUID | None = None,
        member_id: UUID | None = None,
        comprehensive: bool = False,
        mode: str = "comprehensive",
    ) -> AIInsight:
        """Generate AI insight via the configured provider chain (cloud-first when
        a cloud key is set, else local Ollama; the other group is fallback).

        ``mode`` ("comprehensive" | "brief") sets the local Ollama ``num_predict``
        cap (4096 / 1400) so a brief report generates ~2x faster on local hardware.
        """
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

        num_predict = 1400 if mode == "brief" else 4096
        response, provider = await self._call_ollama_insight(prompt, context, num_predict)

        sources_json, freshness_as_of, range_start = await self._provenance_for(
            member_id, comprehensive
        )
        insight = AIInsight(
            health_record_id=health_record_id,
            conversation_id=conversation_id,
            prompt=prompt,
            response=response,
            provider_used=provider,
            sources_json=sources_json,
            freshness_as_of=freshness_as_of,
            range_start=range_start,
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
        postprocess: Callable[[str, AIInsight], dict | None] | None = None,
        mode: str = "comprehensive",
    ) -> AsyncGenerator[str, None]:
        """Generate AI insight with SSE progress events."""
        from app.services.ai import base as _base

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

        # Stage 2: Generate — primary group first (cloud or local), other as fallback
        from app.schemas.ai_provider_config import PROVIDER_LABELS

        system_note = _CLINICAL_SYSTEM_NOTE.format(today=self._fmt_date(date.today()))
        full_prompt = (
            f"{system_note}{context}\n\nUser: {prompt}\n\nAssistant:" if context else prompt
        )

        # Brief mode caps output (~2x faster on local Ollama); comprehensive uses
        # the provider default (4096).
        num_predict = 1400 if mode == "brief" else 4096

        full_response = ""
        provider = ""

        config = await self._get_provider_config()

        # Local: Ollama models (streaming)
        ollama_cfg = next((p for p in config.providers if p.id == "ollama"), None)
        ollama_model = (
            ollama_cfg.model if ollama_cfg and ollama_cfg.model else settings.OLLAMA_MODEL
        )
        ollama_models = [(ollama_model, f"Ollama {ollama_model}")]
        if settings.OLLAMA_TEXT_MODEL != ollama_model:
            ollama_models.append(
                (settings.OLLAMA_TEXT_MODEL, f"Ollama {settings.OLLAMA_TEXT_MODEL}")
            )

        # Cloud: household-configured providers (array order preserved)
        cloud_providers: list[tuple] = []
        for prov in config.providers:
            if not prov.enabled or prov.id == "ollama":
                continue
            provider_fn = self._get_provider_fn(prov.id)
            if not provider_fn:
                continue
            label = f"{PROVIDER_LABELS.get(prov.id, prov.id)} ({prov.model})"
            cloud_providers.append((provider_fn, label, prov.model))

        # Per-member cloud-AI consent: opted-out members never egress to a cloud
        # provider — drop the cloud chain so only local Ollama is used.
        if not self.cloud_ai_consent:
            cloud_providers = []

        from app.services.ai.task_router import TaskType

        # Pre-call routing: try the cheapest capable cloud model first (the
        # configured order remains as failover). No escalation for streaming.
        cloud_providers = await self._routed_cloud_first(
            TaskType.REPORT_INSIGHT, cloud_providers
        )

        async def local_phase() -> AsyncGenerator[str, None]:
            nonlocal full_response, provider
            for model, label in ollama_models:
                try:
                    yield sse({"stage": "provider", "provider": label})
                    chunks = []
                    async for kind, payload in _base.stream_with_heartbeat(
                        self._ollama_chat_stream(model, full_prompt, num_predict)
                    ):
                        if kind == "beat":
                            yield sse({"stage": "ping"})
                        elif kind == "chunk" and isinstance(payload, str):
                            chunks.append(payload)
                            yield sse({"stage": "token", "content": payload})
                        elif kind == "error" and isinstance(payload, BaseException):
                            raise payload
                    result = "".join(chunks)
                    if result:
                        full_response = result
                        provider = label
                        return
                except Exception as exc:
                    logger.warning(
                        "Ollama streaming model %s failed: %s", label, _base.exc_description(exc)
                    )

        async def cloud_phase() -> AsyncGenerator[str, None]:
            nonlocal full_response, provider
            if full_response or not cloud_providers:
                return
            yield sse({"stage": "provider", "provider": "Cloud AI"})
            result = await self._call_cloud_sequential(full_prompt, cloud_providers)
            if result:
                resp, prov = result
                full_response = resp
                provider = prov
                for i in range(0, len(resp), 40):
                    yield sse({"stage": "token", "content": resp[i : i + 40]})

        # Primary group first, the other as automatic fallback.
        phases = (
            [cloud_phase, local_phase]
            if config.primary_provider == "cloud"
            else [local_phase, cloud_phase]
        )
        for phase_fn in phases:
            async for event in phase_fn():
                yield event
            if full_response:
                break

        # Strip residual qwen3 <think> tags / code fences from the final response
        # before persist + postprocess. Belt-and-suspenders with think:False: if
        # reasoning still leaks through, it can't corrupt the stored insight or
        # the Smart-Report JSON parse. Lazy import avoids a module-load cycle.
        if full_response:
            from app.services.ai.document_extractor import strip_llm_noise

            full_response = strip_llm_noise(full_response)

        # Stage 3: Save
        yield sse({"stage": "context", "message": "Saving insight..."})
        sources_json, freshness_as_of, range_start = await self._provenance_for(
            member_id, comprehensive
        )
        insight = AIInsight(
            health_record_id=health_record_id,
            conversation_id=conversation_id,
            prompt=prompt,
            response=full_response,
            provider_used=provider,
            sources_json=sources_json,
            freshness_as_of=freshness_as_of,
            range_start=range_start,
        )
        self.db.add(insight)
        await self.db.flush()

        # Synchronous second-model validation: resolve before the complete frame
        # so the verification status ships with the finished insight (never
        # 'pending'); falls back to fire-and-forget when synchronous mode is off.
        try:
            from app.services.insight_service import verify_insight_inline

            await verify_insight_inline(self.db, self, insight, context, member_id)
        except Exception:
            logger.debug("Streaming insight verification skipped")

        complete_event: dict = {
            "stage": "complete",
            "insight_id": str(insight.id),
            "provider": provider,
            "verification": {
                "status": insight.verification_status,
                "claims_checked": insight.verification_claims_checked,
                "verifier_provider": insight.verification_verifier,
                "summary": insight.verification_summary,
                "warnings": json.loads(insight.verification_warnings_json)
                if insight.verification_warnings_json
                else None,
                "verified_at": insight.verification_at.isoformat()
                if insight.verification_at
                else None,
            },
        }
        if member_id:
            complete_event["member_id"] = str(member_id)
        # Let a caller (e.g. the Smart Report router) enrich the final frame
        # with a parsed payload. Race-free: the data ships in the same SSE
        # frame as the completion signal, so no second round-trip is needed.
        if postprocess is not None:
            try:
                extra = postprocess(full_response, insight)
                if extra:
                    complete_event.update(extra)
            except Exception as exc:  # never block the complete event
                logger.warning("Insight stream postprocess failed: %s", exc)
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
        from app.services.ai import base as _base

        def sse(data: dict) -> str:
            return json.dumps(data)

        user_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=user_message,
        )
        self.db.add(user_msg)
        await self.db.flush()

        yield sse(
            {
                "stage": "user_message",
                "id": str(user_msg.id),
                "content": user_message,
                "created_at": user_msg.created_at.isoformat(),
            }
        )

        health_context = ""
        if member_id:
            cache_key = str(member_id)
            if not self._get_cache(cache_key):
                yield sse({"stage": "context", "message": "Loading health context..."})
                self._put_cache(
                    cache_key, await self._build_member_context(member_id, comprehensive=True)
                )
            health_context = self._get_cache(cache_key) or ""
        elif household_id:
            cache_key = f"hh:{household_id}"
            if not self._get_cache(cache_key):
                yield sse({"stage": "context", "message": "Loading health context..."})
                self._put_cache(cache_key, await self._build_household_context(household_id))
            health_context = self._get_cache(cache_key) or ""

        history = await self._get_conversation_history(conversation_id, limit=10)
        full_context = f"{health_context}\n{history}" if health_context else history

        system_note = _CLINICAL_SYSTEM_NOTE.format(today=self._fmt_date(date.today()))
        full_prompt = (
            f"{system_note}{full_context}\n\nUser: {user_message}\n\nAssistant:"
            if full_context
            else user_message
        )

        full_response = ""
        provider = ""

        config = await self._get_provider_config()
        from app.schemas.ai_provider_config import PROVIDER_LABELS

        # Local: Ollama models (streaming) — use configured model
        ollama_cfg = next((p for p in config.providers if p.id == "ollama"), None)
        ollama_model = (
            ollama_cfg.model if ollama_cfg and ollama_cfg.model else settings.OLLAMA_MODEL
        )
        ollama_models = [(ollama_model, f"Ollama {ollama_model}")]
        if settings.OLLAMA_TEXT_MODEL != ollama_model:
            ollama_models.append(
                (settings.OLLAMA_TEXT_MODEL, f"Ollama {settings.OLLAMA_TEXT_MODEL}")
            )

        # Cloud: configured providers in the user-defined fallback order.
        cloud_providers: list[tuple] = []
        for prov in config.providers:
            if not prov.enabled or prov.id == "ollama":
                continue
            provider_fn = self._get_provider_fn(prov.id)
            if not provider_fn:
                continue
            label = f"{PROVIDER_LABELS.get(prov.id, prov.id)} ({prov.model})"
            cloud_providers.append((provider_fn, label, prov.model))

        # Per-member cloud-AI consent: opted-out members never egress to a cloud
        # provider — drop the cloud chain so only local Ollama is used.
        if not self.cloud_ai_consent:
            cloud_providers = []

        from app.services.ai.task_router import TaskType

        cloud_providers = await self._routed_cloud_first(TaskType.CHAT, cloud_providers)

        async def local_phase() -> AsyncGenerator[str, None]:
            nonlocal full_response, provider
            for model, label in ollama_models:
                try:
                    yield sse({"stage": "provider", "provider": label})
                    chunks = []
                    async for kind, payload in _base.stream_with_heartbeat(
                        self._ollama_chat_stream(model, full_prompt)
                    ):
                        if kind == "beat":
                            yield sse({"stage": "ping"})
                        elif kind == "chunk" and isinstance(payload, str):
                            chunks.append(payload)
                            yield sse({"stage": "token", "content": payload})
                        elif kind == "error" and isinstance(payload, BaseException):
                            raise payload
                    result = "".join(chunks)
                    if result:
                        full_response = result
                        provider = label
                        return
                except Exception as exc:
                    logger.warning(
                        "Ollama streaming model %s failed: %s", label, _base.exc_description(exc)
                    )

        async def cloud_phase() -> AsyncGenerator[str, None]:
            nonlocal full_response, provider
            if full_response or not cloud_providers:
                return
            yield sse({"stage": "provider", "provider": "Cloud AI"})
            result = await self._call_cloud_sequential(full_prompt, cloud_providers)
            if result:
                resp, prov = result
                full_response = resp
                provider = prov
                yield sse({"stage": "token", "content": resp})

        # Primary group first, the other as automatic fallback — mirrors
        # generate_insight_stream so chat respects the cloud/local setting
        # (and the resolved "auto" primary).
        phases = (
            [cloud_phase, local_phase]
            if config.primary_provider == "cloud"
            else [local_phase, cloud_phase]
        )
        for phase_fn in phases:
            async for event in phase_fn():
                yield event
            if full_response:
                break

        # Strip residual qwen3 <think> tags / fences before persisting the
        # assistant message (belt-and-suspenders with think:False).
        if full_response:
            from app.services.ai.document_extractor import strip_llm_noise

            full_response = strip_llm_noise(full_response)

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

        # Synchronous second-model validation: resolve before the complete frame
        # so the verification status ships with the answer (never pending). The
        # conversations router fires the async fallback when this is off.
        verification_payload: dict | None = None
        if (
            settings.AI_VERIFICATION_ENABLED
            and settings.AI_VERIFICATION_SYNCHRONOUS
            and health_context
        ):
            try:
                from app.services.verification_service import VerificationService

                verification = await VerificationService(self.db, self).verify(
                    question=user_message,
                    ai_response=full_response,
                    health_context=health_context,
                    original_provider=provider,
                    message_id=assistant_msg.id,
                )
                verification_payload = {
                    "status": verification.status,
                    "claims_checked": verification.claims_checked,
                    "verifier_provider": verification.verifier_provider,
                    "summary": verification.summary,
                    "warnings": json.loads(verification.warnings_json)
                    if verification.warnings_json
                    else None,
                }
            except Exception as exc:
                logger.warning("Inline chat verification failed: %s", exc)

        complete_frame = {
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
        }
        if verification_payload is not None:
            complete_frame["verification"] = verification_payload
        yield sse(complete_frame)

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
                self._put_cache(
                    cache_key, await self._build_member_context(member_id, comprehensive=True)
                )
            health_context = self._get_cache(cache_key) or ""
        elif household_id:
            cache_key = f"hh:{household_id}"
            if not self._get_cache(cache_key):
                self._put_cache(cache_key, await self._build_household_context(household_id))
            health_context = self._get_cache(cache_key) or ""

        full_context = f"{health_context}\n{history}" if health_context else history

        from app.services.ai.task_router import TaskType

        response_text, provider = await self._call_ai(
            user_message, full_context, task=TaskType.CHAT
        )

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

    async def extract_medical_data(
        self,
        file_path: str,
        mime_type: str,
        content_hash: str | None = None,
        on_progress: Callable[[str, float], None] | None = None,
    ):
        """Extract structured medical data from a document file via vision AI.

        When *content_hash* is supplied, results are cached by content + the
        provider plan + version so re-uploads or duplicate files are extracted
        instantly instead of re-running OCR + the LLM pass. The provider-plan
        fingerprint invalidates stale entries when the user reorders providers,
        changes a model, or flips the primary group — otherwise a cache hit
        would silently return a result produced by a different provider.

        ``on_progress(detail, pct)`` is invoked at stage transitions (OCR,
        per-chunk, vision batch, transcription) so an SSE caller can stream
        finer-grained progress to the UI. It must never raise — extraction
        wraps each call.
        """
        from app.services.ai.document_extractor import (
            EXTRACTION_PROMPT_HASH,
            ExtractionProviderPlan,
            ExtractionResult,
            extract_medical_data as _extract,
        )
        from app.core.cache import cache

        started = time.monotonic()
        config = await self._get_provider_config()
        # Task-aware routing: image/pdf -> vision extraction, else text. Difficulty
        # defaults to "normal" and is memoized per content so an escalated
        # re-extract sticks (the same doc routes straight to the stronger model).
        from app.services.ai.document_extractor import extraction_confidence
        from app.services.ai.task_router import (
            TaskType,
            difficulty_for,
            next_difficulty,
            record_escalation,
            should_escalate,
        )

        is_vision = bool(mime_type) and (mime_type.startswith("image/") or "pdf" in mime_type)
        task = TaskType.EXTRACTION_VISION if is_vision else TaskType.EXTRACTION_TEXT
        route_key = content_hash or file_path
        difficulty = difficulty_for(task, route_key, "normal")
        plan = await ExtractionProviderPlan.from_config_for_task(task, difficulty, config)
        # Drop providers a recent pre-flight health probe confirmed dead so the
        # sequential failover doesn't pay the 15s dead-key tax on each. No-op
        # (returns the same plan) when no probe has populated the cache.
        pruned_plan = plan.prune_known_dead()
        providers_were_pruned = pruned_plan is not plan
        plan = pruned_plan

        cache_hit = False
        if content_hash:
            key = (
                f"extraction:{content_hash}:{plan.cache_fingerprint()}"
                f":{EXTRACTION_CACHE_VERSION}:{EXTRACTION_PROMPT_HASH}"
            )
            try:
                cached = await cache.get_async(key)
            except Exception:
                cached = None
            if isinstance(cached, dict):
                try:
                    from app.schemas.health_record import ExtractedFields

                    cache_hit = True
                    cached_result = ExtractionResult(
                        extracted=ExtractedFields.model_validate_json(cached["extracted_json"]),
                        transcription=cached.get("transcription"),
                    )
                    _record_extraction_metric(
                        mime=mime_type,
                        provider="-",
                        cache_hit=True,
                        had_data=cached_result.extracted.has_any_data(),
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                    )
                    return cached_result
                except Exception as exc:
                    logger.warning("Extraction cache parse failed — re-extracting: %s", exc)

        result = await _extract(
            self.db,
            file_path,
            mime_type,
            self._last_provider_ref,
            plan=plan,
            on_progress=on_progress,
        )

        # Escalate once on low confidence: re-extract at a higher tier and
        # memoize, so this content routes directly to the stronger model next
        # time. Only when there IS data to re-check — escalating an empty
        # (no-data) result is pointless. Cost guardrail: one bump, ≤ task ceiling.
        if result.extracted.has_any_data() and should_escalate(
            task, extraction_confidence(result.extracted)
        ):
            bumped = next_difficulty(difficulty)
            if bumped != difficulty:
                record_escalation(task, route_key, bumped)
                esc_plan = (
                    await ExtractionProviderPlan.from_config_for_task(task, bumped, config)
                ).prune_known_dead()
                try:
                    result = await _extract(
                        self.db,
                        file_path,
                        mime_type,
                        self._last_provider_ref,
                        plan=esc_plan,
                        on_progress=on_progress,
                    )
                    plan = esc_plan  # cache write uses the escalated fingerprint
                except Exception as exc:
                    logger.warning("Escalated re-extraction failed; keeping first result: %s", exc)

        had_data = result.extracted.has_any_data()
        # Cache when we have a content hash. Positive results use the long TTL.
        # No-data results are negative-cached with a SHORT TTL — but ONLY when no
        # providers were pruned: an empty result alongside a dead key may be a
        # transient failure, and caching it would hide a just-fixed key.
        if content_hash:
            key = (
                f"extraction:{content_hash}:{plan.cache_fingerprint()}"
                f":{EXTRACTION_CACHE_VERSION}:{EXTRACTION_PROMPT_HASH}"
            )
            try:
                if had_data:
                    await cache.set_async(
                        key,
                        {
                            "extracted_json": result.extracted.model_dump_json(),
                            "transcription": result.transcription,
                        },
                        ttl=EXTRACTION_CACHE_TTL,
                    )
                elif not providers_were_pruned:
                    await cache.set_async(
                        key,
                        {
                            "extracted_json": result.extracted.model_dump_json(),
                            "transcription": result.transcription,
                            "negative": True,
                        },
                        ttl=EXTRACTION_NEGATIVE_CACHE_TTL,
                    )
            except Exception:
                pass  # non-fatal — caching failure must not break extraction

        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "extraction mime=%s provider=%s data=%s cache=%s pruned=%s elapsed_ms=%d",
            mime_type,
            self._last_provider_ref[0] or "-",
            had_data,
            "hit" if cache_hit else "miss",
            providers_were_pruned,
            elapsed_ms,
        )
        _record_extraction_metric(
            mime=mime_type,
            provider=self._last_provider_ref[0] or "-",
            cache_hit=False,
            pruned=providers_were_pruned,
            had_data=had_data,
            elapsed_ms=elapsed_ms,
        )
        return result

    async def generate_consultation_summary(self, extracted_data: dict) -> str:
        """Generate a human-readable consultation summary from extracted fields.

        Uses the AI provider failover chain. Falls back to a basic template
        if all providers fail.
        """
        from app.services.ai.prompts import load_prompt

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

        # Load prompt template (frozen-aware: prompts/ under sys._MEIPASS when
        # bundled, else repo-root prompts/).
        try:
            prompt_template = load_prompt("consultation_summary.md")
        except FileNotFoundError:
            prompt_template = (
                "Generate a clear consultation summary from this medical data.\n\n{extracted_data}"
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

    async def generate_transcription_report(
        self,
        extracted_data: dict,
        member_ctx: dict | None = None,
        provider_ctx: dict | None = None,
    ) -> tuple[str, dict | None]:
        """Generate a formal 'Medical Records Transcription Report'.

        Produces the polished, numbered-section layout (Patient Identification
        → Consultation → Treatment Plan → Diagnostic Summary → Discrepancy
        Notes) from the extracted clinical fields plus member/provider
        demographics. Uses the AI provider failover chain; falls back to a
        deterministic template (_build_template_transcription_report) if every
        provider fails, so the record always receives a report.

        Returns ``(report, verification)`` where ``verification`` is the
        second-model check result (dict) for the AI-generated report, or ``None``
        when the report came from the deterministic template / verification is
        disabled. Transcription runs as a background task, so the check always
        runs inline (not gated on ``AI_VERIFICATION_SYNCHRONOUS``).
        """
        from app.services.ai.prompts import load_prompt

        context_str = self._build_report_context(extracted_data, member_ctx, provider_ctx)
        if not context_str:
            return "", None

        # Load the transcription-report prompt template (frozen-aware).
        try:
            prompt_template = load_prompt("transcription_report.md")
        except FileNotFoundError:
            prompt_template = (
                "Produce a 'Medical Records Transcription Report' with these numbered "
                "sections in order, omitting any that have no data: 1. Patient Identification "
                "& Demographics, 2. Outpatient Consultation & Clinical Findings, 3. Treatment "
                "Plan & Medical Orders, 4. Diagnostic Summary, 5. Discrepancy & Verification "
                "Notes. Use markdown tables for medications and lab results. Return only the "
                "report.\n\n{extracted_data}"
            )

        prompt = prompt_template.replace("{extracted_data}", context_str)

        try:
            result, provider = await self._call_ai(prompt, "")
            if result:
                logger.info("Transcription report generated via %s", provider)
                report = self._strip_markdown_fences(result)
                verification = await self._verify_transcription_report(
                    report, extracted_data, provider
                )
                return report, verification
        except Exception as exc:
            logger.warning("AI transcription report failed, using template: %s", exc)

        return self._build_template_transcription_report(extracted_data, member_ctx, provider_ctx), None

    async def _verify_transcription_report(
        self, report: str, extracted_data: dict, generator_label: str
    ) -> dict | None:
        """Second-model validation for an AI transcription report (None if disabled)."""
        if not settings.AI_VERIFICATION_ENABLED:
            return None
        try:
            from app.services.verification_service import VerificationService

            return await VerificationService(self.db, self).verify_transcription(
                report, extracted_data, generator_label
            )
        except Exception as exc:
            logger.warning("Transcription verification failed: %s", exc)
            return None

    @staticmethod
    def _build_report_context(
        extracted_data: dict, member_ctx: dict | None, provider_ctx: dict | None
    ) -> str:
        """Assemble the labelled data block fed to the report prompt."""
        member_ctx = member_ctx or {}
        provider_ctx = provider_ctx or {}
        parts: list[str] = []

        demo_labels = {
            "name": "Patient Name",
            "patient_id": "Patient ID / ID No",
            "age_gender": "Age / Gender",
            "phone": "Contact No",
            "address": "Primary Address",
            "blood_group": "Blood Group",
        }
        demo = [
            f"**{lbl}:** {member_ctx[k]}" for k, lbl in demo_labels.items() if member_ctx.get(k)
        ]
        if demo:
            parts.append("PATIENT DEMOGRAPHICS\n" + "\n".join(demo))

        if provider_ctx.get("name") or provider_ctx.get("speciality"):
            prov: list[str] = []
            if provider_ctx.get("name"):
                prov.append(f"**Provider:** {provider_ctx['name']}")
            if provider_ctx.get("speciality"):
                prov.append(f"**Specialty/Qualifications:** {provider_ctx['speciality']}")
            parts.append("PROVIDER\n" + "\n".join(prov))

        field_labels = {
            "record_type": "Record Type",
            "record_date": "Visit/Document Date",
            "record_time": "Time",
            "chief_complaint": "Chief Complaint",
            "diagnosis": "Diagnosis",
            "existing_conditions": "Existing Conditions",
            "investigations": "Investigations Ordered",
            "prescription_text": "Prescription Text",
            "clinical_data": "Clinical Notes",
            "next_review_date": "Next Review Date",
        }
        clin = [
            f"**{lbl}:** {extracted_data[k]}"
            for k, lbl in field_labels.items()
            if extracted_data.get(k)
        ]
        if clin:
            parts.append("CLINICAL DATA\n" + "\n".join(clin))

        prescriptions = extracted_data.get("prescriptions")
        if isinstance(prescriptions, list) and prescriptions:
            rows = [
                f"- {rx.get('type', '')} {rx.get('medicine', '')} "
                f"{rx.get('dosage', '')} {rx.get('timing', '')} "
                f"× {rx.get('duration', '')} {rx.get('note', '')}".strip()
                for rx in prescriptions
            ]
            parts.append("PRESCRIPTIONS\n" + "\n".join(rows))

        lab_tests = extracted_data.get("lab_tests")
        if isinstance(lab_tests, list) and lab_tests:
            rows = [
                f"- {lt.get('test_name', '')}: {lt.get('result', '')} "
                f"{lt.get('units', '')} (ref: {lt.get('ref_value', '')}) "
                f"— {lt.get('note', '')}".strip()
                for lt in lab_tests
            ]
            parts.append("LAB TESTS\n" + "\n".join(rows))

        return "\n\n".join(parts)

    @staticmethod
    def _build_template_transcription_report(
        extracted_data: dict, member_ctx: dict | None, provider_ctx: dict | None
    ) -> str:
        """Deterministic fallback report (no AI) in the canonical format."""
        member_ctx = member_ctx or {}
        provider_ctx = provider_ctx or {}

        institution = provider_ctx.get("name") or "Family Health Manager"
        doc_date = extracted_data.get("record_date", "")
        lines: list[str] = [f"# {institution}", "## Medical Records Transcription Report"]
        if doc_date:
            lines.append(f"**Document Date:** {doc_date}")
        lines.append("")

        # §1 Patient Identification & Demographics
        demo: list[str] = []
        if member_ctx.get("name"):
            demo.append(f"- **Patient Name:** {member_ctx['name']}")
        if member_ctx.get("patient_id"):
            demo.append(f"- **Patient ID / ID No:** {member_ctx['patient_id']}")
        if member_ctx.get("age_gender"):
            demo.append(f"- **Age / Gender:** {member_ctx['age_gender']}")
        if doc_date:
            reg = f"- **Registration Date:** {doc_date}"
            if extracted_data.get("record_time"):
                reg += f" {extracted_data['record_time']}"
            demo.append(reg)
        if member_ctx.get("phone"):
            demo.append(f"- **Contact No:** {member_ctx['phone']}")
        if member_ctx.get("address"):
            demo.append(f"- **Primary Address:** {member_ctx['address']}")
        if demo:
            lines.append("### 1. PATIENT IDENTIFICATION & DEMOGRAPHICS")
            lines.extend(demo)
            lines.append("")

        # §2 Outpatient Consultation & Clinical Findings
        s2: list[str] = []
        prov_line = provider_ctx.get("name", "")
        if provider_ctx.get("speciality"):
            prov_line = (
                f"{prov_line}, {provider_ctx['speciality']}"
                if prov_line
                else provider_ctx["speciality"]
            )
        if prov_line:
            s2.append(f"- **Consultant Physician:** {prov_line}")
        if extracted_data.get("chief_complaint"):
            s2.append(f"- **History & Symptoms:** {extracted_data['chief_complaint']}")
        if extracted_data.get("diagnosis"):
            s2.append(f"- **Diagnosis:** {extracted_data['diagnosis']}")
        if extracted_data.get("existing_conditions"):
            s2.append(f"- **Existing Conditions:** {extracted_data['existing_conditions']}")
        if s2:
            lines.append("### 2. OUTPATIENT CONSULTATION & CLINICAL FINDINGS")
            lines.extend(s2)
            lines.append("")

        # §3 Treatment Plan & Medical Orders
        prescriptions = extracted_data.get("prescriptions")
        if isinstance(prescriptions, list) and prescriptions:
            lines.append("### 3. TREATMENT PLAN & MEDICAL ORDERS")
            lines.append("| Medication / Clinical Order | Dosage & Instructions |")
            lines.append("|---|---|")
            for rx in prescriptions:
                order = f"{rx.get('type', '')} {rx.get('medicine', '')}".strip()
                instr = " ".join(
                    str(x) for x in (rx.get("dosage"), rx.get("timing"), rx.get("duration")) if x
                ).strip()
                lines.append(f"| {order} | {instr} |")
            if extracted_data.get("next_review_date"):
                lines.append("")
                lines.append(f"- **Follow-up:** {extracted_data['next_review_date']}")
            lines.append("")

        # §4 Diagnostic Summary
        lab_tests = extracted_data.get("lab_tests")
        if isinstance(lab_tests, list) and lab_tests:
            lines.append("### 4. DIAGNOSTIC SUMMARY")
            lines.append("| Test Name | Observed Value | Unit | Normal Reference Range |")
            lines.append("|---|---|---|---|")
            for lt in lab_tests:
                lines.append(
                    f"| {lt.get('test_name', '')} | {lt.get('result', '')} "
                    f"| {lt.get('units', '')} | {lt.get('ref_value', '')} |"
                )
            lines.append("")

        if extracted_data.get("clinical_data"):
            lines.append("### Notes")
            lines.append(str(extracted_data["clinical_data"]))
            lines.append("")

        lines.append(
            "_This document serves as a verified structured transcription summary "
            "of the referenced record._"
        )
        return "\n".join(lines)

    # ---- Provider methods (delegate to providers/) ----

    async def _call_ollama_text(self, prompt: str, model: str | None = None) -> str | None:
        from app.services.ai.providers.ollama import call_ollama_text

        return await call_ollama_text(prompt, model=model)

    async def _call_gemini_text(self, prompt: str, model: str | None = None) -> str | None:
        from app.services.ai.providers.gemini import call_gemini_text

        return await call_gemini_text(prompt, model=model or "gemini-2.5-flash")

    async def _call_openai_text(self, prompt: str, model: str | None = None) -> str | None:
        from app.services.ai.providers.openai import call_openai_text

        return await call_openai_text(prompt, model=model)

    async def _call_groq_text(self, prompt: str, model: str | None = None) -> str | None:
        from app.services.ai.providers.groq import call_groq_text

        return await call_groq_text(
            prompt, model=model or "llama-3.3-70b-versatile"
        )

    async def _call_openrouter_text(self, prompt: str, model: str | None = None) -> str | None:
        from app.services.ai.providers.openrouter import call_openrouter_text

        return await call_openrouter_text(prompt, model=model or "deepseek/deepseek-v4-flash")

    async def _ollama_chat(self, model: str, prompt: str, num_predict: int = 4096) -> str | None:
        from app.services.ai.providers.ollama import ollama_chat

        return await ollama_chat(model, prompt, num_predict=num_predict)

    async def _ollama_chat_stream(
        self, model: str, prompt: str, num_predict: int = 4096
    ) -> AsyncGenerator[str, None]:
        from app.services.ai.providers.ollama import ollama_chat_stream

        async for chunk in ollama_chat_stream(model, prompt, num_predict=num_predict):
            yield chunk

    # ---- Provider config loading ----

    _PROVIDER_FN_MAP: dict[str, str] = {
        "ollama": "_call_ollama_text",
        "openrouter": "_call_openrouter_text",
        "groq": "_call_groq_text",
        "gemini": "_call_gemini_text",
        "openai": "_call_openai_text",
    }

    async def _get_provider_config(self):
        """Lazy-load provider config from household settings."""
        if self._provider_config is not None:
            return self._provider_config
        if self.household_id:
            try:
                from sqlalchemy import select
                from app.models.base import Household
                from app.schemas.household import FeatureSettings

                result = await self.db.execute(
                    select(Household).where(Household.id == self.household_id)
                )
                household = result.scalar_one_or_none()
                if household and household.settings_json:
                    data = json.loads(household.settings_json)
                    fs = FeatureSettings(**data)
                    self._provider_config = fs.ai_providers
            except Exception as exc:
                logger.warning("Failed to load provider config: %s", exc)
        if self._provider_config is None:
            from app.schemas.ai_provider_config import default_provider_config

            self._provider_config = default_provider_config()

        # Resolve "auto" primary to a concrete group now that we (async) can
        # check whether any cloud key is configured. Baked onto the cached
        # config so every downstream caller (extraction + chat/insights) and the
        # extraction cache fingerprint see the resolved order — a freshly-keyed
        # household thus becomes cloud-first with no manual Settings change.
        primary = self._provider_config.primary_provider
        if primary == "auto":
            from app.schemas.ai_provider_config import resolve_primary_provider

            resolved = await resolve_primary_provider(self._provider_config)
            if resolved != primary:
                self._provider_config = self._provider_config.model_copy(
                    update={"primary_provider": resolved}
                )
        return self._provider_config

    def _get_provider_fn(self, provider_id: str):
        """Map provider ID string to bound method."""
        method_name = self._PROVIDER_FN_MAP.get(provider_id)
        if method_name:
            return getattr(self, method_name)
        return None

    async def _routed_cloud_first(
        self, task: "TaskType", cloud_providers: list[tuple]
    ) -> list[tuple]:
        """Pre-call routing for streaming tasks: when the router is on, prepend the
        cheapest capable CLOUD model so the streaming cloud phase tries it first
        (the rest of the configured order remains as failover). Ollama is never
        prepended here — it stays the local fallback. Returns ``cloud_providers``
        unchanged when routing is off, yields nothing, or picks Ollama.
        """
        try:
            from app.services.ai.task_router import resolve_model_for_task, router_enabled

            if not router_enabled():
                return cloud_providers
            config = await self._get_provider_config()
            pick = await resolve_model_for_task(task, "normal", config)
        except Exception:
            return cloud_providers
        if not pick:
            return cloud_providers
        provider_id, model = pick
        if provider_id == "ollama":
            return cloud_providers
        fn = self._get_provider_fn(provider_id)
        if not fn:
            return cloud_providers
        from app.schemas.ai_provider_config import PROVIDER_LABELS

        label = f"{PROVIDER_LABELS.get(provider_id, provider_id)} ({model})"
        return [(fn, label, model), *cloud_providers]

    @staticmethod
    def _ordered_providers(config: AIProviderConfig) -> list[ProviderConfigItem]:
        """Order providers so the primary group (local or cloud) is tried first.

        Delegates to :func:`ordered_providers` (single source of truth shared
        with document extraction) so chat/insights and extraction can never
        apply different ordering.
        """
        return ordered_providers(config)

    # ---- Internal AI call routing ----

    async def _call_ai(
        self,
        prompt: str,
        context: str,
        task: "TaskType | None" = None,
        difficulty: str = "normal",
    ) -> tuple[str, str]:
        """Call AI provider with failover chain.

        Order and models come from the household config by default; when ``task``
        is given and ``AI_ROUTER_ENABLED``, the task router picks the cheapest
        model meeting the task's accuracy floor instead (falling back to the
        configured order if routing yields nothing). Uses the circuit breaker to
        skip recently-failed providers and the AI-response cache to reuse results.
        """
        from app.schemas.ai_provider_config import PROVIDER_LABELS
        from app.services.ai import base as _base
        from app.services.ai.base import (
            is_provider_available,
            record_provider_failure,
            record_provider_success,
        )

        # Performance: check AI response cache before calling any provider
        cached = _base.get_ai_response(prompt, context)
        if cached is not None:
            return cached

        system_note = _CLINICAL_SYSTEM_NOTE.format(today=self._fmt_date(date.today()))
        full_prompt = (
            f"{system_note}{context}\n\nUser: {prompt}\n\nAssistant:" if context else prompt
        )

        config = await self._get_provider_config()
        # Failover plan as (provider_id, model). Default = configured order; the
        # router overrides when a task is declared.
        plan: list[tuple[str, str]] = [
            (p.id, p.model) for p in self._ordered_providers(config) if p.enabled
        ]
        if task is not None:
            try:
                from app.services.ai.task_router import difficulty_for, route, router_enabled

                if router_enabled():
                    routed = await route(task, difficulty_for(task, prompt, difficulty), config)
                    if routed:
                        plan = routed
            except Exception:
                logger.debug("Task routing failed; using configured order", exc_info=True)

        for provider_id, model in plan:
            provider_fn = self._get_provider_fn(provider_id)
            if not provider_fn:
                continue
            label = f"{PROVIDER_LABELS.get(provider_id, provider_id)} ({model})"

            # Performance: skip providers whose circuit breaker is open
            if not is_provider_available(provider_id):
                logger.debug("Skipping provider %s — circuit breaker open", label)
                continue

            try:
                result = await provider_fn(full_prompt, model=model)
                if result:
                    record_provider_success(provider_id)
                    logger.debug(
                        "AI call: provider=%s prompt_chars=%d response_chars=%d",
                        label,
                        len(full_prompt),
                        len(result),
                    )
                    logger.info("AI text call succeeded via %s", label)
                    _base.put_ai_response(prompt, context, result, label)
                    return result, label
            except Exception as exc:
                record_provider_failure(provider_id)
                logger.warning("Provider %s failed: %s", label, _base.exc_description(exc))
                continue
        raise ValueError("All AI providers failed")

    async def _call_validator(
        self, prompt: str, generator_label: str
    ) -> tuple[str, str] | None:
        """Pick a second model to validate content generated by ``generator_label``.

        Honors the configured provider order but (1) never uses the same provider
        *family* as the generator (Groq never validates Groq), (2) when
        ``settings.AI_VALIDATOR_CLOUD_PREFERRED`` is set, tries local Ollama only
        after every cloud candidate — so Ollama never validates Ollama while a
        cloud option exists, and (3) when
        ``settings.AI_VALIDATOR_PREFERRED_FAMILY`` is set (default ``"gemini"``),
        tries that family first within the cloud group — so Groq-generated
        content is validated by Google even if OpenRouter/OpenAI sit earlier in
        the household's list. Returns ``(result, label)`` for the first eligible
        provider returning non-empty output, or ``None`` when no different-family
        validator is available (the caller then marks the content "unvalidated"
        instead of raising). Circuit breakers + success/failure recording apply
        per provider, same as :meth:`_call_ai`.
        """
        from app.schemas.ai_provider_config import PROVIDER_LABELS
        from app.services.ai import base as _base
        from app.services.ai.base import (
            is_provider_available,
            record_provider_failure,
            record_provider_success,
        )

        def family_of(label: str) -> str:
            """Map a provider label to its family id.

            Cloud labels are ``'<Label> (<model>)'`` (e.g. ``'Groq (x)'``); local
            Ollama labels are ``'Ollama <model>'`` (no ``'(local)'``), so match the
            ``PROVIDER_LABELS`` value first, then fall back to an ``ollama`` prefix.
            """
            if not label:
                return ""
            for pid, lbl in PROVIDER_LABELS.items():
                if label.startswith(lbl):
                    return pid
            if label.lower().startswith("ollama"):
                return "ollama"
            return ""

        generator_family = family_of(generator_label)
        preferred = getattr(settings, "AI_VALIDATOR_PREFERRED_FAMILY", "") or ""

        config = await self._get_provider_config()

        # Failover plan as (provider_id, model). When the task router is enabled,
        # VALIDATION routes via it — cheapest capable model, different family from
        # the generator, preferred family first, Ollama last (cost-ordered).
        plan: list[tuple[str, str]] = []
        try:
            from app.services.ai.task_router import TaskType as _TaskType
            from app.services.ai.task_router import route as _route
            from app.services.ai.task_router import router_enabled

            if router_enabled():
                plan = await _route(
                    _TaskType.VALIDATION,
                    "normal",
                    config,
                    exclude_family=generator_family,
                    prefer_family=preferred,
                )
        except Exception:
            logger.debug("Validator routing failed; using configured order", exc_info=True)

        if not plan:  # router off, or nothing qualified — configured order fallback
            ordered = self._ordered_providers(config)
            cloud_pref = getattr(settings, "AI_VALIDATOR_CLOUD_PREFERRED", True)

            def prefer_first(group: list) -> list:
                if not preferred:
                    return group
                return [p for p in group if p.id == preferred] + [
                    p for p in group if p.id != preferred
                ]

            groups = (
                [
                    prefer_first([p for p in ordered if p.id != "ollama"]),
                    [p for p in ordered if p.id == "ollama"],
                ]
                if cloud_pref
                else [prefer_first(list(ordered))]
            )
            for group in groups:
                for prov in group:
                    if prov.enabled and prov.id != generator_family:
                        plan.append((prov.id, prov.model))

        for provider_id, model in plan:
            provider_fn = self._get_provider_fn(provider_id)
            if not provider_fn:
                continue
            label = f"{PROVIDER_LABELS.get(provider_id, provider_id)} ({model})"
            if not is_provider_available(label):
                logger.debug("Skipping validator %s — circuit breaker open", label)
                continue
            try:
                result = await provider_fn(prompt, model=model)
                if result:
                    record_provider_success(label)
                    logger.info("Validation call succeeded via %s", label)
                    return result, label
            except Exception as exc:
                record_provider_failure(label)
                logger.warning("Validator %s failed: %s", label, _base.exc_description(exc))
                continue
        return None

    async def _call_ollama_insight(
        self, prompt: str, context: str, num_predict: int = 4096
    ) -> tuple[str, str]:
        """Generate insight — primary group first (cloud or local), other as fallback."""
        from app.schemas.ai_provider_config import PROVIDER_LABELS

        system_note = _CLINICAL_SYSTEM_NOTE.format(today=self._fmt_date(date.today()))
        full_prompt = (
            f"{system_note}{context}\n\nUser: {prompt}\n\nAssistant:" if context else prompt
        )

        config = await self._get_provider_config()

        # Local: Ollama models
        ollama_cfg = next((p for p in config.providers if p.id == "ollama"), None)
        ollama_model = (
            ollama_cfg.model if ollama_cfg and ollama_cfg.model else settings.OLLAMA_MODEL
        )
        ollama_models = [(ollama_model, f"Ollama {ollama_model}")]
        if settings.OLLAMA_TEXT_MODEL != ollama_model:
            ollama_models.append(
                (settings.OLLAMA_TEXT_MODEL, f"Ollama {settings.OLLAMA_TEXT_MODEL}")
            )

        # Cloud: household-configured providers (array order preserved)
        cloud_providers: list[tuple] = []
        for prov in config.providers:
            if not prov.enabled or prov.id == "ollama":
                continue
            provider_fn = self._get_provider_fn(prov.id)
            if not provider_fn:
                continue
            label = f"{PROVIDER_LABELS.get(prov.id, prov.id)} ({prov.model})"
            cloud_providers.append((provider_fn, label, prov.model))

        # Per-member cloud-AI consent: opted-out members never egress to a cloud
        # provider — drop the cloud chain so only local Ollama is used.
        if not self.cloud_ai_consent:
            cloud_providers = []

        from app.services.ai.task_router import TaskType

        cloud_providers = await self._routed_cloud_first(
            TaskType.REPORT_INSIGHT, cloud_providers
        )

        async def _try_local() -> tuple[str, str] | None:
            for model, label in ollama_models:
                try:
                    result = await self._ollama_chat(model, full_prompt, num_predict)
                    if result:
                        logger.debug(
                            "AI call: provider=%s prompt_chars=%d response_chars=%d",
                            label,
                            len(full_prompt),
                            len(result),
                        )
                        return result, label
                except Exception as exc:
                    logger.debug("Ollama model %s failed: %s", label, exc)
            return None

        async def _try_cloud() -> tuple[str, str] | None:
            if not cloud_providers:
                return None
            return await self._call_cloud_sequential(full_prompt, cloud_providers)

        # Primary group first, the other as fallback.
        phases = (
            [_try_cloud, _try_local]
            if config.primary_provider == "cloud"
            else [_try_local, _try_cloud]
        )
        for phase in phases:
            result = await phase()
            if result:
                return result

        raise ValueError("All AI providers failed for insight generation")

    async def _call_cloud_sequential(
        self, prompt: str, cloud_providers: list[tuple]
    ) -> tuple[str, str] | None:
        """Try cloud providers one at a time in configured order; first non-empty wins.

        Honors a household's provider order as a strict failover chain (e.g.
        Groq → Gemini → …) rather than racing them in parallel — so the chosen
        ``primary`` cloud provider is genuinely preferred, and the next is tried
        only on failure/empty. Mirrors :meth:`_call_ai` and document extraction.
        Ollama is never in this list; callers keep it as the separate local
        fallback. Each entry is ``(fn, label, model)``. Circuit breakers skip
        known-down providers; successes/failures are recorded for the breaker.
        Returns ``(result, label)`` on success, ``None`` when every entry fails.
        """
        from app.services.ai import base as _base
        from app.services.ai.base import (
            is_provider_available,
            record_provider_failure,
            record_provider_success,
        )

        for entry in cloud_providers:
            provider_fn, label = entry[0], entry[1]
            model = entry[2] if len(entry) > 2 else ""
            if not is_provider_available(label):
                logger.debug("Skipping cloud provider %s — circuit breaker open", label)
                continue
            try:
                result = await provider_fn(prompt, model=model)
                if result:
                    record_provider_success(label)
                    logger.info("Cloud call succeeded via %s", label)
                    return result, label
            except Exception as exc:
                record_provider_failure(label)
                logger.warning("Cloud provider %s failed: %s", label, _base.exc_description(exc))
                continue
        return None

    # ---- Context builder delegation ----

    async def _build_member_context(self, member_id: UUID, comprehensive: bool = False) -> str:
        from app.services.ai.context_builder import build_member_context, fmt_date

        return await build_member_context(self.db, member_id, fmt_date, comprehensive=comprehensive)

    async def _provenance_for(
        self, member_id: UUID | None, comprehensive: bool
    ) -> tuple[str | None, date | None, date | None]:
        """Server-side provenance for a member-level insight.

        Returns ``(sources_json, freshness_as_of, range_start)`` — the source
        records + date range, computed from real rows (never from LLM output).
        All ``None`` when there's no member (chat / single-record insights).
        """
        if not member_id:
            return None, None, None
        from app.services.ai.context_builder import build_member_provenance

        prov = await build_member_provenance(self.db, member_id, comprehensive=comprehensive)
        sources_json = json.dumps(prov["sources"]) if prov["sources"] else None
        return sources_json, prov["freshness_as_of"], prov["range_start"]

    async def _build_household_context(self, household_id: UUID) -> str:
        from app.services.ai.context_builder import build_household_context, fmt_date

        return await build_household_context(self.db, household_id, fmt_date)

    async def _build_record_context(self, record_id: UUID) -> str:
        from app.services.ai.context_builder import build_record_context, fmt_date

        return await build_record_context(self.db, record_id, fmt_date)

    async def _get_conversation_history(self, conversation_id: UUID, limit: int = 10) -> str:
        from app.services.ai.chat_assistant import _get_conversation_history

        return await _get_conversation_history(self.db, conversation_id, limit)
