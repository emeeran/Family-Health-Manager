"""AI response verification service.

Cross-checks chatbot responses and AI-generated insights against the health
context using a different AI provider than the one that generated the original.
"""
import json
import logging
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.verification import ResponseVerification

logger = logging.getLogger(__name__)

VERIFICATION_PROMPT = """You are a medical data fact-checker. Verify whether the AI assistant's
response about family health records is factually accurate given the provided health context.

CRITICAL RULES:
1. Compare EVERY specific claim in the response against the context data.
2. A claim is "inaccurate" only if it contradicts the context. If the context
   does not contain the information, mark it as "unverifiable" (NOT inaccurate).
3. Pay special attention to:
   - DATE ACCURACY: Does the response use the exact dates from the context?
     Watch for swapped day/month.
   - VALUE ACCURACY: Are numeric values exactly as shown in context?
     Watch for Hb (hemoglobin ~12-17 g/dL) being confused with HbA1c (~4-14%).
   - MEMBER ATTRIBUTION: Are facts attributed to the correct family member?
   - COMPLETENESS: When asked to list all items, does the response include all?
   - FABRICATION: Does the response mention data not present in the context?

HEALTH CONTEXT:
{context}

USER QUESTION:
{question}

AI RESPONSE TO VERIFY:
{response}

Return ONLY valid JSON (no markdown, no code fences) with this exact structure:
{{
  "status": "verified" | "warnings" | "unverifiable",
  "claims_checked": <number>,
  "warnings": [
    {{
      "type": "wrong_date" | "wrong_value" | "wrong_member" | "omission" | "fabrication",
      "claim": "<the inaccurate claim>",
      "correction": "<what the context actually says>",
      "severity": "high" | "medium" | "low"
    }}
  ],
  "summary": "<one sentence overall assessment>"
}}

If all claims are accurate, return status "verified" with empty warnings array.
If the context lacks data to verify, return status "unverifiable".
If any claim is wrong, return status "warnings" with details."""


INSIGHT_VERIFICATION_PROMPT = """Verify this AI health insight against the patient context. Check: correct dates, values (Hb vs HbA1c), member attribution, medication accuracy, and no fabrication.

CRITICAL VERIFICATION CHECKS:
1. MEDICATION-INDICATION ACCURACY: For EACH medication mentioned, verify the AI's stated purpose/indication matches the patient's records. Flag if the AI says a drug is "for diabetes" but the records show it's prescribed for blood pressure (e.g., Metoprolol/Met XL is a beta-blocker for hypertension/heart, NOT for diabetes). If the records do not specify the indication, the AI should say "indication not specified" — flag any guess as a warning.
2. DATE ACCURACY: Exact dates from context, no swapping.
3. VALUE ACCURACY: Numeric values match exactly. Watch for Hb vs HbA1c confusion.
4. COMPLETENESS: When asked to list all items, verify nothing is omitted.
5. FABRICATION: No data mentioned that isn't in the context.

CONTEXT (truncated):
{context}

INSIGHT TO VERIFY:
{insight}

Return ONLY valid JSON:
{{"status": "verified" | "warnings" | "unverifiable", "claims_checked": <n>, "warnings": [{{"type": "wrong_date" | "wrong_value" | "wrong_member" | "wrong_medication" | "fabrication", "claim": "...", "correction": "...", "severity": "high" | "medium" | "low"}}], "summary": "..."}}"""


EXTRACTION_VERIFICATION_PROMPT = """You are a medical data extraction verifier. A second AI already extracted structured data from a medical document. Verify the extraction for accuracy.

CRITICAL RULES:
1. Check that medicine names are plausible and not garbled (especially handwritten ones).
2. Verify dosage format makes sense (e.g., "1-1-1", "500mg", not random strings).
3. Check that the record_type is reasonable given the extracted content.
4. Verify dates are in valid format (YYYY-MM-DD).
5. Look for fabricated prescriptions — medicines that seem invented rather than real drug names.
6. Check if key data might have been missed (obvious prescriptions or lab results).

EXTRACTED DATA:
{extraction}

Return ONLY valid JSON (no markdown, no code fences):
{{
  "status": "verified" | "warnings" | "unverifiable",
  "claims_checked": <number>,
  "warnings": [
    {{
      "type": "wrong_value" | "fabrication" | "omission" | "wrong_date",
      "claim": "<the potentially wrong extracted field>",
      "correction": "<what should be corrected>",
      "severity": "high" | "medium" | "low"
    }}
  ],
  "summary": "<one sentence assessment of extraction quality>"
}}"""


class VerificationService:
    """Verifies AI responses against health context using a different provider."""

    def __init__(self, db: AsyncSession, ai_service: "AIService"):  # noqa: F821
        self.db = db
        self.ai_service = ai_service

    async def verify(
        self,
        question: str,
        ai_response: str,
        health_context: str,
        original_provider: str,
        message_id: UUID,
    ) -> ResponseVerification:
        """Verify an AI response and persist the result."""
        # Create pending record
        verification = ResponseVerification(
            message_id=message_id,
            status="pending",
            verifier_provider="",
        )
        self.db.add(verification)
        await self.db.flush()

        try:
            prompt = VERIFICATION_PROMPT.format(
                context=health_context,
                question=question,
                response=ai_response,
            )

            result_text, provider = await self.ai_service._call_ai_excluding(
                prompt, exclude_provider=original_provider
            )

            verification.verifier_provider = provider
            parsed = self._parse_verification_response(result_text)

            if parsed:
                verification.status = parsed.get("status", "unverifiable")
                verification.claims_checked = parsed.get("claims_checked", 0)
                verification.summary = (parsed.get("summary") or "")[:500]
                warnings = parsed.get("warnings", [])
                verification.warnings_json = json.dumps(warnings) if warnings else None
            else:
                verification.status = "failed"
                verification.summary = "Could not parse verification response"

        except Exception as exc:
            logger.warning("Verification failed for message %s: %s", message_id, exc)
            verification.status = "failed"
            verification.summary = str(exc)[:500]

        await self.db.flush()
        return verification

    async def verify_insight(
        self,
        insight: "AIInsight",  # noqa: F821
        health_context: str,
    ) -> None:
        """Cross-check an AI-generated insight against health context using a different provider.

        Writes verification results directly on the AIInsight record.
        """
        try:
            prompt = INSIGHT_VERIFICATION_PROMPT.format(
                context=health_context[:2000],
                insight=insight.response,
            )

            result_text, provider = await self.ai_service._call_ai_excluding(
                prompt, exclude_provider=insight.provider_used
            )

            insight.verification_verifier = provider
            parsed = self._parse_verification_response(result_text)

            if parsed:
                insight.verification_status = parsed.get("status", "unverifiable")
                insight.verification_claims_checked = parsed.get("claims_checked", 0)
                insight.verification_summary = (parsed.get("summary") or "")[:500]
                warnings = parsed.get("warnings", [])
                insight.verification_warnings_json = (
                    json.dumps(warnings) if warnings else None
                )
            else:
                insight.verification_status = "failed"
                insight.verification_summary = "Could not parse verification response"

        except Exception as exc:
            logger.warning(
                "Insight verification failed for %s: %s", insight.id, exc
            )
            insight.verification_status = "failed"
            insight.verification_summary = str(exc)[:500]

        insight.verification_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def verify_extraction(
        self,
        extracted_fields: dict,
        original_provider: str,
    ) -> dict:
        """Cross-check extraction results using a different AI provider.

        Returns a verification dict with status, warnings, and summary.
        Does NOT persist — extraction results are ephemeral until a record is saved.
        """
        extraction_json = json.dumps(extracted_fields, indent=2, default=str)

        prompt = EXTRACTION_VERIFICATION_PROMPT.format(
            extraction=extraction_json,
        )

        try:
            result_text, provider = await self.ai_service._call_ai_excluding(
                prompt, exclude_provider=original_provider
            )

            parsed = self._parse_verification_response(result_text)
            if parsed:
                parsed["verifier_provider"] = provider
                parsed["verified_at"] = datetime.now(timezone.utc).isoformat()
                return parsed
            else:
                return {
                    "status": "failed",
                    "claims_checked": 0,
                    "warnings": [],
                    "summary": "Could not parse verification response",
                    "verifier_provider": provider,
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                }
        except Exception as exc:
            logger.warning("Extraction verification failed: %s", exc)
            return {
                "status": "failed",
                "claims_checked": 0,
                "warnings": [],
                "summary": str(exc)[:200],
                "verifier_provider": "",
                "verified_at": None,
            }

    @staticmethod
    def _parse_verification_response(raw: str | None) -> dict | None:
        """Parse the structured JSON response from the verifier."""
        if not raw:
            return None

        # Strip markdown fences
        import re
        cleaned = re.sub(r"```json\s*", "", raw)
        cleaned = re.sub(r"```\s*", "", cleaned).strip()

        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            pass

        # Try to find JSON object
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
                            return json.loads(cleaned[start : i + 1])
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break

        return None
