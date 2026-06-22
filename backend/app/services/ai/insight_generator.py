"""Shared AI helpers — drug-interaction checks and NL/search-query parsing.

Insight generation and streaming live on the ``AIService`` facade
(``app/services/ai/__init__.py``); this module holds the prompt-based
helpers the facade delegates to.
"""

import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.document_extractor import strip_markdown_fences

logger = logging.getLogger(__name__)


async def check_drug_interactions(
    db: AsyncSession, medications: list[dict], call_ai_fn
) -> list[dict]:
    """Check drug interactions between a list of medications using AI."""
    if len(medications) < 2:
        return []

    med_list = "\n".join(
        f"{i + 1}. {m.get('medicine', 'Unknown')}"
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


async def parse_natural_language(text: str, member_list: str, call_ai_fn) -> dict:
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
5. Today's date is {datetime.now().strftime("%Y-%m-%d")} -- use it to resolve relative dates like "yesterday", "last week".
6. For glucose/blood sugar mentions, include glucose_value and meal_timing.
7. For vitals mentions (weight, height, BP, heart rate, temperature), include individual fields.
8. For HbA1c mentions, include hba1c_value (percentage).
9. For prescriptions/medicines, populate the prescriptions array (one entry per medicine) AND a prescription_text summary.
10. For lab/test results, populate the lab_tests array (one entry per test) and set record_type to lab_report.
11. For consultations, include chief_complaint and provider_name (doctor name) when mentioned.

RECORD TYPES: doctor_visit, lab_report, rx_eyeglass, blood_glucose, hba1c, vitals, misc_record

Return this JSON:
{{
  "member_name": "matched name or relationship from text, lowercase" or null,
  "record_type": "doctor_visit" or null,
  "record_date": "YYYY-MM-DD" or null,
  "record_time": "HH:MM" or null,
  "diagnosis": "extracted diagnosis" or null,
  "chief_complaint": "main reason for the visit" or null,
  "existing_conditions": "chronic/underlying conditions mentioned" or null,
  "investigations": "tests ordered or recommended" or null,
  "provider_name": "doctor or provider name" or null,
  "prescription_text": "extracted prescriptions text" or null,
  "prescriptions": [
    {{"type": "Tab|Cap|Inj|Syp|Cream|Drops|Inhaler|Other", "medicine": "name", "dosage": "e.g. 1-1-1", "duration": "e.g. 5 days", "timing": "before_food|after_food|with_food|empty_stomach|bedtime|sos|stat", "note": "optional"}}
  ] or null,
  "lab_tests": [
    {{"test_name": "e.g. HbA1c", "result": "e.g. 7.8 %", "ref_value": "e.g. <6.0 %", "note": "e.g. High"}}
  ] or null,
  "clinical_notes": "any other relevant notes" or null,
  "next_review_date": "YYYY-MM-DD" or null,
  "glucose_value": "number" or null,
  "meal_timing": "before_food|after_food" or null,
  "hba1c_value": "number" or null,
  "weight": "value" or null,
  "height": "value in cm" or null,
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


async def parse_search_query(query: str, member_list: str, call_ai_fn) -> dict | None:
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
