"""Document extraction — OCR, PDF handling, vision AI extraction, and parsing."""
import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.ai.providers.gemini import call_gemini_text, call_gemini_vision, call_gemini_ocr
from app.services.ai.providers.openai import call_openai_text, call_openai_vision
from app.services.ai.providers.groq import call_groq_text, call_groq_vision
from app.services.ai.providers.openrouter import call_openrouter_text, call_openrouter_vision
from app.services.ai.providers.ollama import call_ollama_text, call_ollama_vision, call_ollama_ocr

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Holds both structured extraction and raw transcription."""

    extracted: "ExtractedFields"  # noqa: F821
    transcription: str | None = None

EXTRACTION_PROMPT = """You are a medical document data extraction assistant. Analyze the provided medical document image/PDF and extract structured data.

IMPORTANT INSTRUCTIONS:
1. Return ONLY valid JSON -- no markdown, no explanation, no code fences.
2. If a field is not found or unclear in the document, set it to null.
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
10. existing_conditions: Extract any mentioned existing/chronic conditions (e.g. "T2DM, Hypertension, Depression"). Comma-separated, uppercase.
11. chief_complaint: The main reason for the visit / chief complaint (e.g. "Fever for 3 days", "Routine follow-up for T2DM"). Extract exactly as stated, including from handwritten notes.
12. investigations: Any tests or investigations ordered, recommended, or mentioned (e.g. "CBC, HbA1c, Lipid profile, ECG"). Comma-separated.
13. clinical_data: Include a transcription of any handwritten notes, advice, or instructions that don't fit into other fields. Preserve the original meaning even if exact words are uncertain.

Return this exact JSON structure:
{
  "record_type": "doctor_visit" or null,
  "record_date": "2024-01-15" or null,
  "record_time": "10:30" or null,
  "clinical_data": "all other relevant text, observations, notes — include transcribed handwritten content here" or null,
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
  } or null
}"""


async def classify_document(file_path: str, mime_type: str, call_ai_fn) -> "RecordType":  # noqa: F821
    """Classify a document into a record type using AI with keyword fallback."""
    from app.models.base import RecordType

    # Try to get text content first
    text = ""
    if mime_type == "application/pdf":
        text = extract_pdf_text(file_path) or ""

    # Try AI classification
    classification_prompt = (
        "Classify this medical document into exactly one category. "
        "Return ONLY one of these words: doctor_visit, lab_report, rx_eyeglass, blood_glucose, misc_record\n\n"
        f"Document content (first 1000 chars):\n{text[:1000]}"
    )
    try:
        response, _ = await call_ai_fn(classification_prompt, "")
        if response:
            cleaned = response.strip().lower().strip("\"'`")
            for rt in RecordType:
                if rt.value in cleaned:
                    return rt
    except Exception as exc:
        logger.warning("AI classification failed, using keyword fallback: %s", exc)

    # Keyword fallback
    text_lower = text.lower()
    if any(kw in text_lower for kw in ("prescription", "rx", "medicine", "tablet", "capsule", "syrup")):
        return RecordType.DOCTOR_VISIT
    if any(kw in text_lower for kw in ("eye", "vision", "sph", "cyl", "lens", "optical")):
        return RecordType.RX_EYEGLASS
    if any(kw in text_lower for kw in ("hba1c", "diabetes monitoring", "fasting glucose", "postprandial")):
        return RecordType.BLOOD_GLUCOSE
    if any(kw in text_lower for kw in ("lab", "test", "blood", "hemoglobin", "cholesterol", "urine")):
        return RecordType.LAB_REPORT
    return RecordType.MISC_RECORD


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
            logger.info("PDF has embedded text (%d chars) — using fast text extraction", len(pdf_text))
            raw_text = await call_text_extraction(pdf_text, last_provider_ref)
            result = parse_extraction(raw_text, ExtractedFields)
            if not result.has_any_data():
                logger.warning("PDF text extraction returned no usable fields — text may be non-medical or too short")
            return ExtractionResult(extracted=result, transcription=pdf_text)

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
        ocr_text = ocr_pdf_pages(file_path, page_count)

        if ocr_text:
            logger.info("OCR extracted %d chars from %d pages — using text extraction", len(ocr_text), page_count)
            # Chunk OCR text by page markers to keep prompts small for local models
            page_chunks = chunk_ocr_text(ocr_text, pages_per_chunk=3)
            all_extracted = ExtractedFields()
            # Process all chunks in parallel
            chunk_results = await asyncio.gather(*[
                call_text_extraction(chunk[:10000], last_provider_ref)
                for chunk in page_chunks
            ])
            for raw_text in chunk_results:
                chunk_result = parse_extraction(raw_text, ExtractedFields)
                all_extracted = merge_extractions(all_extracted, chunk_result)
            if all_extracted.has_any_data():
                return ExtractionResult(extracted=all_extracted, transcription=ocr_text)
            logger.warning("OCR text extraction returned no usable fields — falling back to vision AI")
        else:
            logger.warning("OCR produced no text — falling back to vision AI")

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
            logger.error("PDF has %d pages but none could be rendered — file may be encrypted", page_count)
            return ExtractionResult(extracted=ExtractedFields())

        logger.info("Vision fallback: %d pages — extracting in parallel batches", len(page_images))

        BATCH_SIZE = 3
        all_extracted = ExtractedFields()
        for batch_start in range(0, len(page_images), BATCH_SIZE):
            batch = page_images[batch_start:batch_start + BATCH_SIZE]
            page_nums = list(range(batch_start + 1, batch_start + len(batch) + 1))
            logger.info("Extracting pages %s via vision AI...", ", ".join(str(p) for p in page_nums))
            tasks = [
                call_vision_provider_from_b64(b64, "image/jpeg", last_provider_ref)
                for b64 in batch
            ]
            results = await asyncio.gather(*tasks)
            for raw_text in results:
                page_result = parse_extraction(raw_text, ExtractedFields)
                all_extracted = merge_extractions(all_extracted, page_result)

        # Generate transcription for vision-only path
        transcription = await _transcribe_via_vision(page_images, mime_type="image/jpeg")
        return ExtractionResult(extracted=all_extracted, transcription=transcription)

    if mime_type.startswith("image/"):
        # Try local tesseract first (fast, free)
        ocr_text = tesseract_image(file_path)
        if ocr_text:
            logger.info("Image OCR (tesseract) extracted %d chars — using text extraction", len(ocr_text))
            raw_text = await call_text_extraction(ocr_text, last_provider_ref)
            return ExtractionResult(
                extracted=parse_extraction(raw_text, ExtractedFields),
                transcription=ocr_text,
            )

        # Fallback: cloud AI OCR
        ocr_text = await call_ocr(file_path, mime_type)
        if ocr_text:
            raw_text = await call_text_extraction(ocr_text, last_provider_ref)
            return ExtractionResult(
                extracted=parse_extraction(raw_text, ExtractedFields),
                transcription=ocr_text,
            )
        # OCR failed — fall through to vision providers

    # Vision-only path: run extraction and transcription in parallel
    file_bytes = Path(file_path).read_bytes()
    b64_data = base64.b64encode(file_bytes).decode()
    extraction_task = asyncio.create_task(
        call_vision_provider(file_path, mime_type, last_provider_ref)
    )
    transcription_task = asyncio.create_task(
        _transcribe_via_vision([b64_data], mime_type)
    )
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


def ocr_pdf_pages(file_path: str, page_count: int) -> str | None:
    """OCR all pages of a scanned PDF using tesseract.

    Renders each page to an image, runs tesseract OCR, and combines
    the results. Much faster and more reliable than vision AI for
    text-heavy scanned documents.
    """
    import os
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("tesseract"):
        logger.info("Tesseract not installed — skipping OCR")
        return None

    import fitz
    doc = fitz.open(file_path)
    all_text: list[str] = []

    for page_num in range(page_count):
        try:
            page = doc[page_num]
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(img_bytes)
                tmp_path = tmp.name

            result = subprocess.run(
                ["tesseract", tmp_path, "stdout"],
                capture_output=True, text=True, timeout=30,
            )
            os.unlink(tmp_path)

            page_text = result.stdout.strip()
            if page_text:
                all_text.append(f"--- Page {page_num + 1} ---\n{page_text}")
        except Exception as exc:
            logger.warning("OCR failed for page %d: %s", page_num + 1, exc)
            continue

    doc.close()
    combined = "\n\n".join(all_text).strip()
    return combined or None


def tesseract_image(file_path: str) -> str | None:
    """OCR a single image file using tesseract (fast, local)."""
    import shutil
    import subprocess

    if not shutil.which("tesseract"):
        return None

    try:
        result = subprocess.run(
            ["tesseract", file_path, "stdout"],
            capture_output=True, text=True, timeout=15,
        )
        text = result.stdout.strip()
        return text or None
    except Exception as exc:
        logger.debug("Image tesseract OCR failed: %s", exc)
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


TRANSCRIPTION_PROMPT = (
    "Transcribe all text from this document image. "
    "Include ALL handwritten text, printed text, headers, labels, and values. "
    "Preserve the original layout and line breaks as closely as possible. "
    "If any text is partially legible, include your best reading marked with (?). "
    "Return ONLY the raw transcription text, no JSON, no explanations."
)


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


async def call_text_extraction(pdf_text: str, last_provider_ref: list) -> str | None:
    """Send extracted PDF text to an AI model for structured extraction.

    Races all available providers in parallel — first valid result wins.
    last_provider_ref is a mutable list [str] used to track the winning provider.
    """
    prompt = f"{EXTRACTION_PROMPT}\n\nDocument Content:\n{pdf_text[:30000]}"

    providers = [
        (call_openrouter_text, "OpenRouter text"),
        (call_groq_text, "Groq text"),
        (call_gemini_text, "Gemini text"),
        (call_ollama_text, "Ollama text"),
        (call_openai_text, "OpenAI text"),
    ]

    async def _try(fn, label):
        try:
            result = await fn(prompt)
            if result:
                return label, result
        except Exception as exc:
            logger.warning("Text provider %s failed: %s", label, exc)
        return None

    # Race all providers — first valid result wins
    tasks = [asyncio.create_task(_try(fn, label)) for fn, label in providers]
    winner = None
    for coro in asyncio.as_completed(tasks):
        result = await coro
        if result is not None:
            name, text = result
            logger.info("Text extraction succeeded via %s", name)
            last_provider_ref[0] = name
            winner = text
            break

    # Cancel remaining tasks
    for t in tasks:
        if not t.done():
            t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    if winner is None:
        logger.error("All text providers failed for extraction")
    return winner


def merge_extractions(
    base: "ExtractedFields", page: "ExtractedFields"  # noqa: F821
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


def parse_extraction(
    raw_text: str | None, extracted_class: type
) -> "ExtractedFields":  # noqa: F821
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
            raw_text = early[match.start():]
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
        logger.warning("Extraction: could not parse JSON from AI response (first 200 chars: %s)", raw_text[:200] if raw_text else "None")
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
    """Send base64-encoded data to vision-capable AI providers — races all in parallel."""
    providers = [
        (call_openrouter_vision, "_call_openrouter_vision"),
        (call_gemini_vision, "_call_gemini_vision"),
        (call_groq_vision, "_call_groq_vision"),
        (call_ollama_vision, "_call_ollama_vision"),
        (call_openai_vision, "_call_openai_vision"),
    ]
    MAX_RESPONSE_CHARS = 4096

    async def _try(fn, name):
        try:
            result = await fn(b64_data, mime_type, EXTRACTION_PROMPT)
            if result:
                if len(result) > MAX_RESPONSE_CHARS:
                    result = result[:MAX_RESPONSE_CHARS]
                return name, result
        except Exception as exc:
            logger.warning("Vision provider %s failed: %s", name, exc)
        return None

    # Race all providers — first valid result wins
    tasks = [asyncio.create_task(_try(fn, name)) for fn, name in providers]
    winner = None
    for coro in asyncio.as_completed(tasks):
        result = await coro
        if result is not None:
            name, text = result
            logger.info("Vision extraction succeeded via %s", name)
            last_provider_ref[0] = name
            winner = text
            break

    # Cancel remaining tasks
    for t in tasks:
        if not t.done():
            t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    if winner is None:
        logger.error("All vision providers failed for extraction")
    return winner
