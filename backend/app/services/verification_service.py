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


DDI_VERIFICATION_PROMPT = """You are a clinical pharmacist fact-checker. Another AI generated a list of drug-drug
interactions for a patient's medication list. Verify each interaction.

CRITICAL CHECKS:
1. FABRICATION: Every interaction must involve two drugs that are ACTUALLY in the
   medication list below. Flag any interaction that names a drug the patient is
   not taking as fabrication.
2. SEVERITY ACCURACY: Is the stated severity (high/moderate/low) clinically
   reasonable for that drug pair? Flag gross miscategorizations.
3. DRUG IDENTITY: Watch for the same drug listed twice under different names, or
   a generic/brand confusion that invents a pair.
4. OMISSION: Only flag a MISSED major interaction if it is well-documented and
   clinically significant (do not invent theoretical risks).

MEDICATION LIST:
{medications}

AI-GENERATED INTERACTIONS TO VERIFY:
{interactions}

Return ONLY valid JSON (no markdown, no code fences):
{{
  "status": "verified" | "warnings" | "unverifiable",
  "claims_checked": <number>,
  "warnings": [
    {{
      "type": "fabrication" | "wrong_value" | "omission",
      "claim": "<the suspect interaction>",
      "correction": "<what the medication list actually supports>",
      "severity": "high" | "medium" | "low"
    }}
  ],
  "summary": "<one sentence assessment>"
}}"""


TRANSCRIPTION_VERIFICATION_PROMPT = """You are a medical transcription fact-checker. Another AI produced a formal
"Medical Records Transcription Report" from the structured data below. Verify the
report against that source data.

CRITICAL CHECKS:
1. FABRICATION: Every medication, dosage, lab value, date, and diagnosis in the
   report must come from the source data. Flag anything invented or not present.
2. VALUE ACCURACY: Numeric values, units, and dates must match the source exactly.
3. MEMBER/PROVIDER ATTRIBUTION: Demographics and provider details must match.
4. OMISSION: Flag only clearly-important source data that the report dropped.

SOURCE EXTRACTED DATA:
{extracted_data}

AI-GENERATED TRANSCRIPTION REPORT:
{report}

Return ONLY valid JSON (no markdown, no code fences):
{{
  "status": "verified" | "warnings" | "unverifiable",
  "claims_checked": <number>,
  "warnings": [
    {{
      "type": "fabrication" | "wrong_value" | "omission" | "wrong_date",
      "claim": "<the suspect statement in the report>",
      "correction": "<what the source data actually says>",
      "severity": "high" | "medium" | "low"
    }}
  ],
  "summary": "<one sentence assessment>"
}}"""


DRUG_INFO_VERIFICATION_PROMPT = """You are a medication-safety fact-checker. A patient app flyout shows the
registry-sourced information below for one of a patient's medicines. Verify the
information pertains to the CORRECT medicine — registry lookups can resolve to
the wrong drug when a brand/generic name is ambiguous.

CRITICAL CHECKS:
1. WRONG DRUG: Does the indication/label match the stated medicine's drug class?
   Flag if the indication describes a different condition/class (e.g. medicine is
   a beta-blocker but the indication describes diabetes treatment).
2. PLAUSIBILITY: Are the listed adverse events and substitutes plausible for this
   medicine? Flag clearly unrelated ones (e.g. an oncology drug among substitutes
   for an antacid).
3. BRAND/GENERIC CONFUSION: Flag if two different drugs appear mixed together.
Do NOT flag missing data, formatting, or completeness — only correctness
mismatches that would mislead a patient about THIS medicine.

MEDICINE: {medicine}

FLYOUT CONTENT (JSON):
{content}

Return ONLY valid JSON (no markdown, no code fences):
{{
  "status": "verified" | "warnings" | "unverifiable",
  "claims_checked": <number>,
  "warnings": [
    {{
      "type": "wrong_drug" | "wrong_value" | "fabrication",
      "claim": "<the suspect item>",
      "correction": "<what is wrong about it>",
      "severity": "high" | "medium" | "low"
    }}
  ],
  "summary": "<one sentence assessment>"
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

            validated = await self.ai_service._call_validator(
                prompt, generator_label=original_provider
            )

            if validated is None:
                verification.verifier_provider = ""
                verification.status = "unvalidated"
                verification.summary = "No second model available to validate this content."
            else:
                result_text, provider = validated
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
        health_context: str = "",
        *,
        prompt: str | None = None,
    ) -> None:
        """Cross-check an AI-generated insight against health context using a different provider.

        Writes verification results directly on the AIInsight record. Pass
        ``prompt`` to use a domain-specific verification prompt (e.g. DDI);
        otherwise the default insight prompt is built from ``health_context``.
        """
        try:
            if prompt is None:
                prompt = INSIGHT_VERIFICATION_PROMPT.format(
                    context=(health_context or "")[:2000],
                    insight=insight.response,
                )

            validated = await self.ai_service._call_validator(
                prompt, generator_label=insight.provider_used
            )

            if validated is None:
                # No different-family validator available (e.g. single-provider
                # household). Surface as "unvalidated" — content is still shown.
                insight.verification_verifier = None
                insight.verification_status = "unvalidated"
                insight.verification_summary = "No second model available to validate this content."
            else:
                result_text, provider = validated
                insight.verification_verifier = provider
                parsed = self._parse_verification_response(result_text)

                if parsed:
                    insight.verification_status = parsed.get("status", "unverifiable")
                    insight.verification_claims_checked = parsed.get("claims_checked", 0)
                    insight.verification_summary = (parsed.get("summary") or "")[:500]
                    warnings = parsed.get("warnings", [])
                    insight.verification_warnings_json = json.dumps(warnings) if warnings else None
                else:
                    insight.verification_status = "failed"
                    insight.verification_summary = "Could not parse verification response"

        except Exception as exc:
            logger.warning("Insight verification failed for %s: %s", insight.id, exc)
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
        prompt = EXTRACTION_VERIFICATION_PROMPT.format(
            extraction=json.dumps(extracted_fields, indent=2, default=str),
        )
        return await self._verify_with_prompt(prompt, original_provider)

    async def verify_transcription(
        self,
        report: str,
        extracted_data: dict,
        generator_label: str,
    ) -> dict:
        """Cross-check an AI transcription report against its source extracted data.

        Returns a verification dict; the caller persists it on the record.
        """
        prompt = TRANSCRIPTION_VERIFICATION_PROMPT.format(
            extracted_data=json.dumps(extracted_data, indent=2, default=str)[:2000],
            report=report,
        )
        return await self._verify_with_prompt(prompt, generator_label)

    async def verify_drug_info(
        self, medicine: str, content: dict, generator_label: str = ""
    ) -> dict:
        """Cross-check drug-info flyout content against the stated medicine.

        The flyout content is registry-sourced (openFDA/ABDM/FAERS), so this
        guards the one real risk: a name-resolution error resolving the content
        to the wrong drug. Returns a verification dict (does not persist).
        """
        prompt = DRUG_INFO_VERIFICATION_PROMPT.format(
            medicine=medicine,
            content=json.dumps(content, indent=2, default=str)[:2000],
        )
        return await self._verify_with_prompt(prompt, generator_label)

    async def _verify_with_prompt(self, prompt: str, generator_label: str) -> dict:
        """Run a second-model check and return a verification dict.

        Shared by :meth:`verify_extraction` and :meth:`verify_transcription`.
        Returns status ``unvalidated`` when no different-family validator is
        available, ``failed`` on parse/error, else the parsed verdict.
        """
        try:
            validated = await self.ai_service._call_validator(
                prompt, generator_label=generator_label
            )

            if validated is None:
                return {
                    "status": "unvalidated",
                    "claims_checked": 0,
                    "warnings": [],
                    "summary": "No second model available to validate this content.",
                    "verifier_provider": "",
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                }

            result_text, provider = validated
            parsed = self._parse_verification_response(result_text)
            if parsed:
                parsed["verifier_provider"] = provider
                parsed["verified_at"] = datetime.now(timezone.utc).isoformat()
                return parsed
            return {
                "status": "failed",
                "claims_checked": 0,
                "warnings": [],
                "summary": "Could not parse verification response",
                "verifier_provider": provider,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.warning("Verification failed: %s", exc)
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
