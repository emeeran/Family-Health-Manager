"""AI service with multi-provider failover."""
import asyncio
import base64
import json
import logging
import re
from collections.abc import AsyncGenerator
from datetime import date, datetime
from pathlib import Path
from uuid import UUID
import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import AIInsight, HealthRecord, FamilyMember, Message, MessageRole
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

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

_CLINICAL_SYSTEM_NOTE = (
    "You are a senior clinical reviewer AI, functioning as an attending physician "
    "conducting a thorough chart review. Your role is to produce professional clinical "
    "assessment notes.\n\n"
    "WRITING DISCIPLINE:\n"
    "- Write structured clinical assessment prose, not patient-facing summaries.\n"
    "- Use precise medical terminology appropriate for a medical record.\n"
    "- Always cite the specific value, date, or medication name from the patient data "
    "to support every clinical observation.\n"
    "- Follow clinical reasoning: observation → significance → recommendation.\n"
    "- Never state a conclusion without citing the supporting evidence from the provided data.\n"
    "- When comparing values across time, state both the date and the value for each data point.\n"
    "- Use standard clinical abbreviations where appropriate (e.g., T2DM, HTN, BID, TDS, HbA1c).\n\n"
    "EVIDENCE RULES:\n"
    "- Never fabricate lab values, medication dosages, or diagnoses not present in the context.\n"
    "- If data is missing or silent on a topic, write 'insufficient data to assess' rather than speculating.\n"
    "- Do NOT confuse Hemoglobin (Hb) with HbA1c — they are different tests.\n"
    "- Use ONLY the exact dates from the context. Never approximate or guess dates.\n"
    "- Do NOT mix up data between family members — each section is clearly labeled.\n"
    "- Today's date: {today}\n\n"
)


class AIService:
    """AI health intelligence service with provider failover."""

    # Class-level LRU cache — survives across per-request instances
    _member_context_cache: dict[str, str] = {}
    _MAX_CACHE_SIZE = 64

    # Shared httpx clients for connection pooling — reused across all instances
    _cloud_client: httpx.AsyncClient | None = None
    _ollama_client: httpx.AsyncClient | None = None
    _client_lock: asyncio.Lock | None = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Lazy lock to avoid binding to a closed event loop between tests."""
        if cls._client_lock is None:
            cls._client_lock = asyncio.Lock()
        return cls._client_lock

    @classmethod
    async def _get_cloud_client(cls) -> httpx.AsyncClient:
        """Get or create a shared httpx client for cloud AI providers."""
        async with cls._get_lock():
            if cls._cloud_client is None or cls._cloud_client.is_closed:
                cls._cloud_client = httpx.AsyncClient(timeout=60)
            return cls._cloud_client

    @classmethod
    async def _get_ollama_client(cls) -> httpx.AsyncClient:
        """Get or create a shared httpx client for Ollama (longer timeout)."""
        async with cls._get_lock():
            client = cls._ollama_client
            if client is not None and not client.is_closed:
                # Detect dead event loop — client looks open but loop is gone
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop is None or client._transport is None:
                    client = None
            if client is None or client.is_closed:
                cls._ollama_client = httpx.AsyncClient(timeout=300)
            return cls._ollama_client

    @classmethod
    def invalidate_member_cache(cls, member_id: "UUID | str") -> None:
        """Invalidate cached context for a member (call after record changes)."""
        key = str(member_id)
        cls._member_context_cache.pop(key, None)

    @classmethod
    def _put_cache(cls, key: str, value: str) -> None:
        """Store value in LRU cache, evicting half if at capacity."""
        if len(cls._member_context_cache) >= cls._MAX_CACHE_SIZE:
            for old_key in list(cls._member_context_cache.keys())[: cls._MAX_CACHE_SIZE // 2]:
                del cls._member_context_cache[old_key]
        cls._member_context_cache[key] = value

    @classmethod
    def _get_cache(cls, key: str) -> str | None:
        """Retrieve value from LRU cache, or None if not found."""
        return cls._member_context_cache.get(key)

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db
        self.last_provider: str = ""

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

        # Stage 2: Generate — cloud first (more capable), Ollama as fallback
        system_note = _CLINICAL_SYSTEM_NOTE.format(today=self._fmt_date(date.today()))
        full_prompt = f"{system_note}{context}\n\nUser: {prompt}\n\nAssistant:" if context else prompt

        full_response = ""
        provider = ""

        # Preferred: cloud providers (streaming-capable, large context)
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

        # Stage 3: Save to DB
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

        yield sse({"stage": "complete", "insight_id": str(insight.id), "provider": provider})

    async def _ollama_chat_stream(self, model: str, prompt: str) -> AsyncGenerator[str, None]:
        """Stream tokens from local Ollama model."""
        if not settings.OLLAMA_LOCAL_URL:
            return
        url = f"{settings.OLLAMA_LOCAL_URL}/api/chat"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "options": {"num_ctx": 32768},
        }
        client = await self._get_ollama_client()
        async with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done"):
                        return
                except json.JSONDecodeError:
                    continue

    async def _call_ollama_insight(self, prompt: str, context: str) -> tuple[str, str]:
        """Generate insight — races cloud providers in parallel for speed, Ollama as fallback."""
        system_note = _CLINICAL_SYSTEM_NOTE.format(today=self._fmt_date(date.today()))
        full_prompt = f"{system_note}{context}\n\nUser: {prompt}\n\nAssistant:" if context else prompt

        # Race cloud providers in parallel — OpenRouter DeepSeek first
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

        # Fallback: try Ollama models — prefer capable cloud-routed models
        ollama_models = [("gemma4:31b-cloud", "Ollama gemma4:31b-cloud")]
        ollama_models.append((settings.OLLAMA_MODEL, f"Ollama {settings.OLLAMA_MODEL}"))
        ollama_models.append((settings.OLLAMA_TEXT_MODEL, f"Ollama {settings.OLLAMA_TEXT_MODEL}"))
        for model, label in ollama_models:
            try:
                result = await self._ollama_chat(model, full_prompt)
                if result:
                    return result, label
            except Exception as exc:
                logger.warning("Ollama model %s failed: %s", label, exc)

        raise ValueError("All AI providers failed for insight generation")

    async def _race_providers(
        self, prompt: str, providers: list[tuple]
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

    async def _ollama_chat(self, model: str, prompt: str) -> str | None:
        """Call local Ollama with a specific model."""
        if not settings.OLLAMA_LOCAL_URL:
            return None
        url = f"{settings.OLLAMA_LOCAL_URL}/api/chat"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        try:
            client = await self._get_ollama_client()
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content")
        except Exception:
            # Reset shared client on failure — connection pool may be corrupted
            if cls_client := self._ollama_client:
                try:
                    await cls_client.aclose()
                except Exception:
                    pass
                self.__class__._ollama_client = None
            raise

    async def _build_member_context(self, member_id: UUID, comprehensive: bool = False) -> str:
        """Build comprehensive medical history context for AI prompt."""
        result = await self.db.execute(
            select(FamilyMember).where(FamilyMember.id == member_id)
        )
        member = result.scalar_one_or_none()
        if not member:
            return ""

        # --- Patient Profile ---
        today = date.today()
        age = today.year - member.date_of_birth.year - (
            (today.month, today.day) < (member.date_of_birth.month, member.date_of_birth.day)
        )
        context = f"Patient: {member.first_name} {member.last_name} (Age: {age})\n"
        context += f"Date of Birth: {self._fmt_date(member.date_of_birth)}\n"
        context += f"Gender: {member.gender.value}\n"

        if member.blood_group:
            context += f"Blood Group: {member.blood_group}\n"

        # Physical metrics + BMI
        if member.height_cm and member.weight_kg and member.height_cm > 0:
            hm = member.height_cm / 100
            bmi = round(member.weight_kg / (hm * hm), 1)
            context += f"Height: {member.height_cm} cm, Weight: {member.weight_kg} kg, BMI: {bmi}\n"
        elif member.height_cm:
            context += f"Height: {member.height_cm} cm\n"
        elif member.weight_kg:
            context += f"Weight: {member.weight_kg} kg\n"

        # Allergies
        if member.allergies_json:
            try:
                allergies = json.loads(member.allergies_json)
                if isinstance(allergies, list) and allergies:
                    allergy_lines = []
                    for a in allergies:
                        if isinstance(a, dict):
                            name = a.get("name") or a.get("allergy") or ""
                            severity = a.get("severity") or a.get("reaction") or ""
                            line = name
                            if severity:
                                line += f" ({severity})"
                            if line:
                                allergy_lines.append(line)
                        elif isinstance(a, str) and a:
                            allergy_lines.append(a)
                    if allergy_lines:
                        context += f"Allergies: {'; '.join(allergy_lines)}\n"
            except (json.JSONDecodeError, ValueError):
                pass

        if member.medical_history_summary:
            context += f"Medical History: {member.medical_history_summary}\n"
        if member.family_history:
            context += f"Family Medical History: {member.family_history}\n"

        # --- Health Records ---
        query = (
            select(HealthRecord)
            .options(selectinload(HealthRecord.provider))
            .where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc())
        )
        query = query.limit(20 if comprehensive else 5)

        recent = await self.db.execute(query)
        records = list(recent.scalars().all())

        # Aggregate across records for summary sections
        all_diagnoses: list[str] = []
        all_providers: list[str] = []
        overdue_followups: list[str] = []

        if records:
            label = "All Health Records" if comprehensive else "Recent Records"
            context += f"\n{label} ({len(records)} records):\n"
            for r in records:
                # Track diagnoses
                if r.diagnosis and r.diagnosis.strip():
                    all_diagnoses.append(r.diagnosis.strip())

                # Track providers
                if r.provider_name and r.provider_name.strip():
                    pname = r.provider_name.strip()
                    if pname not in all_providers:
                        all_providers.append(pname)

                # Track overdue follow-ups
                if r.next_review_date and r.next_review_date < today:
                    overdue_followups.append(
                        f"[{self._fmt_date(r.next_review_date)}] {r.record_type.value}"
                        + (f" — {r.diagnosis}" if r.diagnosis else "")
                    )

                rec_line = f"- [{self._fmt_date(r.record_date)}] {r.record_type.value}"
                if r.diagnosis:
                    rec_line += f" — {r.diagnosis}"
                summary = self._summarize_clinical_data(r.clinical_data)
                if summary:
                    rec_line += f"\n  {summary[:500]}"
                if r.prescription_text:
                    rec_line += f"\n  Rx: {r.prescription_text[:300]}"
                if r.provider_name:
                    rec_line += f"\n  Provider: {r.provider_name}"
                if r.next_review_date:
                    rec_line += f"\n  Next Review: {self._fmt_date(r.next_review_date)}"
                context += rec_line + "\n"

        # --- Aggregated Summary Sections ---

        # All diagnoses (deduplicated)
        unique_diagnoses = list(dict.fromkeys(all_diagnoses))
        if unique_diagnoses:
            context += f"\n=== ALL DIAGNOSES ({len(unique_diagnoses)}) ===\n"
            for d in unique_diagnoses:
                context += f"  - {d}\n"

        # All providers
        if all_providers:
            context += f"\n=== PROVIDERS ({len(all_providers)}) ===\n"
            for p in all_providers:
                context += f"  - {p}\n"

        # Overdue follow-ups
        if overdue_followups:
            context += f"\n=== OVERDUE FOLLOW-UPS ({len(overdue_followups)}) ===\n"
            for f in overdue_followups:
                context += f"  - {f}\n"

        # Aggregate ALL medications across ALL records (not limited by record cap)
        med_summary = await self._build_medication_summary(member_id)
        if med_summary:
            context += f"\n{med_summary}\n"

        # Key lab trends
        if records:
            lab_trends = self._build_lab_trends_from_records(records)
            if lab_trends:
                context += lab_trends

        return context

    async def _build_medication_summary(self, member_id: UUID) -> str:
        """Aggregate all medications for a member using MedicationService + prescription_text."""
        from app.services.medication_service import MedicationService

        med_svc = MedicationService(self.db)
        all_meds: dict[str, str] = {}  # normalized_name -> formatted line

        # 1. Use MedicationService for structured, deduplicated active medications
        try:
            active_meds = await med_svc.get_active_medications(member_id)
            for med in active_meds:
                name = med.get("medicine", "").strip()
                if not name:
                    continue
                key = name.strip().lower().split()[0]
                dtype = med.get("type", "")
                dosage = med.get("dosage", "")
                timing = med.get("timing", "")
                line = f"{dtype} {name} {dosage}".strip()
                if timing:
                    line += f" ({timing})"
                status = med.get("status", "")
                if status:
                    line += f" [{status}]"
                all_meds[key] = line
        except Exception as exc:
            logger.warning("MedicationService failed for summary: %s", exc)

        # 2. Also scan ALL records for prescriptions in clinical_data (catches non-doctor_visit)
        result = await self.db.execute(
            select(HealthRecord.clinical_data, HealthRecord.prescription_text)
            .where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.is_deleted.is_(False),
            )
        )
        for clinical_data, prescription_text in result.all():
            # Structured prescriptions from ANY record type
            if clinical_data:
                try:
                    data = json.loads(clinical_data)
                    if isinstance(data, dict):
                        rx = data.get("prescriptions")
                        if rx and isinstance(rx, list):
                            for p in rx:
                                if not isinstance(p, dict):
                                    continue
                                med_name = (p.get("medicine") or "").strip()
                                if not med_name:
                                    continue
                                key = med_name.strip().lower().split()[0]
                                if key in all_meds:
                                    continue
                                dtype = p.get("type", "")
                                dosage = p.get("dosage", "")
                                timing = p.get("timing", "")
                                line = f"{dtype} {med_name} {dosage}".strip()
                                if timing:
                                    line += f" ({timing})"
                                all_meds[key] = line
                except (json.JSONDecodeError, ValueError):
                    pass

            # Free-text prescriptions (handle multiple separators)
            if prescription_text:
                import re as _re
                for line in _re.split(r"[;\n]+", prescription_text):
                    line = line.strip()
                    if not line or len(line) < 3:
                        continue
                    key = line.lower().split()[0] if line.split() else ""
                    if key and key not in all_meds:
                        all_meds[key] = line

        if not all_meds:
            return ""

        lines = [f"=== ALL CURRENT MEDICATIONS ({len(all_meds)} medications) ==="]
        for med_line in sorted(all_meds.values()):
            lines.append(f"  - {med_line}")
        return "\n".join(lines)

    async def _build_household_context(self, household_id: UUID) -> str:
        """Build health context for an entire household (all members + recent records)."""
        # Fetch all active members
        members_result = await self.db.execute(
            select(FamilyMember).where(
                FamilyMember.household_id == household_id,
            )
        )
        members = list(members_result.scalars().all())

        if not members:
            return ""

        # Single query for all members' records (avoids N+1)
        member_ids = [m.id for m in members]
        all_records_result = await self.db.execute(
            select(HealthRecord)
            .where(
                HealthRecord.family_member_id.in_(member_ids),
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc())
            .limit(200)
        )
        all_records = list(all_records_result.scalars().all())

        # Group records by member
        records_by_member: dict[UUID, list[HealthRecord]] = {}
        for r in all_records:
            records_by_member.setdefault(r.family_member_id, []).append(r)

        context = "=== FAMILY HEALTH SUMMARY ===\n\n"

        for member in members:
            context += f"--- {member.first_name} {member.last_name} ---\n"
            context += f"DOB: {self._fmt_date(member.date_of_birth)}\n"
            context += f"Gender: {member.gender.value}\n"
            if member.medical_history_summary:
                context += f"Conditions: {member.medical_history_summary}\n"
            if member.blood_group:
                context += f"Blood Group: {member.blood_group}\n"

            records = records_by_member.get(member.id, [])[:15]
            if records:
                context += f"Records ({len(records)}):\n"
                for r in records:
                    rec_line = f"  [{self._fmt_date(r.record_date)}] {r.record_type.value}"
                    if r.diagnosis:
                        rec_line += f" — {r.diagnosis}"
                    summary = self._summarize_clinical_data(r.clinical_data)
                    if summary:
                        rec_line += f"\n    {summary[:200]}"
                    if r.prescription_text:
                        rec_line += f"\n    Rx: {r.prescription_text[:150]}"
                    context += rec_line + "\n"
            context += "\n"

        # Key Lab Trends — extract HbA1c, glucose, cholesterol across ALL records
        context += self._build_lab_trends_from_records(all_records)

        return context

    @staticmethod
    def _build_lab_trends_from_records(records: list) -> str:
        """Build a summary of key lab test trends from pre-fetched records (no DB queries)."""
        KEY_TESTS = {
            "hba1c": "HbA1c",
            "hb a1c": "HbA1c",
            "glycosylated": "HbA1c",
            "fasting glucose": "Fasting Glucose",
            "postprandial": "Postprandial Glucose",
            "total cholesterol": "Total Cholesterol",
            "ldl cholesterol": "LDL Cholesterol",
            "hdl cholesterol": "HDL Cholesterol",
            "triglyceride": "Triglycerides",
        }

        trends: dict[str, list[tuple[str, str, str]]] = {}

        for r in records:
            if not r.clinical_data:
                continue
            try:
                data = json.loads(r.clinical_data)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            for key in ("tests", "lab_results"):
                for t in data.get(key, []) or []:
                    if not isinstance(t, dict):
                        continue
                    name = (t.get("test_name") or "").lower()
                    result = str(t.get("result", ""))
                    note = t.get("note", "")
                    for kw, canonical in KEY_TESTS.items():
                        if kw in name:
                            date_str = str(r.record_date)
                            trends.setdefault(canonical, []).append(
                                (date_str, result, note)
                            )
                            break

        if not trends:
            return ""

        lines = ["\n=== KEY LAB TRENDS (all dates) ==="]
        for test_name, entries in sorted(trends.items()):
            lines.append(f"\n{test_name}:")
            for date_str, result, note in entries:
                line = f"  {date_str}: {result}"
                if note:
                    line += f" ({note})"
                lines.append(line)

        return "\n".join(lines) + "\n"

    @staticmethod
    def _summarize_clinical_data(raw: str | None) -> str:
        """Extract key information from structured clinical JSON for AI context."""
        if not raw:
            return ""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return f"Data: {raw[:500]}"

        if not isinstance(data, dict) or data.get("_type") != "structured":
            return f"Data: {raw[:500]}"

        parts: list[str] = []

        # Chief complaint
        if data.get("chief_complaint"):
            parts.append(f"Complaint: {data['chief_complaint']}")

        # Existing conditions
        if data.get("existing_conditions"):
            parts.append(f"Existing Conditions: {data['existing_conditions']}")

        # Lab tests / results (from both 'tests' and 'lab_results' keys)
        for key in ("tests", "lab_results"):
            tests = data.get(key)
            if tests and isinstance(tests, list):
                for t in tests:
                    if not isinstance(t, dict):
                        continue
                    name = t.get("test_name", "")
                    result = t.get("result", "")
                    ref = t.get("ref_value", "")
                    note = t.get("note", "")
                    line = f"{name}: {result}"
                    if ref:
                        line += f" (ref: {ref})"
                    if note:
                        line += f" — {note}"
                    parts.append(line)

        # Prescriptions (from structured clinical_data)
        rx = data.get("prescriptions")
        if rx and isinstance(rx, list):
            rx_items = []
            for p in rx:
                if not isinstance(p, dict):
                    continue
                med = p.get("medicine", "")
                dtype = p.get("type", "")
                dosage = p.get("dosage", "")
                timing = p.get("timing", "")
                note = p.get("note", "")
                line = f"{dtype} {med} {dosage}".strip()
                if timing:
                    line += f" ({timing})"
                if note:
                    line += f" [{note}]"
                rx_items.append(line)
            if rx_items:
                parts.append("Prescriptions: " + "; ".join(rx_items))

        # Investigations
        if data.get("investigations"):
            parts.append(f"Investigations: {data['investigations']}")

        # Clinical notes (free text)
        if data.get("clinical_data"):
            parts.append(f"Notes: {str(data['clinical_data'])[:200]}")

        return "\n    ".join(parts)

    async def _build_record_context(self, record_id: UUID) -> str:
        """Build context from health record."""
        result = await self.db.execute(
            select(HealthRecord).where(HealthRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            return ""

        context = f"\nHealth Record ({record.record_type.value}):\n"
        context += f"Date: {self._fmt_date(record.record_date)}\n"
        context += f"Data: {(record.clinical_data or '')[:500]}\n"
        if record.diagnosis:
            context += f"Diagnosis: {record.diagnosis}\n"
        return context

    @staticmethod
    def _fmt_date(d: object) -> str:
        """Format a date for AI context in an unambiguous, human-readable way."""
        if d is None:
            return "N/A"
        s = str(d)
        try:
            parsed = datetime.strptime(s[:10], "%Y-%m-%d")
            return parsed.strftime("%d-%b-%Y")  # e.g. "09-Apr-2026"
        except (ValueError, TypeError):
            return s

    async def _call_ai(self, prompt: str, context: str) -> tuple[str, str]:
        """Call AI provider with failover chain for text-based chat/insights."""
        system_note = _CLINICAL_SYSTEM_NOTE.format(today=self._fmt_date(date.today()))
        full_prompt = f"{system_note}{context}\n\nUser: {prompt}\n\nAssistant:" if context else prompt

        providers = [
            (self._call_openrouter_text, "OpenRouter DeepSeek V4 Flash"),
            (self._call_groq_text, "Groq Llama-4-Scout"),
            (self._call_gemini_text, "Google Gemini 2.5 Flash"),
            (self._call_ollama_text, "Ollama (local)"),
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
        """Call AI provider with failover, skipping the provider that generated the original response."""
        providers = [
            (self._call_openrouter_text, "OpenRouter DeepSeek V4 Flash"),
            (self._call_groq_text, "Groq Llama-4-Scout"),
            (self._call_gemini_text, "Google Gemini 2.5 Flash"),
            (self._call_ollama_text, "Ollama (local)"),
            (self._call_openrouter_text, "OpenRouter DeepSeek V4 Flash"),
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

    async def _call_groq_text(self, prompt: str) -> str | None:
        """Call Groq API for text-based generation."""
        if not settings.GROQ_API_KEY:
            return None
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        client = await self._get_cloud_client()
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _call_openrouter_text(self, prompt: str) -> str | None:
        """Call OpenRouter API for text-based generation."""
        if not settings.OPENROUTER_API_KEY:
            return None
        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {
            "model": "deepseek/deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        client = await self._get_cloud_client()
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def classify_document(self, file_path: str, mime_type: str) -> "RecordType":  # noqa: F821
        """Classify a document into a record type using AI with keyword fallback."""
        from app.models.base import RecordType

        # Try to get text content first
        text = ""
        if mime_type == "application/pdf":
            text = self._extract_pdf_text(file_path) or ""

        # Try AI classification
        classification_prompt = (
            "Classify this medical document into exactly one category. "
            "Return ONLY one of these words: doctor_visit, lab_report, rx_eyeglass, blood_glucose, misc_record\n\n"
            f"Document content (first 1000 chars):\n{text[:1000]}"
        )
        try:
            response, _ = await self._call_ai(classification_prompt, "")
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
        self, file_path: str, mime_type: str
    ) -> "ExtractedFields":  # noqa: F821
        """Extract structured medical data from a document file via vision AI."""
        from app.schemas.health_record import ExtractedFields

        if mime_type == "application/pdf":
            pdf_text = self._extract_pdf_text(file_path)
            if pdf_text:
                logger.info("PDF has embedded text (%d chars) — using fast text extraction", len(pdf_text))
                raw_text = await self._call_text_extraction(pdf_text)
                result = self._parse_extraction(raw_text, ExtractedFields)
                if not result.has_any_data():
                    logger.warning("PDF text extraction returned no usable fields — text may be non-medical or too short")
                return result

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
                    return ExtractedFields()
                logger.info("PDF has %d pages", page_count)
            except Exception as exc:
                logger.error("Cannot open PDF: %s", exc)
                return ExtractedFields()

            # Step 1: Render pages and OCR with tesseract (fast, local)
            ocr_text = self._ocr_pdf_pages(file_path, page_count)

            if ocr_text:
                logger.info("OCR extracted %d chars from %d pages — using text extraction", len(ocr_text), page_count)
                # Chunk OCR text by page markers to keep prompts small for local models
                page_chunks = self._chunk_ocr_text(ocr_text, pages_per_chunk=3)
                all_extracted = ExtractedFields()
                for i, chunk in enumerate(page_chunks):
                    logger.info("Extracting OCR chunk %d/%d (%d chars)...", i + 1, len(page_chunks), len(chunk))
                    raw_text = await self._call_text_extraction(chunk[:10000])
                    chunk_result = self._parse_extraction(raw_text, ExtractedFields)
                    all_extracted = self._merge_extractions(all_extracted, chunk_result)
                if all_extracted.has_any_data():
                    return all_extracted
                logger.warning("OCR text extraction returned no usable fields — falling back to vision AI")
            else:
                logger.warning("OCR produced no text — falling back to vision AI")

            # Step 2: Vision AI fallback (slow, requires working provider)
            page_images: list[str] = []
            page_num = 0
            while True:
                img_bytes = self._pdf_page_to_image(file_path, page_num=page_num)
                if not img_bytes:
                    break
                page_images.append(base64.b64encode(img_bytes).decode())
                page_num += 1

            if not page_images:
                logger.error("PDF has %d pages but none could be rendered — file may be encrypted", page_count)
                return ExtractedFields()

            logger.info("Vision fallback: %d pages — extracting in parallel batches", len(page_images))

            BATCH_SIZE = 3
            all_extracted = ExtractedFields()
            for batch_start in range(0, len(page_images), BATCH_SIZE):
                batch = page_images[batch_start:batch_start + BATCH_SIZE]
                page_nums = list(range(batch_start + 1, batch_start + len(batch) + 1))
                logger.info("Extracting pages %s via vision AI...", ", ".join(str(p) for p in page_nums))
                tasks = [
                    self._call_vision_provider_from_b64(b64, "image/jpeg")
                    for b64 in batch
                ]
                results = await asyncio.gather(*tasks)
                for raw_text in results:
                    page_result = self._parse_extraction(raw_text, ExtractedFields)
                    all_extracted = self._merge_extractions(all_extracted, page_result)

            return all_extracted

        if mime_type.startswith("image/"):
            # Try local tesseract first (fast, free)
            ocr_text = self._tesseract_image(file_path)
            if ocr_text:
                logger.info("Image OCR (tesseract) extracted %d chars — using text extraction", len(ocr_text))
                raw_text = await self._call_text_extraction(ocr_text)
                return self._parse_extraction(raw_text, ExtractedFields)

            # Fallback: cloud AI OCR
            ocr_text = await self._call_ocr(file_path, mime_type)
            if ocr_text:
                raw_text = await self._call_text_extraction(ocr_text)
                return self._parse_extraction(raw_text, ExtractedFields)
            # OCR failed — fall through to vision providers

        raw_text = await self._call_vision_provider(file_path, mime_type)
        return self._parse_extraction(raw_text, ExtractedFields)

    async def _call_ocr(self, file_path: str, mime_type: str) -> str | None:
        """Use vision AI to OCR an image to text. Prefers Google Gemini."""
        file_bytes = Path(file_path).read_bytes()
        b64_data = base64.b64encode(file_bytes).decode()

        ocr_prompt = "Transcribe all the text in this document, including any handwritten text. Return ONLY the raw text, nothing else."

        # Try Gemini first
        if settings.GEMINI_API_KEY:
            try:
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/"
                    "models/gemini-2.5-flash:generateContent"
                )
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": ocr_prompt},
                            {"inline_data": {"mime_type": mime_type, "data": b64_data}},
                        ]
                    }],
                    "generationConfig": {"temperature": 0.1},
                }
                client = await self._get_cloud_client()
                resp = await client.post(url, json=payload, headers={"x-goog-api-key": settings.GEMINI_API_KEY})
                resp.raise_for_status()
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as exc:
                logger.warning("Gemini OCR failed: %s", exc)

        # Fallback to Ollama (local vision)
        if settings.OLLAMA_LOCAL_URL:
            try:
                url = f"{settings.OLLAMA_LOCAL_URL}/api/chat"
                payload = {
                    "model": settings.OLLAMA_MODEL,
                    "messages": [{
                        "role": "user",
                        "content": ocr_prompt,
                        "images": [b64_data],
                    }],
                    "stream": False,  # type: ignore[dict-item]
                    "options": {"num_ctx": 8192},
                }
                client = await self._get_ollama_client()
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("message", {}).get("content")
            except Exception as exc:
                logger.warning("Ollama OCR failed: %s", exc)

        return None

    @staticmethod
    def _extract_pdf_text(file_path: str) -> str | None:
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

    @staticmethod
    def _chunk_ocr_text(ocr_text: str, pages_per_chunk: int = 3) -> list[str]:
        """Split OCR text (with '--- Page N ---' markers) into chunks."""
        import re
        pages = re.split(r"(?=--- Page \d+ ---)", ocr_text)
        pages = [p.strip() for p in pages if p.strip()]
        chunks: list[str] = []
        for i in range(0, len(pages), pages_per_chunk):
            chunk = "\n\n".join(pages[i : i + pages_per_chunk])
            if chunk:
                chunks.append(chunk)
        return chunks if chunks else [ocr_text]

    @staticmethod
    def _ocr_pdf_pages(file_path: str, page_count: int) -> str | None:
        """OCR all pages of a scanned PDF using tesseract.

        Renders each page to an image, runs tesseract OCR, and combines
        the results. Much faster and more reliable than vision AI for
        text-heavy scanned documents.
        """
        import os
        import subprocess
        import tempfile
        import shutil

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

    @staticmethod
    def _tesseract_image(file_path: str) -> str | None:
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

    @staticmethod
    def _pdf_page_to_image(file_path: str, page_num: int = 0) -> bytes | None:
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

    async def _call_text_extraction(self, pdf_text: str) -> str | None:
        """Send extracted PDF text to an AI model for structured extraction.

        Races all available providers in parallel — first valid result wins.
        """
        prompt = f"{EXTRACTION_PROMPT}\n\nDocument Content:\n{pdf_text[:30000]}"

        providers = [
            (self._call_openrouter_text, "OpenRouter text"),
            (self._call_groq_text, "Groq text"),
            (self._call_gemini_text, "Gemini text"),
            (self._call_ollama_text, "Ollama text"),
            (self._call_openai_text, "OpenAI text"),
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
                self.last_provider = name
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

    async def _call_openai_text(self, prompt: str) -> str | None:
        """Call OpenAI chat completions for text-based extraction."""
        if not settings.OPENAI_API_KEY:
            return None
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        client = await self._get_cloud_client()
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _call_gemini_text(self, prompt: str) -> str | None:
        """Call Google Gemini for text-based extraction."""
        if not settings.GEMINI_API_KEY:
            return None
        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            "models/gemini-2.5-flash:generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }
        client = await self._get_cloud_client()
        resp = await client.post(url, json=payload, headers={"x-goog-api-key": settings.GEMINI_API_KEY})
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    async def _call_vision_provider(
        self, file_path: str, mime_type: str
    ) -> str | None:
        """Send document to vision-capable AI provider with failover."""
        file_bytes = Path(file_path).read_bytes()
        b64_data = base64.b64encode(file_bytes).decode()
        return await self._call_vision_provider_from_b64(b64_data, mime_type)

    async def _call_vision_provider_from_b64(
        self, b64_data: str, mime_type: str
    ) -> str | None:
        """Send base64-encoded data to vision-capable AI providers — races all in parallel."""
        providers = [
            self._call_openrouter_vision,
            self._call_gemini_vision,
            self._call_groq_vision,
            self._call_ollama_vision,
            self._call_openai_vision,
        ]
        MAX_RESPONSE_CHARS = 4096

        async def _try(fn):
            try:
                result = await fn(b64_data, mime_type)
                if result:
                    if len(result) > MAX_RESPONSE_CHARS:
                        result = result[:MAX_RESPONSE_CHARS]
                    return fn.__name__, result
            except Exception as exc:
                logger.warning("Vision provider %s failed: %s", fn.__name__, exc)
            return None

        # Race all providers — first valid result wins
        tasks = [asyncio.create_task(_try(fn)) for fn in providers]
        winner = None
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result is not None:
                name, text = result
                logger.info("Vision extraction succeeded via %s", name)
                self.last_provider = name
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

    async def _call_gemini_vision(
        self, b64_data: str, mime_type: str
    ) -> str | None:
        """Call Google Gemini API for vision extraction."""
        if not settings.GEMINI_API_KEY:
            return None
        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            "models/gemini-2.5-flash:generateContent"
        )
        payload = {
            "contents": [{
                "parts": [
                    {"text": EXTRACTION_PROMPT},
                    {"inline_data": {"mime_type": mime_type, "data": b64_data}},
                ]
            }],
            "generationConfig": {"temperature": 0.1},
        }
        client = await self._get_cloud_client()
        resp = await client.post(url, json=payload, headers={"x-goog-api-key": settings.GEMINI_API_KEY})
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    async def _call_openai_vision(
        self, b64_data: str, mime_type: str
    ) -> str | None:
        """Call OpenAI API for vision extraction."""
        if not settings.OPENAI_API_KEY:
            return None
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime_type};base64,{b64_data}",
                    }},
                ],
            }],
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        client = await self._get_cloud_client()
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _call_groq_vision(
        self, b64_data: str, mime_type: str
    ) -> str | None:
        """Call Groq API for vision extraction."""
        if not settings.GROQ_API_KEY:
            return None
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime_type};base64,{b64_data}",
                    }},
                ],
            }],
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        client = await self._get_cloud_client()
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _call_openrouter_vision(
        self, b64_data: str, mime_type: str
    ) -> str | None:
        """Call OpenRouter API for vision extraction."""
        if not settings.OPENROUTER_API_KEY:
            return None
        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {
            "model": "google/gemini-2.5-flash-preview:thinking",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime_type};base64,{b64_data}",
                    }},
                ],
            }],
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        client = await self._get_cloud_client()
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _call_ollama_vision(
        self, b64_data: str, mime_type: str
    ) -> str | None:
        """Call local Ollama API for vision extraction."""
        if not settings.OLLAMA_LOCAL_URL:
            return None
        url = f"{settings.OLLAMA_LOCAL_URL}/api/chat"
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [{
                "role": "user",
                "content": EXTRACTION_PROMPT,
                "images": [b64_data],
            }],
            "stream": False,
            "options": {"num_ctx": 8192},
        }
        try:
            client = await self._get_ollama_client()
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content")
        except (httpx.TimeoutException, httpx.ConnectError):
            return None

    async def _call_ollama_text(self, prompt: str) -> str | None:
        """Call local Ollama API for text generation — uses lighter model."""
        if not settings.OLLAMA_LOCAL_URL:
            return None
        url = f"{settings.OLLAMA_LOCAL_URL}/api/chat"
        payload = {
            "model": settings.OLLAMA_TEXT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"num_ctx": 8192},
        }
        client = await self._get_ollama_client()
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        if not content or not content.strip():
            logger.warning("Ollama text (%s) returned empty content", settings.OLLAMA_TEXT_MODEL)
            return None
        return content

    def _merge_extractions(
        self, base: "ExtractedFields", page: "ExtractedFields"  # noqa: F821
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

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Remove markdown code fences from AI response text."""
        cleaned = re.sub(r"```json\s*", "", text)
        return re.sub(r"```\s*", "", cleaned).strip()

    def _parse_extraction(
        self, raw_text: str | None, extracted_class: type
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
        cleaned = self._strip_markdown_fences(raw_text)

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

    async def chat_stream(
        self,
        conversation_id: UUID,
        user_message: str,
        member_id: UUID | None = None,
        household_id: UUID | None = None,
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
        self.db.add(user_msg)
        await self.db.flush()

        yield sse({
            "stage": "user_message",
            "id": str(user_msg.id),
            "content": user_message,
            "created_at": user_msg.created_at.isoformat(),
        })

        # Build health context
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

        # Try Ollama streaming first
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

        # Fallback: other Ollama models
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

        # Fallback: cloud providers (non-streaming, sent as single token)
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

        # Save assistant message
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
        """Send message and get AI response with conversation history.

        Returns (user_msg, assistant_msg, provider, health_context).
        """
        user_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=user_message,
        )
        self.db.add(user_msg)
        await self.db.flush()

        history = await self._get_conversation_history(conversation_id, limit=10)

        # Build health context — member-specific or full household
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

    async def check_drug_interactions(
        self, medications: list[dict]
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

IMPORTANT: Return ONLY valid JSON — no markdown, no explanation, no code fences.

Return a JSON array of interactions found. Each interaction object must have:
- "drugs": array of the two drug names involved (strings)
- "severity": one of "high", "moderate", "low"
- "description": brief clinical description of the interaction (1-2 sentences)
- "recommendation": what the prescribing doctor should consider (1 sentence)

If there are no clinically significant interactions, return an empty array: []

Focus only on well-documented, clinically meaningful interactions. Do not flag trivial or theoretical risks."""

        response, _provider = await self._call_ai(prompt, "")

        # Parse the JSON response
        if not response:
            return []

        try:
            # Strip markdown fences
            cleaned = self._strip_markdown_fences(response)

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

    async def _get_conversation_history(self, conversation_id: UUID, limit: int = 10) -> str:
        """Get recent conversation history."""
        result = await self.db.execute(
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

    async def parse_natural_language(self, text: str, member_list: str) -> dict:
        """Parse natural language health text into structured record data."""
        prompt = f"""You are a health data extraction assistant. Parse the following natural language input into structured health record fields.

FAMILY MEMBERS:
{member_list}

USER INPUT: "{text}"

INSTRUCTIONS:
1. Return ONLY valid JSON — no markdown, no explanation, no code fences.
2. Identify which family member the record is for using name or relationship (dad, mom, son, etc.).
3. Determine the record type from context.
4. Extract any relevant health data.
5. Today's date is {datetime.now().strftime('%Y-%m-%d')} — use it to resolve relative dates like "yesterday", "last week".
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
            response, _ = await self._call_ai(prompt, "")
            if not response:
                return {}
            cleaned = self._strip_markdown_fences(response)
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("NL parse failed: %s", exc)
            return {}

    async def parse_search_query(self, query: str, member_list: str) -> dict | None:
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
- Keep it simple — return null for fields you can't determine"""

        try:
            response, _ = await self._call_ai(prompt, "")
            if not response:
                return None
            cleaned = self._strip_markdown_fences(response)
            parsed = json.loads(cleaned)
            # Remove null values
            return {k: v for k, v in parsed.items() if v is not None}
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Search query parse failed: %s", exc)
            return None
