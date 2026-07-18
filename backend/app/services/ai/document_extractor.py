"""Document extraction — OCR, PDF handling, vision AI extraction, and parsing."""

import asyncio
import base64
import functools
import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.provider_keys import any_cloud_provider_configured
from app.services.ai.providers.gemini import call_gemini_text, call_gemini_vision, call_gemini_ocr
from app.services.ai.providers.openai import call_openai_text, call_openai_vision
from app.services.ai.providers.groq import call_groq_text, call_groq_vision
from app.services.ai.providers.openrouter import call_openrouter_text, call_openrouter_vision
from app.services.ai.providers.ollama import call_ollama_text, call_ollama_vision, call_ollama_ocr

logger = logging.getLogger(__name__)

settings = get_settings()


async def _run_provider_chain(providers, invoke, last_provider_ref: list, kind: str) -> str | None:
    """Try providers in priority order; first non-empty result wins.

    Each entry in ``providers`` is ``(callable, label, is_local)``. Cloud
    providers are capped at ``settings.EXTRACTION_PROVIDER_TIMEOUT`` so a slow or
    dead key fails fast and the next provider is tried; the local Ollama entry
    (``is_local=True``) is exempt — it keeps its own generous adaptive timeout,
    since as the last-resort fallback you want it to actually finish.

    ``invoke(fn)`` calls the provider with the arguments appropriate to its kind
    (text takes a prompt; vision takes b64 + mime + prompt) and returns its text
    or ``None``.
    """
    for fn, label, is_local in providers:
        try:
            if is_local:
                result = await invoke(fn)
            else:
                result = await asyncio.wait_for(
                    invoke(fn), timeout=settings.EXTRACTION_PROVIDER_TIMEOUT
                )
        except asyncio.TimeoutError:
            logger.warning(
                "%s provider %s timed out after %ds — trying next",
                kind,
                label,
                settings.EXTRACTION_PROVIDER_TIMEOUT,
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


EXTRACTION_PROMPT = """You are a medical document data extraction assistant. Analyze the provided medical document image/PDF and extract structured data.

IMPORTANT INSTRUCTIONS:
1. Return ONLY valid JSON -- no markdown, no explanation, no code fences.
2. If a field is not found, set it to null — EXCEPT record_type: ALWAYS determine record_type from the document content (never return null for it). ALWAYS attempt record_date from the document header/date line, even when other fields are uncertain. Prefer your best-effort reading over leaving a field null; mark a soft guess with "(?)".
3. Dates must be in YYYY-MM-DD format. Times in HH:MM format.
4. HANDWRITING: This document may contain handwritten notes, especially prescriptions. Carefully transcribe ALL handwritten text. Handwritten medicine names, dosages, and instructions are common — read them character by character if needed. If handwriting is partially legible, provide your best reading and mark uncertain entries with "(?)" in the note field. NEVER skip handwritten prescriptions — they are often the most important part of the record.
5. For record_type, use exactly one of these values:
   "doctor_visit" (consultation notes, prescriptions from a visit),
   "lab_report" (lab test results, blood work, diagnostic reports),
   "rx_eyeglass" (eyeglass prescriptions, vision test results),
   "blood_glucose" (glucose readings, diabetes monitoring),
   "misc_record" (anything that doesn't fit the above categories)
6. provider_name is the doctor/clinic/hospital name.
7. If the document contains prescriptions/medications (printed OR handwritten), extract each medicine as a separate object in the "prescriptions" array with: type (Tab/Cap/Inj/Syp/Cream/Drops/Other), medicine (name), dosage (e.g. "1-1-1"), duration (e.g. "30 days"), timing (before_food/after_food/with_food/empty_stomach/bedtime/sos/stat), note.
   CRITICAL for handwritten prescriptions:
   - Transcribe the medicine name exactly as written, even if misspelled.
   - Common abbreviations: BD (twice daily), TDS/TID (three times daily), OD (once daily), HS (bedtime), PRN (as needed), SOS (if needed), STAT (immediately).
   - If a handwritten medicine name is ambiguous, include your best guess and add "(?)" in the note.
   - Look for prescription patterns: medicine names are often followed by dosage numbers, then frequency abbreviations.
8. If the document contains lab test results, extract each test as a separate object in the "lab_tests" array with: test_name, result (numeric or text value WITHOUT units), units (e.g. "mg/dL", "IU/L", "%"), ref_value (reference range WITH units), note.
   CRITICAL for lab_tests:
   - Separate the numeric/text result from units into distinct fields.
   - ref_value: Use the reference range printed on the document if available. If NOT printed, provide the standard reference range from established medical guidelines (e.g. WHO, ADA, standard lab medicine references). Always include units.
   - note: Write a brief clinical comment on the result status. Examples: "Normal", "Elevated - above target", "Low - monitor", "Critical high", "Borderline", "Well controlled". Keep it under 10 words.
9. If the document is an eyeglass prescription, extract vision data into the "eyeglass" object.
10. existing_conditions: Extract ONLY conditions the document EXPLICITLY labels as pre-existing, chronic, or past medical history (e.g. a "PMH", "Known case of", or "History of" section). Do NOT infer these from the current visit's diagnosis. Comma-separated, uppercase, or null if none are explicitly stated.
11. chief_complaint: The main reason for the visit / chief complaint (e.g. "Fever for 3 days", "Routine follow-up for T2DM"). Extract exactly as stated, including from handwritten notes.
12. investigations: Any tests or investigations ordered, recommended, or mentioned (e.g. "CBC, HbA1c, Lipid profile, ECG"). Comma-separated.
13. clinical_data: A CONCISE summary (under 150 words) of any handwritten notes, advice, or instructions that don't fit other fields. Do NOT copy the document verbatim — summarize. Preserve original meaning.
14. VITALS: If the document records any vital signs or measurements, extract them. weight = numeric kg, height = numeric cm, blood_pressure = "systolic/diastolic" string e.g. "120/80" (mmHg), heart_rate = numeric bpm, temperature = numeric °F. Set a field to null if that vital is not present. Do not invent values.

Return this exact JSON structure:
{
  "record_type": "doctor_visit" or null,
  "record_date": "2024-01-15" or null,
  "record_time": "10:30" or null,
  "clinical_data": "concise (<150 word) summary of other notes/advice" or null,
  "diagnosis": "extracted diagnosis" or null,
  "existing_conditions": "T2DM, HYPERTENSION, DEPRESSION" or null,
  "chief_complaint": "Fever for 3 days" or null,
  "investigations": "CBC, HbA1c, Lipid profile" or null,
  "provider_name": "Dr. Smith, City Hospital" or null,
  "next_review_date": "2024-06-15" or null,
  "prescriptions": [
    {"type": "Tab", "medicine": "Syndopa 110", "dosage": "1-1-1", "duration": "30 days", "timing": "before_food", "note": ""}
  ] or null,
  "lab_tests": [
    {"test_name": "HbA1c", "result": "8.9", "units": "%", "ref_value": "< 6.0 % (ADA guideline)", "note": "Elevated - above target"},
    {"test_name": "Fasting Glucose", "result": "142", "units": "mg/dL", "ref_value": "70-100 mg/dL", "note": "High - diabetic range"},
    {"test_name": "Total Cholesterol", "result": "195", "units": "mg/dL", "ref_value": "< 200 mg/dL", "note": "Borderline high"},
    {"test_name": "HDL Cholesterol", "result": "55", "units": "mg/dL", "ref_value": "> 40 mg/dL (men)", "note": "Normal"}
  ] or null,
  "eyeglass": {
    "re_sph": "+2.50", "re_cyl": "-0.50", "re_axs": "140", "re_va": "6/6",
    "le_sph": "+1.25", "le_cyl": "-0.75", "le_axs": "090", "le_va": "6/6",
    "add_power": "+2.50", "pd": "32/32"
  } or null,
  "weight": 72.5 or null,
  "height": 170 or null,
  "blood_pressure": "120/80" or null,
  "heart_rate": 76 or null,
  "temperature": 98.6 or null
}"""


async def extract_medical_data(
    db: AsyncSession, file_path: str, mime_type: str, last_provider_ref: list
) -> ExtractionResult:
    """Extract structured medical data from a document file via vision AI.

    Returns an ExtractionResult containing both structured fields and the
    raw OCR/text transcription (when available).
    """
    from app.schemas.health_record import ExtractedFields

    if mime_type == "application/pdf":
        pdf_text = extract_pdf_text(file_path)
        if pdf_text:
            logger.info(
                "PDF has embedded text (%d chars) — using fast text extraction", len(pdf_text)
            )
            # Extraction and transcription-formatting both consume only pdf_text —
            # run them concurrently to save an AI round-trip.
            if await _fast_cloud_text_available():
                raw_text, formatted = await asyncio.gather(
                    call_text_extraction(pdf_text, last_provider_ref),
                    _format_ocr_transcription(pdf_text, last_provider_ref),
                )
            else:
                # Ollama-only: skip the cosmetic transcription call (it would
                # serialize behind extraction on the single-threaded server).
                raw_text = await call_text_extraction(pdf_text, last_provider_ref)
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

        # Check if the PDF can even be opened
        try:
            import fitz

            doc = fitz.open(file_path)
            page_count = len(doc)
            doc.close()
            if page_count == 0:
                logger.error("PDF has 0 pages — file may be corrupted or empty")
                return ExtractionResult(extracted=ExtractedFields())
            logger.info("PDF has %d pages", page_count)
        except Exception as exc:
            logger.error("Cannot open PDF: %s", exc)
            return ExtractionResult(extracted=ExtractedFields())

        # Step 1: Render pages and OCR with tesseract (fast, local)
        ocr_text = await ocr_pdf_pages(file_path, page_count)
        ocr_quality = _ocr_quality(ocr_text)

        if ocr_text and ocr_quality >= OCR_QUALITY_THRESHOLD:
            logger.info(
                "OCR extracted %d chars (quality %.2f) from %d pages — using text extraction",
                len(ocr_text),
                ocr_quality,
                page_count,
            )
            # Chunk OCR text by page markers to keep prompts small for local models
            page_chunks = chunk_ocr_text(ocr_text, pages_per_chunk=3)
            all_extracted = ExtractedFields()
            # Process all chunks in parallel
            chunk_results = await asyncio.gather(
                *[call_text_extraction(chunk[:10000], last_provider_ref) for chunk in page_chunks]
            )
            for raw_text in chunk_results:
                chunk_result = parse_extraction(raw_text, ExtractedFields)
                all_extracted = merge_extractions(all_extracted, chunk_result)
            if all_extracted.has_any_data():
                formatted = (
                    await _format_ocr_transcription(ocr_text, last_provider_ref)
                    if await _fast_cloud_text_available()
                    else ocr_text
                )
                return ExtractionResult(extracted=all_extracted, transcription=formatted)
            logger.warning(
                "OCR text extraction returned no usable fields — falling back to vision AI"
            )
        else:
            logger.warning(
                "OCR quality too low (%.2f) or empty — falling back to vision AI", ocr_quality
            )

        # Step 2: Vision AI fallback (slow, requires working provider)
        page_images: list[str] = []
        page_num = 0
        while True:
            img_bytes = pdf_page_to_image(file_path, page_num=page_num)
            if not img_bytes:
                break
            page_images.append(base64.b64encode(img_bytes).decode())
            page_num += 1

        if not page_images:
            logger.error(
                "PDF has %d pages but none could be rendered — file may be encrypted", page_count
            )
            return ExtractionResult(extracted=ExtractedFields())

        logger.info("Vision fallback: %d pages — extracting in parallel batches", len(page_images))

        BATCH_SIZE = 3
        all_extracted = ExtractedFields()
        for batch_start in range(0, len(page_images), BATCH_SIZE):
            batch = page_images[batch_start : batch_start + BATCH_SIZE]
            page_nums = list(range(batch_start + 1, batch_start + len(batch) + 1))
            logger.info(
                "Extracting pages %s via vision AI...", ", ".join(str(p) for p in page_nums)
            )
            tasks = [
                call_vision_provider_from_b64(b64, "image/jpeg", last_provider_ref) for b64 in batch
            ]
            results = await asyncio.gather(*tasks)
            for raw_text in results:
                page_result = parse_extraction(raw_text, ExtractedFields)
                all_extracted = merge_extractions(all_extracted, page_result)

        # Generate transcription for vision-only path
        transcription = await _transcribe_via_vision(page_images, mime_type="image/jpeg")
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
        ocr_text = await asyncio.to_thread(tesseract_image, file_path)
        if ocr_text and _ocr_quality(ocr_text) >= OCR_QUALITY_THRESHOLD:
            logger.info(
                "Image OCR (tesseract) extracted %d chars — using text extraction", len(ocr_text)
            )
            if await _fast_cloud_text_available():
                raw_text, formatted = await asyncio.gather(
                    call_text_extraction(ocr_text, last_provider_ref),
                    _format_ocr_transcription(ocr_text, last_provider_ref),
                )
            else:
                raw_text = await call_text_extraction(ocr_text, last_provider_ref)
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
        ocr_text = await call_ocr(file_path, mime_type)
        if ocr_text and _ocr_quality(ocr_text) >= OCR_QUALITY_THRESHOLD:
            if await _fast_cloud_text_available():
                raw_text, formatted = await asyncio.gather(
                    call_text_extraction(ocr_text, last_provider_ref),
                    _format_ocr_transcription(ocr_text, last_provider_ref),
                )
            else:
                raw_text = await call_text_extraction(ocr_text, last_provider_ref)
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
        call_vision_provider(file_path, mime_type, last_provider_ref)
    )
    transcription_task = asyncio.create_task(_transcribe_via_vision([b64_data], mime_type))
    raw_text, transcription = await asyncio.gather(extraction_task, transcription_task)
    return ExtractionResult(
        extracted=parse_extraction(raw_text, ExtractedFields),
        transcription=transcription,
    )


async def call_ocr(file_path: str, mime_type: str) -> str | None:
    """Use vision AI to OCR an image to text. Prefers Google Gemini."""
    file_bytes = Path(file_path).read_bytes()
    b64_data = base64.b64encode(file_bytes).decode()

    # Try Gemini first
    result = await call_gemini_ocr(b64_data, mime_type)
    if result:
        return result

    # Fallback to Ollama (local vision)
    result = await call_ollama_ocr(b64_data, mime_type)
    if result:
        return result

    return None


def extract_pdf_text(file_path: str) -> str | None:
    """Extract text content from a PDF file using PyMuPDF."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text.strip() or None
    except Exception as exc:
        logger.warning("PDF text extraction failed: %s", exc)
        return None


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


async def ocr_pdf_pages(file_path: str, page_count: int) -> str | None:
    """OCR all pages of a scanned PDF using tesseract.

    Renders each page to an image, runs tesseract OCR, and combines the
    results. Pages are OCR'd concurrently (bounded by OCR_CONCURRENCY) and
    each runs in a worker thread so the blocking tesseract subprocess does
    not stall the event loop. Much faster and more reliable than vision AI
    for text-heavy scanned documents.
    """
    import shutil

    if not shutil.which("tesseract"):
        logger.info("Tesseract not installed — skipping OCR")
        return None

    semaphore = asyncio.Semaphore(OCR_CONCURRENCY)

    async def _bounded(page_num: int) -> str:
        async with semaphore:
            return await asyncio.to_thread(_ocr_single_page, file_path, page_num)

    # gather preserves order, so page markers stay correctly numbered
    results = await asyncio.gather(*[_bounded(p) for p in range(page_count)])

    all_text = [f"--- Page {i + 1} ---\n{txt}" for i, txt in enumerate(results) if txt]
    combined = "\n\n".join(all_text).strip()
    return combined or None


def _ocr_single_page(file_path: str, page_num: int) -> str:
    """Render and OCR a single PDF page with tesseract (blocking worker).

    Opens the PDF independently per call, so it is safe to run concurrently
    from multiple threads. Returns the page text, or "" on failure/empty so
    the caller can omit the page marker. All temp files are cleaned up in
    the finally block regardless of outcome.
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

        # Preprocess for better handwriting OCR
        enhanced_path = _preprocess_image_for_ocr(tmp_path)
        ocr_input = enhanced_path or tmp_path

        # PSM 6 = uniform block of text, better for medical documents
        result = subprocess.run(
            ["tesseract", ocr_input, "stdout", "--psm", "6"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        page_text = result.stdout.strip()

        # If PSM 6 returns nothing, try PSM 4 (variable text sizes)
        if not page_text:
            result = subprocess.run(
                ["tesseract", ocr_input, "stdout", "--psm", "4"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            page_text = result.stdout.strip()

        return page_text
    except Exception as exc:
        logger.warning("OCR failed for page %d: %s", page_num + 1, exc)
        return ""
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


def _preprocess_image_for_ocr(file_path: str) -> str | None:
    """Enhance image for better OCR accuracy on handwritten medical documents.

    Applies grayscale conversion, contrast enhancement, and adaptive
    thresholding — particularly helpful for handwritten text on
    prescription pads and clinical notes.

    Returns path to a temporary enhanced image, or None if PIL unavailable.
    """
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


async def _transcribe_via_vision(b64_images: list[str], mime_type: str) -> str | None:
    """Generate a raw text transcription via vision AI when no OCR text is available.

    Races Gemini/OpenRouter/Groq in parallel for each image.
    Returns concatenated text from all images, or None if all providers fail.
    """
    parts: list[str] = []
    for b64 in b64_images:
        providers = [
            (call_gemini_vision, "Gemini"),
            (call_openrouter_vision, "OpenRouter"),
            (call_groq_vision, "Groq"),
        ]

        async def _try(fn, name):
            try:
                result = await fn(b64, mime_type, TRANSCRIPTION_PROMPT)
                if result:
                    return result
            except Exception as exc:
                logger.debug("Transcription provider %s failed: %s", name, exc)
            return None

        tasks = [asyncio.create_task(_try(fn, name)) for fn, name in providers]
        winner = None
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result is not None:
                winner = result
                break
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        if winner:
            parts.append(winner)

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


async def _format_ocr_transcription(raw_text: str, last_provider_ref: list) -> str | None:
    """Format raw OCR text into a clean, structured medical transcription.

    Uses a lightweight text-only AI call to clean up tesseract/cloud OCR output.
    Falls back to returning the raw text if formatting fails.
    """
    if not raw_text or len(raw_text.strip()) < 20:
        return raw_text

    prompt = f"{FORMAT_TRANSCRIPTION_PROMPT}{raw_text[:15000]}"

    providers = [
        (call_openrouter_text, "OpenRouter"),
        (call_gemini_text, "Gemini"),
        (call_groq_text, "Groq"),
        (call_ollama_text, "Ollama"),
    ]

    async def _try(fn, name):
        try:
            result = await fn(prompt)
            if result:
                return result
        except Exception as exc:
            logger.debug("Format transcription provider %s failed: %s", name, exc)
        return None

    tasks = [asyncio.create_task(_try(fn, name)) for fn, name in providers]
    winner = None
    for coro in asyncio.as_completed(tasks):
        result = await coro
        if result is not None:
            winner = result
            break
    for t in tasks:
        if not t.done():
            t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    return winner or raw_text


async def call_text_extraction(pdf_text: str, last_provider_ref: list) -> str | None:
    """Send extracted PDF text to an AI model for structured extraction.

    Tries providers in priority order — Groq → OpenRouter → Gemini → OpenAI →
    local Ollama. First non-empty result wins; cloud providers fail fast (capped
    timeout) so a dead/slow key doesn't stall the chain, and Ollama is the
    last-resort fallback. ``last_provider_ref`` is a mutable [str] recording the
    winning provider.
    """
    prompt = f"{EXTRACTION_PROMPT}\n\nDocument Content:\n{pdf_text[:30000]}"

    providers = [
        (call_groq_text, "Groq text", False),
        (call_openrouter_text, "OpenRouter text", False),
        (call_gemini_text, "Gemini text", False),
        (call_openai_text, "OpenAI text", False),
        # Grammar-constrain Ollama to JSON — halves generation length and
        # guarantees parseable output on the slow CPU-only path.
        (functools.partial(call_ollama_text, fmt="json"), "Ollama text", True),
    ]

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
    """Remove markdown code fences from AI response text."""
    cleaned = re.sub(r"```json\s*", "", text)
    return re.sub(r"```\s*", "", cleaned).strip()


def parse_extraction(raw_text: str | None, extracted_class: type) -> "ExtractedFields":  # noqa: F821
    """Parse AI response text into ExtractedFields."""
    from app.schemas.health_record import ExtractedFields

    if not raw_text:
        logger.warning("Extraction: AI returned empty response")
        return ExtractedFields()

    # Guard: multi-page lab reports can produce large JSON.
    # Vision models sometimes echo image data producing multi-MB responses.
    MAX_EXTRACTION_CHARS = 32768
    if len(raw_text) > MAX_EXTRACTION_CHARS:
        # Try to locate the JSON object early in the response
        early = raw_text[:MAX_EXTRACTION_CHARS]
        match = re.search(r"\{", early)
        if match:
            raw_text = early[match.start() :]
        else:
            raw_text = early

    # Strip markdown code fences if present
    cleaned = strip_markdown_fences(raw_text)

    data: dict | None = None
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            data = parsed
    except (json.JSONDecodeError, ValueError):
        # Try to find the outermost JSON object by brace-matching
        start = cleaned.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(cleaned)):
                if cleaned[i] == "{":
                    depth += 1
                elif cleaned[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(cleaned[start : i + 1])
                            if isinstance(parsed, dict):
                                data = parsed
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break

    if data is None:
        logger.warning(
            "Extraction: could not parse JSON from AI response (first 200 chars: %s)",
            raw_text[:200] if raw_text else "None",
        )
        return ExtractedFields()

    # Map record_type string to enum if present
    if "record_type" in data and isinstance(data["record_type"], str):
        try:
            from app.models.base import RecordType

            data["record_type"] = RecordType(data["record_type"])
        except ValueError:
            data["record_type"] = None

    try:
        return ExtractedFields(**data)
    except Exception as exc:
        logger.warning("Failed to parse extraction response: %s", exc)
        return ExtractedFields()


async def call_vision_provider(
    file_path: str, mime_type: str, last_provider_ref: list
) -> str | None:
    """Send document to vision-capable AI provider with failover."""
    file_bytes = Path(file_path).read_bytes()
    b64_data = base64.b64encode(file_bytes).decode()
    return await call_vision_provider_from_b64(b64_data, mime_type, last_provider_ref)


async def call_vision_provider_from_b64(
    b64_data: str, mime_type: str, last_provider_ref: list
) -> str | None:
    """Send base64-encoded data to vision-capable AI providers in priority order.

    Groq → OpenRouter → Gemini → OpenAI → local Ollama. First non-empty result
    wins; cloud providers fail fast (capped timeout), Ollama is the last-resort
    fallback. Responses are truncated to keep prompts bounded.
    """
    MAX_RESPONSE_CHARS = 4096

    providers = [
        (call_groq_vision, "Groq vision", False),
        (call_openrouter_vision, "OpenRouter vision", False),
        (call_gemini_vision, "Gemini vision", False),
        (call_openai_vision, "OpenAI vision", False),
        (functools.partial(call_ollama_vision, fmt="json"), "Ollama vision", True),
    ]

    async def invoke(fn):
        result = await fn(b64_data, mime_type, EXTRACTION_PROMPT)
        if result and len(result) > MAX_RESPONSE_CHARS:
            return result[:MAX_RESPONSE_CHARS]
        return result

    return await _run_provider_chain(providers, invoke, last_provider_ref, kind="Vision")
