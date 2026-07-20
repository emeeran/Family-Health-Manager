"""Document extraction — OCR, PDF handling, vision AI extraction, and parsing."""

import asyncio
import base64
import functools
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.provider_keys import any_cloud_provider_configured

# Provider callables are imported into module scope so the config-driven plan
# can resolve them by name via ``globals()`` (which also keeps
# ``patch.object(dex, "call_groq_text", ...)`` effective in tests). The text/
# vision entry points are dispatched dynamically, hence the F401 noqa markers;
# the ``*_ocr`` entry points are called directly.
from app.services.ai.providers.gemini import (  # noqa: F401
    call_gemini_ocr,
    call_gemini_text,
    call_gemini_vision,
    call_gemini_vision_multi,
)
from app.services.ai.providers.groq import (  # noqa: F401
    call_groq_text,
    call_groq_vision,
    call_groq_vision_multi,
)
from app.services.ai.providers.ollama import (  # noqa: F401
    call_ollama_ocr,
    call_ollama_text,
    call_ollama_vision,
    call_ollama_vision_multi,
)
from app.services.ai.providers.openai import (  # noqa: F401
    call_openai_text,
    call_openai_vision,
    call_openai_vision_multi,
)
from app.services.ai.providers.openrouter import (  # noqa: F401
    call_openrouter_text,
    call_openrouter_vision,
    call_openrouter_vision_multi,
)

logger = logging.getLogger(__name__)

settings = get_settings()


def _emit_progress(
    on_progress: Callable[[str, float], None] | None, detail: str, pct: float
) -> None:
    """Push a coarse stage update to an SSE caller. Must never raise."""
    if on_progress is None:
        return
    try:
        on_progress(detail, pct)
    except Exception:  # noqa: BLE001 — progress is best-effort
        logger.debug("on_progress callback raised", exc_info=True)


async def _race_providers(
    entries: "list[_ProviderEntry]", invoke, kind: str
) -> tuple[str | None, str | None]:
    """Race cloud provider entries; return ``(result, label)`` of first non-empty.

    Every entry is fired at once; the first non-empty result wins and the rest
    are cancelled. Failures/timeouts/empty returns simply don't win — the race
    keeps waiting for another entry. Returns ``(None, None)`` when no entry
    produced a non-empty result. Used only when ``EXTRACTION_RACE_PROVIDERS`` is
    on; the local Ollama entry is never raced (see :func:`_run_provider_chain`).
    """
    timeout = settings.EXTRACTION_PROVIDER_TIMEOUT

    async def _one(entry: "_ProviderEntry") -> tuple[str, str] | None:
        try:
            res = await asyncio.wait_for(invoke(entry.fn), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("%s provider %s timed out after %ds in race", kind, entry.label, timeout)
            return None
        except Exception as exc:
            logger.warning("%s provider %s failed in race: %s", kind, entry.label, exc)
            return None
        return (res, entry.label) if res else None

    tasks = [asyncio.create_task(_one(e)) for e in entries]
    winner: tuple[str, str] | None = None
    try:
        for coro in asyncio.as_completed(tasks):
            res = await coro
            if res is not None:
                winner = res
                break
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if winner:
        logger.info("%s extraction succeeded via %s (race)", kind, winner[1])
    return (winner[0], winner[1]) if winner else (None, None)


async def _run_provider_chain(
    providers: "list[_ProviderEntry]", invoke, last_provider_ref: list, kind: str
) -> str | None:
    """Try providers in priority order; first non-empty result wins.

    Each entry in ``providers`` is a :class:`_ProviderEntry` (callable + label +
    ``is_local``). Cloud providers are capped at
    ``settings.EXTRACTION_PROVIDER_TIMEOUT`` so a slow or dead key fails fast and
    the next provider is tried; the local Ollama entry (``is_local=True``) gets a
    larger but still bounded cap (``settings.EXTRACTION_LOCAL_TIMEOUT``) — as the
    last-resort fallback you want it to actually finish, but a stuck
    thinking-model generation must not be allowed to pin the CPU indefinitely.

    ``invoke(fn)`` calls the provider with the arguments appropriate to its kind
    (text takes a prompt; vision takes b64 + mime + prompt) and returns its text
    or ``None``.

    When ``settings.EXTRACTION_RACE_PROVIDERS`` is on and ≥2 cloud entries are
    present, the cloud entries are raced in parallel (fastest live key wins) and
    the local entry is then tried sequentially only if every cloud entry failed
    — racing local Ollama would pin the CPU on a generation we then cancel. Off
    by default; the pre-flight health probe already removes the dead-key tax.
    """
    if getattr(settings, "EXTRACTION_RACE_PROVIDERS", False):
        cloud = [e for e in providers if not e.is_local]
        local = [e for e in providers if e.is_local]
        if len(cloud) >= 2:
            result, label = await _race_providers(cloud, invoke, kind)
            if result:
                last_provider_ref[0] = label  # type: ignore[assignment]
                return result
            # Every cloud entry failed/empty — fall through to local (sequential).
            # If there's no local entry, ``providers`` is empty → returns None.
            providers = local

    for entry in providers:
        fn, label, is_local = entry.fn, entry.label, entry.is_local
        timeout = (
            settings.EXTRACTION_LOCAL_TIMEOUT
            if is_local
            else settings.EXTRACTION_PROVIDER_TIMEOUT
        )
        try:
            result = await asyncio.wait_for(invoke(fn), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "%s provider %s timed out after %ds — %s",
                kind,
                label,
                timeout,
                "abandoning (local fallback was last resort)"
                if is_local
                else "trying next",
            )
            continue
        except Exception as exc:
            logger.warning("%s provider %s failed: %s — trying next", kind, label, exc)
            continue
        if result:
            logger.info("%s extraction succeeded via %s", kind, label)
            last_provider_ref[0] = label
            return result
    logger.error("All %s providers failed for extraction", kind.lower())
    return None


async def _fast_cloud_text_available() -> bool:
    """True if any non-Ollama text provider has an API key configured.

    When False, local Ollama is the only viable provider. The cosmetic
    transcription-formatting call is then skipped, because the single-threaded
    Ollama server serializes requests — a second call would roughly double the
    already-large per-call latency. Raw OCR/text is used as the transcript.
    """
    return await any_cloud_provider_configured()


@dataclass
class ExtractionResult:
    """Holds both structured extraction and raw transcription."""

    extracted: "ExtractedFields"  # noqa: F821
    transcription: str | None = None


# provider_id → callable for each modality. Used to map the config-driven
# provider plan to concrete text/vision calls, so extraction honors the same
# order/models as chat & insights.
# provider_id → name of the text/vision callable in this module's namespace.
# Stored as strings (not references) so the plan resolves the (possibly
# monkeypatched) callable fresh at build time via ``globals()`` — keeping
# ``patch.object(dex, "call_groq_text", ...)`` effective in tests.
_PROVIDER_TEXT: dict[str, str] = {
    "groq": "call_groq_text",
    "openrouter": "call_openrouter_text",
    "gemini": "call_gemini_text",
    "openai": "call_openai_text",
    "ollama": "call_ollama_text",
}
_PROVIDER_VISION: dict[str, str] = {
    "groq": "call_groq_vision",
    "openrouter": "call_openrouter_vision",
    "gemini": "call_gemini_vision",
    "openai": "call_openai_vision",
    "ollama": "call_ollama_vision",
}
# Multi-image variants (one call for several pages). Same provider set; the
# registry maps to the ``*_multi`` callables. Providers that don't support
# multi-image return None, and the caller falls back to single-image per page.
_PROVIDER_VISION_MULTI: dict[str, str] = {
    "groq": "call_groq_vision_multi",
    "openrouter": "call_openrouter_vision_multi",
    "gemini": "call_gemini_vision_multi",
    "openai": "call_openai_vision_multi",
    "ollama": "call_ollama_vision_multi",
}
# Display labels for logs / last_provider_ref (capitalized, matching the
# historical chain labels so existing log scrapers and tests are unaffected).
_PROVIDER_LABEL: dict[str, str] = {
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "gemini": "Gemini",
    "openai": "OpenAI",
    "ollama": "Ollama",
}


@dataclass
class _PlanItem:
    provider_id: str
    model: str
    is_local: bool


@dataclass
class _ProviderEntry:
    """One resolved, ordered provider call for a modality.

    ``fn`` is a partial already bound with the provider's model + Gemini auth
    choice (and Ollama JSON grammar when requested), so the caller only supplies
    the prompt (text) or ``(b64, mime, prompt)`` (vision).
    """

    fn: Any
    label: str
    is_local: bool


@dataclass
class ExtractionProviderPlan:
    """Config-driven, ordered provider plan for one extraction request.

    Built once from the household ``AIProviderConfig`` (or the default config)
    and threaded through every AI call in the pipeline so document extraction
    honors the same provider order, primary group, per-provider model, and
    Gemini auth choice as chat/insights.
    """

    items: list[_PlanItem] = field(default_factory=list)
    gemini_auth: str = "auto"
    # Optional faster Ollama model applied to the TEXT-extraction entries only
    # (see OLLAMA_FAST_MODEL). Vision entries are untouched. Included in the
    # cache fingerprint so toggling it self-invalidates cached extractions.
    fast_text_model: str = ""

    @classmethod
    def from_config(cls, config: Any) -> "ExtractionProviderPlan":
        """Build a plan from an ``AIProviderConfig`` (enabled providers only).

        Falls back to the default order if every provider is disabled, so a
        misconfigured household can't fully disable extraction.
        """
        from app.schemas.ai_provider_config import default_provider_config, ordered_providers

        def _to_items(cfg: Any) -> list[_PlanItem]:
            return [
                _PlanItem(provider_id=p.id, model=p.model, is_local=(p.id == "ollama"))
                for p in ordered_providers(cfg)
                if p.enabled
            ]

        items = _to_items(config)
        if not items:
            items = _to_items(default_provider_config())
        return cls(
            items=items,
            gemini_auth=getattr(config, "gemini_auth", "auto"),
            fast_text_model=settings.OLLAMA_FAST_MODEL,
        )

    def cache_fingerprint(self) -> str:
        """Stable short hash of the ordered providers + Gemini auth + fast model.

        Embedded in the extraction cache key so reordering providers, changing a
        model, flipping the primary group, or enabling the fast text model
        invalidates stale cached results that a different provider/model produced.
        """
        import hashlib

        raw = "|".join(f"{it.provider_id}:{it.model or ''}" for it in self.items)
        raw += f"|auth={self.gemini_auth}"
        if self.fast_text_model:
            raw += f"|fast={self.fast_text_model}"
        return hashlib.md5(raw.encode()).hexdigest()[:10]

    def prune_known_dead(self) -> "ExtractionProviderPlan":
        """Return a copy with providers a recent health probe confirmed dead removed.

        Consults the negative cache in :mod:`provider_health` (populated by the
        pre-flight probe at the start of the extract endpoints, or by /ai/status).
        When the cache is empty (no probe run yet, or expired) NOTHING is pruned
        and ``self`` is returned unchanged — preserving the full chain and the
        behaviour every unit test expects.

        Never returns an empty plan: if every provider were confirmed dead the
        first item is kept so extraction still *attempts* something rather than
        silently returning empty (a half-second probe stale window shouldn't
        strand a document; the chain's own timeouts will surface the failure).
        """
        from app.services.ai.provider_health import known_dead_providers

        dead = known_dead_providers()
        if not dead:
            return self
        kept = [it for it in self.items if it.provider_id not in dead]
        if not kept:
            return self  # never empty the chain
        if len(kept) == len(self.items):
            return self
        logger.info(
            "Pruned %d confirmed-dead provider(s) from extraction chain: %s",
            len(self.items) - len(kept),
            sorted(dead & {it.provider_id for it in self.items}),
        )
        return ExtractionProviderPlan(items=kept, gemini_auth=self.gemini_auth)

    def _entry(
        self, item: _PlanItem, kind: str, json_grammar: bool
    ) -> _ProviderEntry | None:
        if kind == "text":
            table = _PROVIDER_TEXT
        elif kind == "vision_multi":
            table = _PROVIDER_VISION_MULTI
        else:
            table = _PROVIDER_VISION
        fn_name = table.get(item.provider_id)
        if not fn_name:
            return None
        # Resolve via globals() so tests that patch ``dex.call_<p>_text`` are
        # honoured (a module-level dict of captured refs would bypass the patch).
        fn = globals().get(fn_name)
        if fn is None:
            return None
        kwargs: dict[str, Any] = {}
        # Fast text model: when configured, the Ollama TEXT-extraction entry
        # uses it instead of the plan's Ollama model (clean-text path speedup).
        # Scoped to text — vision/multi entries keep the plan model so an image
        # is never fed to a text-only fast model.
        effective_model = item.model
        if (
            kind == "text"
            and item.provider_id == "ollama"
            and self.fast_text_model
        ):
            effective_model = self.fast_text_model
        if effective_model:
            kwargs["model"] = effective_model
        if item.provider_id == "gemini":
            kwargs["gemini_auth"] = self.gemini_auth
        if item.provider_id == "ollama" and json_grammar:
            kwargs["fmt"] = "json"
        bound = functools.partial(fn, **kwargs) if kwargs else fn
        label = f"{_PROVIDER_LABEL[item.provider_id]} {kind}"
        return _ProviderEntry(fn=bound, label=label, is_local=item.is_local)

    def text_entries(self, *, json_grammar: bool = False) -> list[_ProviderEntry]:
        entries = [self._entry(it, "text", json_grammar) for it in self.items]
        return [e for e in entries if e is not None]

    def vision_entries(self, *, json_grammar: bool = False) -> list[_ProviderEntry]:
        entries = [self._entry(it, "vision", json_grammar) for it in self.items]
        return [e for e in entries if e is not None]

    def vision_multi_entries(self, *, json_grammar: bool = False) -> list[_ProviderEntry]:
        """Multi-image vision entries (one call covers several pages).

        Same providers/order as :meth:`vision_entries` but resolved to the
        ``*_multi`` callables. Used to collapse per-page vision calls into one
        per batch on the scanned-PDF vision fallback.
        """
        entries = [self._entry(it, "vision_multi", json_grammar) for it in self.items]
        return [e for e in entries if e is not None]


def _load_extraction_prompt() -> str:
    """Load the extraction prompt from ``prompts/extraction.md`` (repo root).

    Externalised so prompt tuning can happen without code changes, mirroring
    ``consultation_summary.md`` / ``transcription_report.md``. Falls back to a
    minimal directive if the file is absent so extraction still runs.
    """
    prompt_path = (
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "prompts"
        / "extraction.md"
    )
    try:
        return prompt_path.read_text().strip()
    except FileNotFoundError:
        logger.warning("extraction.md not found at %s; using fallback prompt", prompt_path)
        return (
            "You are a medical document data extraction assistant. Extract "
            "record_type, record_date, provider_name, diagnosis, prescriptions, "
            "lab_tests, vitals and other structured fields. Return ONLY valid "
            "JSON with null for missing fields; always set record_type."
        )


EXTRACTION_PROMPT = _load_extraction_prompt()


def _prompt_hash() -> str:
    """Stable short hash of the extraction prompt content.

    Embedded in the extraction cache key so editing ``prompts/extraction.md``
    self-invalidates stale cached extractions without needing to manually bump
    ``EXTRACTION_CACHE_VERSION``.
    """
    import hashlib

    return hashlib.md5(EXTRACTION_PROMPT.encode()).hexdigest()[:8]


EXTRACTION_PROMPT_HASH = _prompt_hash()


async def extract_medical_data(
    db: AsyncSession,
    file_path: str,
    mime_type: str,
    last_provider_ref: list,
    plan: ExtractionProviderPlan | None = None,
    on_progress: Callable[[str, float], None] | None = None,
) -> ExtractionResult:
    """Extract structured medical data from a document file via vision AI.

    Returns an ExtractionResult containing both structured fields and the
    raw OCR/text transcription (when available).

    ``plan`` is the config-driven provider order; when omitted the default
    provider config is used (preserving the original behaviour for direct
    callers such as tests).

    ``on_progress(detail, pct)`` receives coarse stage updates (OCR, per-chunk,
    per-vision-batch, transcription) so an SSE caller can stream finer-grained
    progress than the static "extracting 50%".
    """
    from app.schemas.ai_provider_config import default_provider_config
    from app.schemas.health_record import ExtractedFields

    if plan is None:
        plan = ExtractionProviderPlan.from_config(default_provider_config())

    if mime_type == "application/pdf":
        pdf_text, page_count = extract_pdf_text(file_path)
        if pdf_text:
            logger.info(
                "PDF has embedded text (%d chars) — using fast text extraction", len(pdf_text)
            )
            _emit_progress(on_progress, "Extracting fields from embedded text", 35)
            # Extraction and transcription-formatting both consume only pdf_text —
            # run them concurrently to save an AI round-trip.
            if await _fast_cloud_text_available():
                raw_text, formatted = await asyncio.gather(
                    call_text_extraction(pdf_text, last_provider_ref, plan),
                    _format_ocr_transcription(pdf_text, last_provider_ref, plan),
                )
            else:
                # Ollama-only: skip the cosmetic transcription call (it would
                # serialize behind extraction on the single-threaded server).
                raw_text = await call_text_extraction(pdf_text, last_provider_ref, plan)
                formatted = pdf_text
            result = parse_extraction(raw_text, ExtractedFields)
            if not result.has_any_data():
                logger.warning(
                    "PDF text extraction returned no usable fields — text may be non-medical or too short"
                )
            return _heuristic_fallback(
                ExtractionResult(extracted=result, transcription=formatted),
                pdf_text,
                mime_type,
            )

        # Scanned/image PDF — OCR pages then use fast text extraction
        logger.info("PDF is scanned/image-based — attempting OCR + text extraction")

        # page_count came from extract_pdf_text's single fitz.open — no separate
        # validation open needed. page_count is None only when the file can't be
        # opened at all (extract_pdf_text caught the exception).
        if page_count is None:
            logger.error("Cannot open PDF — file may be corrupted")
            return ExtractionResult(extracted=ExtractedFields())
        if page_count == 0:
            logger.error("PDF has 0 pages — file may be corrupted or empty")
            return ExtractionResult(extracted=ExtractedFields())
        logger.info("PDF has %d pages", page_count)

        # Step 1: Render pages and OCR with tesseract (fast, local)
        _emit_progress(on_progress, f"Running OCR on {page_count} page(s)", 20)
        ocr_text, page_renders = await ocr_pdf_pages(file_path, page_count)
        ocr_quality = _ocr_quality(ocr_text)

        if ocr_text and ocr_quality >= OCR_QUALITY_THRESHOLD:
            logger.info(
                "OCR extracted %d chars (quality %.2f) from %d pages — using text extraction",
                len(ocr_text),
                ocr_quality,
                page_count,
            )
            # Chunk OCR text by page markers to keep prompts small for local
            # models. Pages-per-chunk is configurable (default 5) — larger
            # chunks mean fewer LLM calls on multi-page scans (N/5 vs the old
            # N/3), the big local-mode win for scanned PDFs. Each call is still
            # capped at 10k chars so a dense chunk can't balloon the prompt.
            page_chunks = chunk_ocr_text(
                ocr_text, pages_per_chunk=settings.EXTRACTION_PAGES_PER_CHUNK
            )
            all_extracted = ExtractedFields()
            # Overlap the cosmetic transcription-formatting call with the chunk
            # extractions so it doesn't add a sequential round-trip after them
            # (previously it ran after the gather, roughly doubling cloud OCR
            # latency). On Ollama-only there's no cloud formatting call, so this
            # stays a no-op there.
            cloud_available = await _fast_cloud_text_available()
            format_task = (
                asyncio.create_task(
                    _format_ocr_transcription(ocr_text, last_provider_ref, plan)
                )
                if cloud_available
                else None
            )
            # Process all chunks in parallel, emitting per-chunk progress as
            # each completes so a multi-page scan shows live advancement.
            # On cloud: unbounded (each chunk is an independent API call).
            # On local Ollama: bounded to 2 — Ollama serializes one generation
            # per model, so firing all chunks at once just inflates RAM with
            # zero throughput gain (mirrors BATCH_EXTRACTION_CONCURRENCY_LOCAL).
            n_chunks = len(page_chunks)
            chunk_concurrency = n_chunks if cloud_available else min(2, n_chunks)
            chunk_sem = asyncio.Semaphore(max(1, chunk_concurrency))

            async def _extract_chunk(i: int, chunk: str) -> str | None:
                async with chunk_sem:
                    res = await call_text_extraction(chunk[:10000], last_provider_ref, plan)
                    _emit_progress(
                        on_progress,
                        f"Extracting fields from page group {i + 1}/{n_chunks}",
                        30 + int(30 * (i + 1) / max(1, n_chunks)),
                    )
                    return res

            chunk_results = await asyncio.gather(
                *[_extract_chunk(i, c) for i, c in enumerate(page_chunks)]
            )
            for raw_text in chunk_results:
                chunk_result = parse_extraction(raw_text, ExtractedFields)
                all_extracted = merge_extractions(all_extracted, chunk_result)
            if all_extracted.has_any_data():
                if format_task is not None:
                    try:
                        formatted = await format_task
                    except Exception:
                        formatted = ocr_text
                else:
                    formatted = ocr_text
                return ExtractionResult(extracted=all_extracted, transcription=formatted)
            if format_task is not None and not format_task.done():
                format_task.cancel()
            logger.warning(
                "OCR text extraction returned no usable fields — falling back to vision AI"
            )
        else:
            logger.warning(
                "OCR quality too low (%.2f) or empty — falling back to vision AI", ocr_quality
            )

        # Step 2: Vision AI fallback (slow, requires working provider)
        # Reuse the page renders from OCR if available — the OCR path already
        # rendered every page at 200 DPI PNG; re-rendering the same pages at
        # 150 DPI JPEG (the old behaviour) was pure wasted CPU on every scanned
        # PDF that escalated to vision. Falls back to rendering only when OCR
        # didn't run (e.g. tesseract not installed) or produced no renders.
        if page_renders:
            # Re-encode the 200 DPI PNG renders to JPEG for compact API payloads
            # (~5× smaller); PIL is already a dependency (used by preprocessing).
            page_images = [
                base64.b64encode(_png_to_jpeg(png)).decode() for png in page_renders
            ]
            vision_mime = "image/jpeg"
            logger.info("Reusing %d OCR page renders for vision fallback", len(page_images))
        else:
            # No cached renders — render pages in parallel (bounded by
            # OCR_CONCURRENCY). Each page open is independent and thread-safe.
            _emit_progress(on_progress, f"Rendering {page_count} page(s)", 35)
            render_sem = asyncio.Semaphore(OCR_CONCURRENCY)

            async def _render_page_b64(pn: int) -> str | None:
                async with render_sem:
                    img_bytes = await asyncio.to_thread(pdf_page_to_image, file_path, pn)
                    return base64.b64encode(img_bytes).decode() if img_bytes else None

            page_images = [
                img
                for img in await asyncio.gather(
                    *[_render_page_b64(p) for p in range(page_count)]
                )
                if img
            ]
            vision_mime = "image/jpeg"  # 150 DPI JPEG for compact API payload

        if not page_images:
            logger.error(
                "PDF has %d pages but none could be rendered — file may be encrypted", page_count
            )
            return ExtractionResult(extracted=ExtractedFields())

        logger.info("Vision fallback: %d pages — extracting in parallel batches", len(page_images))

        # Kick off transcription NOW so it overlaps the extraction batches
        # (mirrors the OCR path's overlap of transcription-formatting with
        # chunk extraction). On Ollama-only it serializes behind extraction
        # anyway, so this is a no-op there.
        transcription_task = asyncio.create_task(
            _transcribe_via_vision(page_images, mime_type=vision_mime, plan=plan)
        )

        # Pack k pages into ONE multi-image vision call per batch
        # (EXTRACTION_VISION_BATCH_SIZE, default 3) instead of one call per page.
        # On a 9-page scan that's 3 calls instead of 9 — the biggest local-mode
        # win for scanned PDFs whose OCR was too poor to use the text path. If a
        # provider doesn't support multi-image (returns nothing), the batch
        # transparently falls back to one-call-per-page so no page is lost.
        #
        # Batches run in parallel on cloud (bounded) and sequentially on local
        # Ollama (it serializes one generation per model, so parallel batches
        # would only inflate RAM with zero throughput gain).
        BATCH_SIZE = max(1, settings.EXTRACTION_VISION_BATCH_SIZE)
        n_batches = max(1, (len(page_images) + BATCH_SIZE - 1) // BATCH_SIZE)
        batches = [
            page_images[s : s + BATCH_SIZE]
            for s in range(0, len(page_images), BATCH_SIZE)
        ]
        cloud_available = await _fast_cloud_text_available()
        # Cloud: run batches concurrently, capped at EXTRACTION_VISION_BATCH_CONCURRENCY
        # to avoid rate limits on providers like Groq/OpenRouter. Local: sequential
        # — Ollama serializes one generation per model, so parallel just inflates RAM.
        batch_concurrency = (
            min(len(batches), settings.EXTRACTION_VISION_BATCH_CONCURRENCY)
            if cloud_available
            else 1
        )
        batch_sem = asyncio.Semaphore(max(1, batch_concurrency))

        async def _extract_vision_batch(bi: int, batch: list[str]) -> list[str | None]:
            page_nums = list(range(bi * BATCH_SIZE + 1, bi * BATCH_SIZE + len(batch) + 1))
            logger.info("Extracting pages %s via vision AI...", ", ".join(str(p) for p in page_nums))
            _emit_progress(
                on_progress,
                f"Vision extraction batch {bi + 1}/{n_batches} (pages {page_nums[0]}–{page_nums[-1]})",
                40 + int(35 * (bi + 1) / n_batches),
            )
            async with batch_sem:
                raw_texts: list[str | None] = []
                if len(batch) > 1:
                    multi_raw = await call_vision_provider_from_b64_multi(
                        batch, vision_mime, last_provider_ref, plan
                    )
                    if multi_raw:
                        raw_texts = [multi_raw]
                if not raw_texts:
                    # Single-page batch, or multi-image unsupported by every provider.
                    raw_texts = await asyncio.gather(
                        *[
                            call_vision_provider_from_b64(b64, vision_mime, last_provider_ref, plan)
                            for b64 in batch
                        ]
                    )
                return raw_texts

        # gather preserves submission order, so batch results merge in page order.
        try:
            batch_results = await asyncio.gather(
                *[_extract_vision_batch(bi, batch) for bi, batch in enumerate(batches)]
            )
        except Exception:
            # Batch loop failed — cancel the overlapping transcription task so
            # it doesn't linger as an orphan.
            transcription_task.cancel()
            raise

        all_extracted = ExtractedFields()
        for raw_texts in batch_results:
            for raw_text in raw_texts:
                page_result = parse_extraction(raw_text, ExtractedFields)
                all_extracted = merge_extractions(all_extracted, page_result)

        # Transcription was kicked off before the batch loop — await it now.
        _emit_progress(on_progress, "Building transcription", 85)
        try:
            transcription = await transcription_task
        except Exception:
            if not transcription_task.done():
                transcription_task.cancel()
            transcription = None
        return _heuristic_fallback(
            ExtractionResult(extracted=all_extracted, transcription=transcription),
            ocr_text,
            mime_type,
        )

    if mime_type.startswith("image/"):
        # Try local tesseract first (fast, free). Offloaded to a worker thread —
        # tesseract is a blocking subprocess (+ PIL preprocess) that would
        # otherwise freeze the event loop (measured ~0.7s stall per image),
        # starving the SSE heartbeat and all concurrent requests.
        _emit_progress(on_progress, "Reading image", 20)
        ocr_text = await asyncio.to_thread(tesseract_image, file_path)
        if ocr_text and _ocr_quality(ocr_text) >= OCR_QUALITY_THRESHOLD:
            logger.info(
                "Image OCR (tesseract) extracted %d chars — using text extraction", len(ocr_text)
            )
            if await _fast_cloud_text_available():
                raw_text, formatted = await asyncio.gather(
                    call_text_extraction(ocr_text, last_provider_ref, plan),
                    _format_ocr_transcription(ocr_text, last_provider_ref, plan),
                )
            else:
                raw_text = await call_text_extraction(ocr_text, last_provider_ref, plan)
                formatted = ocr_text
            return _heuristic_fallback(
                ExtractionResult(
                    extracted=parse_extraction(raw_text, ExtractedFields),
                    transcription=formatted,
                ),
                ocr_text,
                mime_type,
            )

        # Tesseract produced nothing usable — try cloud AI OCR
        ocr_text = await call_ocr(file_path, mime_type, plan)
        if ocr_text and _ocr_quality(ocr_text) >= OCR_QUALITY_THRESHOLD:
            if await _fast_cloud_text_available():
                raw_text, formatted = await asyncio.gather(
                    call_text_extraction(ocr_text, last_provider_ref, plan),
                    _format_ocr_transcription(ocr_text, last_provider_ref, plan),
                )
            else:
                raw_text = await call_text_extraction(ocr_text, last_provider_ref, plan)
                formatted = ocr_text
            return _heuristic_fallback(
                ExtractionResult(
                    extracted=parse_extraction(raw_text, ExtractedFields),
                    transcription=formatted,
                ),
                ocr_text,
                mime_type,
            )
        # OCR failed / too low quality — fall through to vision providers

    # Vision-only path: run extraction and transcription in parallel
    file_bytes = Path(file_path).read_bytes()
    b64_data = base64.b64encode(file_bytes).decode()
    extraction_task = asyncio.create_task(
        call_vision_provider(file_path, mime_type, last_provider_ref, plan)
    )
    transcription_task = asyncio.create_task(
        _transcribe_via_vision([b64_data], mime_type, plan=plan)
    )
    raw_text, transcription = await asyncio.gather(extraction_task, transcription_task)
    return ExtractionResult(
        extracted=parse_extraction(raw_text, ExtractedFields),
        transcription=transcription,
    )


async def call_ocr(
    file_path: str, mime_type: str, plan: ExtractionProviderPlan | None = None
) -> str | None:
    """Use vision AI to OCR an image to text.

    Tries OCR-capable providers (Gemini, then Ollama) in the configured plan
    order. Only Gemini and Ollama expose a dedicated OCR call; other providers
    are skipped here. Each call is capped at ``EXTRACTION_PROVIDER_TIMEOUT``
    (cloud) or ``EXTRACTION_LOCAL_TIMEOUT`` (Ollama) so a dead/slow key fails
    fast instead of stalling indefinitely — mirroring every other AI call path.
    """
    if plan is None:
        from app.schemas.ai_provider_config import default_provider_config

        plan = ExtractionProviderPlan.from_config(default_provider_config())
    file_bytes = Path(file_path).read_bytes()
    b64_data = base64.b64encode(file_bytes).decode()

    for item in plan.items:
        is_local = item.provider_id == "ollama"
        timeout = (
            settings.EXTRACTION_LOCAL_TIMEOUT
            if is_local
            else settings.EXTRACTION_PROVIDER_TIMEOUT
        )
        try:
            if item.provider_id == "gemini":
                result = await asyncio.wait_for(
                    call_gemini_ocr(
                        b64_data,
                        mime_type,
                        model=item.model or None,
                        gemini_auth=plan.gemini_auth,
                    ),
                    timeout=timeout,
                )
            elif item.provider_id == "ollama":
                result = await asyncio.wait_for(
                    call_ollama_ocr(b64_data, mime_type), timeout=timeout
                )
            else:
                continue
        except asyncio.TimeoutError:
            logger.warning(
                "OCR provider %s timed out after %ds", item.provider_id, timeout
            )
            continue
        except Exception as exc:
            logger.warning("OCR provider %s failed: %s", item.provider_id, exc)
            continue
        if result:
            return result

    return None


def extract_pdf_text(file_path: str) -> tuple[str | None, int | None]:
    """Extract text content from a PDF file using PyMuPDF.

    Returns ``(text, page_count)`` — both derived from a single ``fitz.open``
    so the caller doesn't need a second open just to count pages. ``text`` is
    ``None`` for scanned/image PDFs (no embedded text); ``page_count`` is
    ``None`` when the file can't be opened at all.
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)
        page_count = len(doc)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return (text.strip() or None), page_count
    except Exception as exc:
        logger.warning("PDF text extraction failed: %s", exc)
        return None, None


# Month name → number, for parsing named-month dates ("02-Jun-2026", "5 June 2026").
_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

# Specific signals kept tight so a doctor's note that merely mentions a test
# isn't mis-routed to the lab-report type.
_LAB_KEYWORDS = (
    "laboratory report",
    "lab report",
    "reference range",
    "specimen",
    "test name",
    "investigation report",
    "pathology",
    "biochemistry",
    "microbiology",
    "haematology",
    "hematology",
)

# All fillable ExtractedFields names, in the gap-fill / clean passes.
_FILLABLE = (
    "record_type",
    "record_date",
    "record_time",
    "clinical_data",
    "diagnosis",
    "existing_conditions",
    "chief_complaint",
    "investigations",
    "prescription_text",
    "provider_name",
    "next_review_date",
    "prescriptions",
    "lab_tests",
    "eyeglass",
    "weight",
    "height",
    "blood_pressure",
    "heart_rate",
    "temperature",
)
_STRING_FIELDS = frozenset(
    (
        "clinical_data",
        "diagnosis",
        "existing_conditions",
        "chief_complaint",
        "investigations",
        "prescription_text",
        "provider_name",
        "weight",
        "height",
        "blood_pressure",
        "heart_rate",
        "temperature",
    )
)

# Matches a "--- Section Name ---" header line emitted by the transcription
# prompts (TRANSCRIPTION_PROMPT / FORMAT_TRANSCRIPTION_PROMPT).
_SECTION_HEADER_RE = re.compile(r"^\s*---\s+(.+?)\s*---\s*$", re.IGNORECASE | re.MULTILINE)


def _clean_markers(value: str | None) -> str | None:
    """Strip [illegible]/[...] uncertainty markers from a single value.

    Returns None when nothing readable remains (a value that was *only* markers).
    "[illegible]" / "[...]" become "?"; "(?)" is kept (it signals a soft guess).
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = re.sub(r"\[illegible\]", "?", s, flags=re.IGNORECASE)
    s = re.sub(r"\[\.\.\.\]", "?", s)
    if not re.search(r"[A-Za-z0-9]", s):
        return None
    return re.sub(r"\s+", " ", s).strip()


def _clean_transcription_display(text: str | None) -> str | None:
    """Soften '[illegible]' in the transcription shown to the user."""
    if not text:
        return text
    return re.sub(r"\[illegible\]", "(unreadable)", str(text), flags=re.IGNORECASE)


def _split_sections(text: str) -> dict[str, str]:
    """Split a ``--- Section ---``-formatted transcription into {name: body}.

    Returns {} for free-form text (no section headers). Names are lowercased.
    """
    matches = list(_SECTION_HEADER_RE.finditer(text))
    if not matches:
        return {}
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1).strip().lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


def _extract_blood_pressure(text: str | None) -> str | None:
    """Pull 'systolic/diastolic' from a vitals block; tolerate a missing half."""
    t = _clean_markers(text) or ""
    m = re.search(r"(\d{2,3})\s*/\s*(\d{2,3}|\?)", t)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.search(r"\b(?:bp|blood pressure)\b[:\s]*([8-9]\d|1\d{2}|2[0-5]\d)\b", t, re.IGNORECASE)
    return m.group(1) if m else None


def _extract_first_number(text: str | None, labels: list[str]) -> str | None:
    """First number following any label regex in a vitals block."""
    t = _clean_markers(text) or ""
    for label in labels:
        m = re.search(rf"{label}\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)", t, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _clean_extracted(extracted: "ExtractedFields") -> "ExtractedFields":  # noqa: F821
    """Return a copy with [illegible] markers cleaned from string fields (or the
    original object if nothing changed)."""
    from app.schemas.health_record import ExtractedFields

    changed = False
    values: dict[str, object] = {}
    for f in _FILLABLE:
        v = getattr(extracted, f)
        if f in _STRING_FIELDS and isinstance(v, str):
            cleaned = _clean_markers(v)
            if cleaned != v:
                changed = True
                v = cleaned
        values[f] = v
    return ExtractedFields(**values) if changed else extracted


def _fill_null_fields(
    ai: "ExtractedFields",
    heur: "ExtractedFields",  # noqa: F821
) -> tuple["ExtractedFields", bool]:  # noqa: F821
    """Copy of ``ai`` with still-empty fields filled from ``heur``.

    Never overwrites a value the AI already set. Returns (merged, changed).
    """
    from app.schemas.health_record import ExtractedFields

    changed = False
    values: dict[str, object] = {}
    for f in _FILLABLE:
        ai_val = getattr(ai, f)
        if ai_val in (None, "", []):
            heur_val = getattr(heur, f)
            if heur_val not in (None, "", []):
                values[f] = heur_val
                changed = True
                continue
        values[f] = ai_val
    return ExtractedFields(**values), changed


def heuristic_extract(text: str | None, mime_type: str = "application/pdf") -> "ExtractedFields":
    """Deterministic gap-filler that extracts fields from OCR/transcription text.

    Used as a backfill when AI structured extraction leaves fields empty (common
    on CPU-only local models). Parses both free text and the ``--- section ---``
    transcription format produced by the vision/OCR transcription prompts, so a
    readable transcription yields record_type, diagnosis, chief complaint,
    vitals, etc. even when the AI's structured JSON pass was weak. All values are
    cleaned of ``[illegible]`` markers. Never invents a date: ambiguous numeric
    dates (day and month both ≤ 12) and DOB/birth-line dates are refused.

    ``mime_type`` is accepted for signature symmetry with the AI path but does
    not change the heuristics.
    """
    from app.models.base import RecordType
    from app.schemas.health_record import ExtractedFields

    if not text or not str(text).strip():
        return ExtractedFields()

    raw = str(text)
    fields = ExtractedFields()
    sections = _split_sections(raw)
    lowered = raw.lower()

    # Always carry the raw text through so the form is auto-filled rather than
    # left blank ("no readable data found"). Truncate to the schema max length.
    fields.clinical_data = raw.strip()[:50000]

    # ── Record-type classification ───────────────────────────────────────────
    # Structured transcription sections are the strongest signal; fall back to
    # keyword/Dr. detection for free-form text.
    has_visit_sections = any(
        s in sections
        for s in ("patient complaint", "vitals", "prescriptions", "diagnosis", "advice / notes")
    )
    has_lab_section = "lab results" in sections
    if has_lab_section and not has_visit_sections:
        fields.record_type = RecordType.LAB_REPORT
    elif has_visit_sections:
        fields.record_type = RecordType.DOCTOR_VISIT
    elif any(kw in lowered for kw in _LAB_KEYWORDS):
        fields.record_type = RecordType.LAB_REPORT
    elif re.search(r"\bdr\.?\s+\w", lowered) or "consultation" in lowered:
        fields.record_type = RecordType.DOCTOR_VISIT

    # ── Section-derived fields (cleaned of [illegible]/(?) noise) ─────────────
    def _section(name: str) -> str | None:
        body = sections.get(name)
        if not body:
            return None
        # First non-empty line is the value for single-line sections.
        first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
        return _clean_markers(first) or _clean_markers(body)

    fields.diagnosis = _section("diagnosis")
    fields.chief_complaint = _section("patient complaint")
    fields.existing_conditions = _section("existing conditions")
    fields.investigations = _section("investigations")

    # ── Provider name: prefer the Provider section, else first "Dr. Name" ─────
    provider_text = sections.get("provider") or raw
    for line in provider_text.splitlines():
        m = re.search(r"Dr\.?\s+([A-Z][\w.'-]*(?:[ \t]+[A-Z][\w.'-]*)*)", line)
        if m:
            fields.provider_name = _clean_markers(f"Dr. {m.group(1).strip()}")
            break
    else:
        # No doctor name — use the provider section's first line as the
        # clinic/hospital name, dropping a trailing date if present.
        if sections.get("provider"):
            first = next((ln.strip() for ln in sections["provider"].splitlines() if ln.strip()), "")
            if first:
                first = re.split(r"\s*[,;]\s*|\b\d{1,2}[\s/-][A-Za-z]", first)[0].strip()
                fields.provider_name = _clean_markers(first)

    # ── Record date: Provider section first, then the whole text ─────────────
    fields.record_date = _extract_record_date(sections.get("provider") or raw)

    # ── Vitals from the Vitals section ────────────────────────────────────────
    vitals = sections.get("vitals") or ""
    if vitals:
        bp = _extract_blood_pressure(vitals)
        if bp:
            fields.blood_pressure = bp
        hr = _extract_first_number(vitals, [r"pulse", r"\bpr\b", r"\bhr\b", r"heart rate"])
        if hr:
            fields.heart_rate = hr
        temp = _extract_first_number(vitals, [r"temp(?:erature)?"])
        if temp:
            fields.temperature = temp
        wt = _extract_first_number(vitals, [r"\bwt\b", r"weight"])
        if wt:
            fields.weight = wt
        ht = _extract_first_number(vitals, [r"\bht\b", r"height"])
        if ht:
            fields.height = ht

    return fields


def _extract_record_date(text: str) -> date | None:
    """Best-effort visit/record date from free text.

    Returns None when no unambiguous date is found, when the only date is on a
    DOB/birth line, or when a numeric date's day/month order is unknowable.
    """
    for line in text.splitlines():
        low = line.lower()
        if "dob" in low or "birth" in low:
            continue
        # Named-month dates are unambiguous: "02-Jun-2026", "5 June 2026".
        m = re.search(r"(\d{1,2})[\s/.-]+([A-Za-z]{3,9})[\s/.-]+(\d{4})", line)
        if m:
            day, month_token, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
            month = _MONTHS.get(month_token) or _MONTHS.get(month_token[:3])
            if month:
                try:
                    return date(year, month, day)
                except ValueError:
                    pass  # impossible day/month (e.g. 31-Feb) — keep scanning
        # Numeric dates: "15/06/2026". Disambiguate by magnitude; if both parts
        # are ≤ 12 the order is unknowable, so refuse to guess.
        m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", line)
        if m:
            day, month = _resolve_numeric_date(int(m.group(1)), int(m.group(2)))
            if day is not None:
                try:
                    return date(int(m.group(3)), month, day)
                except ValueError:
                    pass
    return None


def _resolve_numeric_date(a: int, b: int) -> tuple[int | None, int]:
    """Map two numeric date components to (day, month) when the order is obvious.

    Returns (None, 0) when ambiguous (both ≤ 12) or invalid (both > 12).
    """
    if a > 12 and b <= 12:
        return a, b  # DD/MM/YYYY
    if b > 12 and a <= 12:
        return b, a  # MM/DD/YYYY
    return None, 0


def _heuristic_fallback(
    result: ExtractionResult, text: str | None, mime_type: str
) -> ExtractionResult:
    """Gap-fill missing fields from a deterministic parse of the best text.

    Runs the heuristic on the richer transcription when one is available — the
    vision transcription is structured with ``--- section ---`` headers that the
    heuristic parses, whereas the OCR that triggered a vision fallback is often
    unusable. Fills ONLY fields the AI left empty (never overwrites AI values),
    and cleans ``[illegible]`` markers from both the AI values and the displayed
    transcription so the form never shows them.
    """
    source = result.transcription or text
    transcription = _clean_transcription_display(
        result.transcription or (str(text).strip() if text else None)
    )
    extracted = _clean_extracted(result.extracted)

    if source and str(source).strip():
        heur = heuristic_extract(source, mime_type)
        merged, changed = _fill_null_fields(extracted, heur)
        if changed:
            logger.info("Heuristic backfilled fields the AI left empty")
            extracted = merged

    return ExtractionResult(extracted=extracted, transcription=transcription)


def chunk_ocr_text(ocr_text: str, pages_per_chunk: int = 3) -> list[str]:
    """Split OCR text (with '--- Page N ---' markers) into chunks."""
    pages = re.split(r"(?=--- Page \d+ ---)", ocr_text)
    pages = [p.strip() for p in pages if p.strip()]
    chunks: list[str] = []
    for i in range(0, len(pages), pages_per_chunk):
        chunk = "\n\n".join(pages[i : i + pages_per_chunk])
        if chunk:
            chunks.append(chunk)
    return chunks if chunks else [ocr_text]


# Max concurrent tesseract processes during multi-page OCR. tesseract is CPU-bound,
# so cap concurrency to avoid thrashing CPU/memory on multi-page scanned PDFs.
OCR_CONCURRENCY = 4

# Minimum OCR quality to trust the text-extraction path instead of escalating to
# vision AI. Garbage OCR (non-empty but mostly symbols, or very sparse) scores
# below this, so the extractor falls back to vision rather than extracting from
# junk — the old code only escalated when OCR returned *nothing at all*.
OCR_QUALITY_THRESHOLD = 0.5


def _ocr_quality(text: str | None) -> float:
    """Heuristic OCR quality in [0, 1].

    Combines the alphanumeric ratio with a sparsity penalty. Garbage OCR
    (non-empty but mostly punctuation, or very few characters) scores low so the
    caller escalates to vision AI instead of extracting fields from junk text.
    """
    if not text:
        return 0.0
    total = len(text)
    alpha = sum(c.isalnum() for c in text)
    if total == 0 or alpha == 0:
        return 0.0
    ratio = alpha / total
    sparse_penalty = min(1.0, alpha / 40.0)  # <40 alnum chars → suspect
    return ratio * sparse_penalty


def extraction_confidence(extracted: "ExtractedFields") -> str:  # noqa: F821
    """Coverage-based confidence label: high/medium/low.

    More usable structured data → higher confidence. Replaces the binary
    has-any-data heuristic with a field-coverage signal.
    """
    score = 0
    if extracted.record_type:
        score += 1
    if extracted.record_date:
        score += 1
    if extracted.provider_name:
        score += 1
    if extracted.diagnosis:
        score += 1
    if extracted.chief_complaint:
        score += 1
    if extracted.prescriptions:
        score += 2
    if extracted.lab_tests:
        score += 2
    if extracted.eyeglass:
        score += 2
    vitals = sum(
        1
        for v in (
            extracted.weight,
            extracted.height,
            extracted.blood_pressure,
            extracted.heart_rate,
            extracted.temperature,
        )
        if v
    )
    score += min(vitals, 2)
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


async def ocr_pdf_pages(
    file_path: str, page_count: int
) -> tuple[str | None, list[bytes]]:
    """OCR all pages of a scanned PDF using tesseract.

    Renders each page to an image, runs tesseract OCR, and combines the
    results. Pages are OCR'd concurrently (bounded by OCR_CONCURRENCY) and
    each runs in a worker thread so the blocking tesseract subprocess does
    not stall the event loop. Much faster and more reliable than vision AI
    for text-heavy scanned documents.

    Returns ``(combined_text, page_renders)`` where ``page_renders`` is the
    list of rendered PNG bytes (one per page, in order). The renders are
    reused by the vision fallback so the same pages aren't re-rendered.
    """
    import shutil

    if not shutil.which("tesseract"):
        logger.info("Tesseract not installed — skipping OCR")
        return None, []

    semaphore = asyncio.Semaphore(OCR_CONCURRENCY)

    async def _bounded(page_num: int) -> tuple[str, bytes | None]:
        async with semaphore:
            return await asyncio.to_thread(_ocr_single_page, file_path, page_num)

    # gather preserves order, so page markers stay correctly numbered
    results = await asyncio.gather(*[_bounded(p) for p in range(page_count)])

    all_text = [f"--- Page {i + 1} ---\n{txt}" for i, (txt, _) in enumerate(results) if txt]
    combined = "\n\n".join(all_text).strip()
    renders = [png for _, png in results if png]
    return combined or None, renders


def _ocr_single_page(file_path: str, page_num: int) -> tuple[str, bytes | None]:
    """Render and OCR a single PDF page with tesseract (blocking worker).

    Opens the PDF independently per call, so it is safe to run concurrently
    from multiple threads. Returns ``(page_text, png_bytes)`` — the text may
    be "" on failure/empty so the caller can omit the page marker; ``png_bytes``
    is the rendered page image (200 DPI PNG) reused by the vision fallback to
    avoid a redundant re-render. All temp files are cleaned up in the finally
    block regardless of outcome.
    """
    import os
    import subprocess
    import tempfile

    import fitz

    tmp_path: str | None = None
    enhanced_path: str | None = None
    try:
        doc = fitz.open(file_path)
        try:
            page = doc[page_num]
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
        finally:
            doc.close()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(img_bytes)
            tmp_path = tmp.name

        # PDF pages are digitally rendered — skip PIL preprocessing (contrast
        # boost / threshold) which is designed for handwritten/faded photos and
        # can degrade clean digital text. Uploaded images (tesseract_image)
        # still get the full preprocessing pipeline.
        enhanced_path = _preprocess_image_for_ocr(tmp_path, preprocess=False)
        ocr_input = enhanced_path or tmp_path

        # PSM 6 = uniform block of text, better for medical documents
        result = subprocess.run(
            ["tesseract", ocr_input, "stdout", "--psm", "6", "--dpi", "200"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        page_text = result.stdout.strip()

        # If PSM 6 returns nothing, try PSM 4 (variable text sizes)
        if not page_text:
            result = subprocess.run(
                ["tesseract", ocr_input, "stdout", "--psm", "4", "--dpi", "200"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            page_text = result.stdout.strip()

        return page_text, img_bytes
    except Exception as exc:
        logger.warning("OCR failed for page %d: %s", page_num + 1, exc)
        return "", None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        if enhanced_path:
            try:
                os.unlink(enhanced_path)
            except OSError:
                pass


def tesseract_image(file_path: str) -> str | None:
    """OCR a single image file using tesseract (fast, local).

    Preprocesses the image (grayscale + contrast boost) for better
    handwriting recognition before running tesseract with --psm 6
    (uniform block of text) which works well for medical documents.
    """
    import shutil
    import subprocess

    if not shutil.which("tesseract"):
        return None

    enhanced_path: str | None = None
    try:
        enhanced_path = _preprocess_image_for_ocr(file_path)
        ocr_input = enhanced_path or file_path

        # PSM 6 = uniform block of text, good for medical docs/prescriptions
        result = subprocess.run(
            ["tesseract", ocr_input, "stdout", "--psm", "6"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        text = result.stdout.strip()
        if not text:
            # Fallback: try PSM 4 (single column of text of variable sizes)
            result = subprocess.run(
                ["tesseract", ocr_input, "stdout", "--psm", "4"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            text = result.stdout.strip()
        return text or None
    except Exception as exc:
        logger.debug("Image tesseract OCR failed: %s", exc)
        return None
    finally:
        if enhanced_path:
            import os

            try:
                os.unlink(enhanced_path)
            except OSError:
                pass


def _preprocess_image_for_ocr(file_path: str, preprocess: bool = True) -> str | None:
    """Enhance image for better OCR accuracy on handwritten medical documents.

    Applies grayscale conversion, contrast enhancement, and adaptive
    thresholding — particularly helpful for handwritten text on
    prescription pads and clinical notes.

    ``preprocess=False`` skips the PIL pipeline and returns ``None`` so the
    caller uses the original image as-is — used for digitally-rendered PDF
    pages where the pipeline can degrade clean text.

    Returns path to a temporary enhanced image, or None if PIL unavailable or
    preprocessing was skipped.
    """
    if not preprocess:
        return None
    try:
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError:
        return None

    try:
        img = Image.open(file_path)

        # Convert to grayscale
        if img.mode != "L":
            img = img.convert("L")

        # Boost contrast — helps distinguish faded handwriting
        img = ImageEnhance.Contrast(img).enhance(1.8)

        # Slight sharpening — helps with blurry handwritten characters
        img = img.filter(ImageFilter.SHARPEN)

        # Boost brightness slightly for dark backgrounds
        img = ImageEnhance.Brightness(img).enhance(1.1)

        # Adaptive threshold via point operation: convert to pure B/W
        # This binarization helps tesseract separate text from background
        img = img.point(lambda x: 0 if x < 140 else 255, "1")
        # Convert back to grayscale for tesseract compatibility
        img = img.convert("L")

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(tmp, format="PNG")
        tmp.close()
        return tmp.name
    except Exception as exc:
        logger.debug("Image preprocessing failed: %s", exc)
        return None


def _png_to_jpeg(png_bytes: bytes, quality: int = 85) -> bytes:
    """Re-encode PNG bytes to JPEG for compact vision API payloads.

    OCR renders pages at 200 DPI PNG (~1.5 MB each); vision AI APIs accept JPEG
    at 150 DPI (~300 KB) just as well, so re-encoding cuts payload size ~5×
    before sending. Falls back to the original PNG on any PIL error so a
    conversion failure never strands a page.
    """
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(png_bytes))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    except Exception as exc:
        logger.debug("PNG→JPEG re-encode failed, using original PNG: %s", exc)
        return png_bytes


def pdf_page_to_image(file_path: str, page_num: int = 0) -> bytes | None:
    """Render a PDF page to JPEG bytes using PyMuPDF.

    Uses JPEG at 150 DPI for compact size suitable for vision AI APIs
    (typically <300KB vs 1.5MB for PNG at 200 DPI).
    """
    try:
        import fitz

        doc = fitz.open(file_path)
        if page_num >= len(doc):
            doc.close()
            return None
        page = doc[page_num]
        # 150 DPI is sufficient for OCR/vision AI — keeps images under ~300KB
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("jpeg", jpg_quality=85)
        doc.close()
        return img_bytes
    except Exception as exc:
        logger.warning("PDF page-to-image conversion failed: %s", exc)
        return None


TRANSCRIPTION_PROMPT = """You are an expert medical document transcription specialist. Transcribe the medically relevant content from this document image.

GOAL: Produce a clean, formatted transcription containing ONLY medically important information. Omit non-essential content like logos, decorative borders, page numbers, watermarks, footers, hospital slogans, and repeated headers.

HANDWRITING RULES:
- Read character by character if needed. Handwriting is often the most important part.
- If partially legible, give your best reading followed by (?). Example: "Metformin (?) 500mg"
- Reserve [illegible] for runs of text that are genuinely unreadable; use [...] for cut-off sections. Do NOT mark a whole line [illegible] when part of it is readable — transcribe the readable part and mark only the unreadable fragment.
- NEVER skip handwritten prescriptions or notes — they contain the actual treatment plan.

ABBREVIATIONS — keep as written, do not expand:
BD/TDS/OD/HS/PRN/SOS/STAT, Tab/Cap/Inj/Syp/Drops, AC/PC/PO/IM/IV

FORMAT the transcription using this structure (include only sections present in the document):

--- Provider ---
Doctor/clinic/hospital name and date

--- Patient Complaint ---
Reason for visit or chief complaint

--- Vitals ---
BP, temperature, weight, height, pulse, SpO2, etc.

--- Diagnosis ---
Diagnosed condition(s)

--- Investigations ---
Tests ordered or recommended

--- Prescriptions ---
Each medicine on its own line: Type Name Dosage Duration Timing
Example: Tab Metformin 500mg 1-0-1 After food 30 days

--- Lab Results ---
Each test on its own line: Test Name: Value Unit (Reference Range)
Example: HbA1c: 8.9% (< 6.0%)

--- Advice / Notes ---
Diet instructions, follow-up date, lifestyle advice, any handwritten notes

--- Existing Conditions ---
Chronic conditions mentioned (e.g., T2DM, Hypertension)

If a section is not present in the document, omit it entirely. Do NOT include empty sections.
Return ONLY the formatted transcription text. No JSON, no explanations."""


async def _transcribe_via_vision(
    b64_images: list[str], mime_type: str, plan: ExtractionProviderPlan | None = None
) -> str | None:
    """Generate a raw text transcription via vision AI when no OCR text is available.

    Batches page images (``EXTRACTION_VISION_BATCH_SIZE``) into ONE multi-image
    vision call per batch using the multi-image entries + the transcription
    prompt — collapsing N per-page transcription calls into N/batch (a 9-page
    scan drops from 9 to 3 transcription calls). Falls back to one-call-per-page
    when a provider doesn't support multi-image. Returns concatenated text, or
    None if all providers fail.

    Runs through the same provider chain as extraction (respecting
    ``EXTRACTION_RACE_PROVIDERS`` and per-provider timeouts) instead of custom
    racing, so the sequential-by-default config doesn't waste API calls firing
    every provider at once. Uses a local provider ref — transcription overlaps
    extraction and must not clobber its provider record.
    """
    if plan is None:
        from app.schemas.ai_provider_config import default_provider_config

        plan = ExtractionProviderPlan.from_config(default_provider_config())
    if not b64_images:
        return None

    multi_entries = plan.vision_multi_entries()
    single_entries = plan.vision_entries()
    batch_size = max(1, settings.EXTRACTION_VISION_BATCH_SIZE)
    transcribe_ref: list[str] = [""]  # local — don't clobber extraction's ref

    parts: list[str] = []
    for start in range(0, len(b64_images), batch_size):
        batch = b64_images[start : start + batch_size]
        text: str | None = None
        if len(batch) > 1:
            async def invoke_multi(fn, batch=batch):
                return await fn(batch, mime_type, TRANSCRIPTION_PROMPT)
            text = await _run_provider_chain(
                multi_entries, invoke_multi, transcribe_ref, kind="Transcription"
            )
        if text is None:
            # Single-image batch, or every multi-image provider returned nothing.
            for b64 in batch:
                async def invoke_single(fn, b64=b64):
                    return await fn(b64, mime_type, TRANSCRIPTION_PROMPT)
                winner = await _run_provider_chain(
                    single_entries, invoke_single, transcribe_ref, kind="Transcription"
                )
                if winner:
                    parts.append(winner)
        else:
            parts.append(text)

    return "\n\n--- Page ---\n".join(parts) if parts else None


FORMAT_TRANSCRIPTION_PROMPT = """You are a medical document formatter. Clean up and format the following raw OCR text from a medical document.

RULES:
1. Remove non-essential content: logos, page numbers, watermarks, decorative borders, footers, hospital slogans, repeated headers, blank lines.
2. Keep ONLY medically relevant information: provider name, patient details, vitals, diagnosis, prescriptions, lab results, advice, follow-up dates.
3. FORMAT using this structure (include ONLY sections present in the text):

--- Provider ---
Doctor/clinic/hospital name and date

--- Patient Complaint ---
Reason for visit

--- Vitals ---
BP, temperature, weight, height, pulse, SpO2

--- Diagnosis ---
Diagnosed condition(s)

--- Investigations ---
Tests ordered or recommended

--- Prescriptions ---
Each medicine on its own line: Type Name Dosage Duration Timing

--- Lab Results ---
Each test: Test Name: Value Unit (Reference Range)

--- Advice / Notes ---
Diet, follow-up date, lifestyle advice

--- Existing Conditions ---
Chronic conditions mentioned

4. Preserve medical abbreviations as-is (BD, TDS, OD, HS, PRN, SOS, STAT, Tab, Cap, etc.).
5. Mark uncertain text with (?). Reserve [illegible] for genuinely unreadable runs only; never mark a whole value [illegible] when part of it is readable.
6. If a section is not present, omit it. Do NOT include empty sections.

Return ONLY the formatted text. No JSON, no explanations.

Raw OCR text:
"""


async def _format_ocr_transcription(
    raw_text: str, last_provider_ref: list, plan: ExtractionProviderPlan | None = None
) -> str | None:
    """Format raw OCR text into a clean, structured medical transcription.

    Uses a lightweight text-only AI call to clean up tesseract/cloud OCR output.
    Runs through the same provider chain as extraction (respecting
    ``EXTRACTION_RACE_PROVIDERS`` and per-provider timeouts); falls back to
    returning the raw text if all fail. Uses a local provider ref so the
    cosmetic formatting call doesn't clobber the extraction provider record
    (they run concurrently via ``asyncio.gather``).
    """
    if not raw_text or len(raw_text.strip()) < 20:
        return raw_text
    if plan is None:
        from app.schemas.ai_provider_config import default_provider_config

        plan = ExtractionProviderPlan.from_config(default_provider_config())

    prompt = f"{FORMAT_TRANSCRIPTION_PROMPT}{raw_text[:15000]}"
    providers = plan.text_entries()

    async def invoke(fn):
        return await fn(prompt)

    # Local ref — don't clobber the extraction's last_provider_ref (concurrent).
    format_ref: list[str] = [""]
    result = await _run_provider_chain(providers, invoke, format_ref, kind="Format")
    return result or raw_text


async def call_text_extraction(
    pdf_text: str, last_provider_ref: list, plan: ExtractionProviderPlan | None = None
) -> str | None:
    """Send extracted PDF text to an AI model for structured extraction.

    Tries the configured providers in priority order (primary group first);
    first non-empty result wins. Cloud providers fail fast (capped timeout) so a
    dead/slow key doesn't stall the chain, and Ollama is the bounded last-resort
    fallback. ``last_provider_ref`` is a mutable [str] recording the winning
    provider. Ollama is grammar-constrained to JSON to halve generation length
    and guarantee parseable output on the slow CPU-only path.
    """
    if plan is None:
        from app.schemas.ai_provider_config import default_provider_config

        plan = ExtractionProviderPlan.from_config(default_provider_config())
    prompt = f"{EXTRACTION_PROMPT}\n\nDocument Content:\n{pdf_text[:30000]}"

    providers = plan.text_entries(json_grammar=True)

    async def invoke(fn):
        return await fn(prompt)

    return await _run_provider_chain(providers, invoke, last_provider_ref, kind="Text")


def merge_extractions(
    base: "ExtractedFields",
    page: "ExtractedFields",  # noqa: F821
) -> "ExtractedFields":  # noqa: F821
    """Merge extraction results from multiple pages into one."""
    from app.schemas.health_record import ExtractedFields

    # Use page value if base is empty, keep base otherwise
    merged = ExtractedFields(
        record_type=page.record_type or base.record_type,
        record_date=page.record_date or base.record_date,
        record_time=page.record_time or base.record_time,
        clinical_data=base.clinical_data or "",
        diagnosis=page.diagnosis or base.diagnosis,
        existing_conditions=page.existing_conditions or base.existing_conditions,
        chief_complaint=page.chief_complaint or base.chief_complaint,
        investigations=page.investigations or base.investigations,
        prescription_text=page.prescription_text or base.prescription_text,
        provider_name=page.provider_name or base.provider_name,
        next_review_date=page.next_review_date or base.next_review_date,
    )

    # Append clinical_data from new page
    if page.clinical_data and base.clinical_data:
        merged.clinical_data = f"{base.clinical_data}\n\n--- Page ---\n{page.clinical_data}"
    elif page.clinical_data:
        merged.clinical_data = page.clinical_data

    # Merge arrays — append new rows
    if page.prescriptions:
        base_rx = base.prescriptions or []
        merged.prescriptions = base_rx + page.prescriptions
    else:
        merged.prescriptions = base.prescriptions

    if page.lab_tests:
        base_labs = base.lab_tests or []
        merged.lab_tests = base_labs + page.lab_tests
    else:
        merged.lab_tests = base.lab_tests

    # Eyeglass: page overwrites if present
    merged.eyeglass = page.eyeglass or base.eyeglass

    return merged


def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from AI response text (kept for back-compat)."""
    return strip_llm_noise(text)


# Reasoning wrappers emitted by qwen3 and other "thinking" models. These are
# stripped BEFORE JSON parsing because they routinely contain stray ``{``/``}``
# that mislead the brace-matcher into extracting a fragment of the reasoning
# instead of the real JSON object — the primary cause of blank extracted fields
# on the local Ollama path.
_REASONING_BLOCK_RE = re.compile(
    r"<(?:think|thinking|reflection)>.*?</(?:think|thinking|reflection)>",
    re.DOTALL | re.IGNORECASE,
)
# Unclosed reasoning tag (model truncated mid-thought): drop everything after it.
_REASONING_OPEN_RE = re.compile(r"<(?:think|thinking|reflection)>.*", re.DOTALL | re.IGNORECASE)


def strip_llm_noise(text: str) -> str:
    """Normalize an LLM response before JSON parsing.

    Removes qwen3-style reasoning wrappers, markdown code fences, and any
    leading prose so the remaining text begins at (or near) the JSON object.
    """
    text = _REASONING_BLOCK_RE.sub("", text)
    text = _REASONING_OPEN_RE.sub("", text)
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return text.strip()


def _parse_json_object(text: str) -> dict | None:
    """Best-effort extraction of a JSON object dict from noisy LLM text.

    Tries, in order: the whole text, the maximal ``{...}`` span (first ``{`` to
    last ``}``), then a depth-matched scan. Returns the first dict parsed.
    """
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        try:
            obj = json.loads(text[first : last + 1])
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass

    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except (json.JSONDecodeError, ValueError):
                        pass
                    break
    return None


# Accepted date/time formats beyond what Pydantic parses natively. Best-effort:
# the model is asked for ISO dates, so this only rescues odd regional formats.
_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y",
    "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y",
)
_TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p")


def _parse_flexible_date(value: object) -> date | None:
    if value is None or isinstance(value, date):
        return value  # type: ignore[return-value]
    s = str(value).strip().strip("'\"")
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _parse_flexible_time(value: object) -> time | None:
    if value is None or isinstance(value, time):
        return value  # type: ignore[return-value]
    s = str(value).strip().strip("'\"")
    if not s:
        return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    try:
        return time.fromisoformat(s[:8])
    except ValueError:
        return None


def _coerce_extraction_fields(data: dict) -> dict:
    """Best-effort coercion of raw LLM fields into schema-compatible values."""
    if isinstance(data.get("record_type"), str):
        try:
            from app.models.base import RecordType

            data["record_type"] = RecordType(data["record_type"])
        except (ValueError, KeyError):
            data["record_type"] = None
    for key in ("record_date", "next_review_date"):
        if key in data and not isinstance(data[key], (date, type(None))):
            data[key] = _parse_flexible_date(data[key])
    if "record_time" in data and not isinstance(data["record_time"], (time, type(None))):
        data["record_time"] = _parse_flexible_time(data["record_time"])
    for key in ("prescriptions", "lab_tests"):
        val = data.get(key)
        if val is None:
            continue
        data[key] = [r for r in val if isinstance(r, dict)] if isinstance(val, list) else None
    if data.get("eyeglass") is not None and not isinstance(data["eyeglass"], dict):
        data["eyeglass"] = None
    if isinstance(data.get("clinical_data"), str) and len(data["clinical_data"]) > 50000:
        data["clinical_data"] = data["clinical_data"][:50000]
    return data


def _build_extracted_lenient(data: dict) -> "ExtractedFields":  # noqa: F821
    """Construct ``ExtractedFields``, dropping only fields that can't validate.

    Replaces the old all-or-nothing ``ExtractedFields(**data)`` so a single bad
    value (an unparseable date, an unknown enum) no longer discards the entire
    extraction — the remaining fields still come through.
    """
    from app.schemas.health_record import ExtractedFields

    data = _coerce_extraction_fields(dict(data))
    try:
        return ExtractedFields(**data)
    except Exception:
        pass
    kept: dict = {}
    for key, value in data.items():
        try:
            ExtractedFields(**{key: value})  # validates this field in isolation
            kept[key] = value
        except Exception as exc:
            logger.debug("Extraction: dropping unparseable field %s (%s)", key, exc)
    try:
        return ExtractedFields(**kept)
    except Exception:
        return ExtractedFields()


def parse_extraction(raw_text: str | None, extracted_class: type) -> "ExtractedFields":  # noqa: F821
    """Parse AI response text into ExtractedFields (robust to LLM noise)."""
    if not raw_text:
        logger.warning("Extraction: AI returned empty response")
        from app.schemas.health_record import ExtractedFields

        return ExtractedFields()

    # Guard: multi-page lab reports can produce large JSON; vision models
    # sometimes echo image data producing multi-MB responses.
    MAX_EXTRACTION_CHARS = 32768
    if len(raw_text) > MAX_EXTRACTION_CHARS:
        early = raw_text[:MAX_EXTRACTION_CHARS]
        match = re.search(r"\{", early)
        raw_text = early[match.start() :] if match else early

    cleaned = strip_llm_noise(raw_text)
    data = _parse_json_object(cleaned)

    if data is None:
        logger.warning(
            "Extraction: could not parse JSON from AI response (first 200 chars: %s)",
            raw_text[:200] if raw_text else "None",
        )
        from app.schemas.health_record import ExtractedFields

        return ExtractedFields()

    return _build_extracted_lenient(data)


async def call_vision_provider(
    file_path: str,
    mime_type: str,
    last_provider_ref: list,
    plan: ExtractionProviderPlan | None = None,
) -> str | None:
    """Send document to vision-capable AI provider with failover."""
    file_bytes = Path(file_path).read_bytes()
    b64_data = base64.b64encode(file_bytes).decode()
    return await call_vision_provider_from_b64(b64_data, mime_type, last_provider_ref, plan)


async def call_vision_provider_from_b64(
    b64_data: str,
    mime_type: str,
    last_provider_ref: list,
    plan: ExtractionProviderPlan | None = None,
) -> str | None:
    """Send base64-encoded data to vision-capable AI providers in priority order.

    Uses the configured provider order (primary group first); first non-empty
    result wins. Cloud providers fail fast (capped timeout), Ollama is the
    bounded last-resort fallback. Responses are truncated to keep prompts
    bounded. Ollama is grammar-constrained to JSON for parseable output.
    """
    if plan is None:
        from app.schemas.ai_provider_config import default_provider_config

        plan = ExtractionProviderPlan.from_config(default_provider_config())
    MAX_RESPONSE_CHARS = 4096

    providers = plan.vision_entries(json_grammar=True)

    async def invoke(fn):
        result = await fn(b64_data, mime_type, EXTRACTION_PROMPT)
        if result and len(result) > MAX_RESPONSE_CHARS:
            return result[:MAX_RESPONSE_CHARS]
        return result

    return await _run_provider_chain(providers, invoke, last_provider_ref, kind="Vision")


async def call_vision_provider_from_b64_multi(
    b64_images: list[str],
    mime_type: str,
    last_provider_ref: list,
    plan: ExtractionProviderPlan | None = None,
) -> str | None:
    """Send several page images in ONE vision call per provider (multi-page scan).

    Mirrors :func:`call_vision_provider_from_b64` but uses the ``*_multi``
    provider callables so a k-page batch is one call per provider (raced/
    failed-over via the chain) instead of k. Returns ``None`` when no provider
    produced a result — callers should then fall back to per-page single-image
    calls so an unsupported multi-image model never strands a page.
    """
    if not b64_images:
        return None
    if plan is None:
        from app.schemas.ai_provider_config import default_provider_config

        plan = ExtractionProviderPlan.from_config(default_provider_config())
    MAX_RESPONSE_CHARS = 4096

    providers = plan.vision_multi_entries(json_grammar=True)

    async def invoke(fn):
        result = await fn(b64_images, mime_type, EXTRACTION_PROMPT)
        if result and len(result) > MAX_RESPONSE_CHARS:
            return result[:MAX_RESPONSE_CHARS]
        return result

    return await _run_provider_chain(providers, invoke, last_provider_ref, kind="Vision")
