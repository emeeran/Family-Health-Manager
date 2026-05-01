"""AI insight generation for health records."""
import asyncio
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models.base import HealthRecord, AIInsight, RecordType
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


# Record-type-specific prompt templates
_PROMPTS = {
    RecordType.LAB_REPORT: (
        "Write a focused clinical assessment note for this lab report as a reviewing physician.\n\n"
        "DATA: {data}\n\n"
        "In your assessment:\n"
        "- Identify every value outside its reference range, citing the exact result and reference range.\n"
        "- For each abnormal value, explain its clinical significance in the context of the patient's "
        "known conditions (e.g., elevated HbA1c in a diabetic patient indicates suboptimal control).\n"
        "- If serial results are detectable in the data, note the trajectory with specific values and dates.\n"
        "- Flag any critical values requiring urgent clinical attention.\n"
        "- Suggest specific follow-up tests or specialist referrals warranted by the findings.\n\n"
        "Write in clinical assessment prose. Cite values with units and reference ranges. "
        "Write approximately 250-300 words."
    ),
    RecordType.DOCTOR_VISIT: (
        "Write a focused clinical assessment note for this doctor visit as a reviewing physician.\n\n"
        "DATA: {data}\n"
        "DIAGNOSIS: {diagnosis}\n"
        "MEDICATIONS: {medications}\n\n"
        "In your assessment:\n"
        "- Summarize the visit reason and diagnosis. Assess whether the prescribed medications "
        "are clinically consistent with the diagnosis.\n"
        "- Check for potential drug-drug interactions between the prescribed medications and "
        "the patient's existing medications (listed in the patient context).\n"
        "- Identify any unresolved symptoms or chief complaints that were not addressed.\n"
        "- Note the follow-up plan and flag if the next review date has already passed.\n"
        "- If the record mentions existing conditions, assess whether this visit's treatment "
        "aligns with current management of those conditions.\n\n"
        "Write in clinical assessment prose. Reference specific medications by name and dosage. "
        "Write approximately 250-300 words."
    ),
    RecordType.BLOOD_GLUCOSE: (
        "Write a focused clinical assessment note for this glucose reading as a reviewing physician.\n\n"
        "DATA: {data}\n\n"
        "In your assessment:\n"
        "- Evaluate the reading against standard targets (Fasting: 80-130 mg/dL, "
        "Post-meal: <180 mg/dL per ADA guidelines). State whether it is within target.\n"
        "- If HbA1c data is available in the patient context, comment on overall glycemic control "
        "and how this reading fits the pattern.\n"
        "- Assess the trajectory if multiple readings are detectable — note any patterns "
        "(consistently high fasting, post-meal spikes, hypoglycemia risk from medications).\n"
        "- Evaluate the current medication regimen's effectiveness given this reading.\n"
        "- Provide targeted recommendations citing specific values.\n\n"
        "Write in clinical assessment prose. Cite values with units. "
        "Write approximately 250-300 words."
    ),
    RecordType.VITALS: (
        "Write a focused clinical assessment note for these vitals as a reviewing physician.\n\n"
        "DATA: {data}\n\n"
        "In your assessment:\n"
        "- Evaluate each vital sign (BMI, blood pressure, heart rate, temperature) against "
        "standard clinical ranges. State each value and whether it is normal/elevated/critical.\n"
        "- Assess cardiovascular risk indicators based on the numbers "
        "(e.g., BP stage, BMI category, heart rate regularity).\n"
        "- If previous readings are detectable in the patient context, note the direction "
        "and magnitude of change with specific values and dates.\n"
        "- Consider medication-related impacts on vitals (e.g., is BP medication effective? "
        "is heart rate consistent with beta-blocker therapy?).\n"
        "- Provide targeted lifestyle or medication recommendations based on the specific numbers.\n\n"
        "Write in clinical assessment prose. Cite values with units. "
        "Write approximately 250-300 words."
    ),
}

_DEFAULT_PROMPT = (
    "Write a focused clinical assessment note for this health record as a reviewing physician.\n\n"
    "Record type: {record_type}\n"
    "Date: {date}\n"
    "Diagnosis: {diagnosis}\n"
    "Clinical data: {data}\n\n"
    "In your assessment:\n"
    "- Summarize the key clinical findings from this record.\n"
    "- Identify any concerning values, results, or observations requiring attention.\n"
    "- Place the findings in context of the patient's known conditions and medications.\n"
    "- Note any follow-up actions or recommendations warranted.\n\n"
    "Write in clinical assessment prose. Cite specific values and findings. "
    "Write approximately 200-250 words."
)


class InsightService:
    """Auto-generates AI insights for new health records."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _build_prompt(self, record: HealthRecord) -> str:
        """Build a record-type-specific prompt for insight generation."""
        data_preview = (record.clinical_data or "")[:2000]
        diagnosis = record.diagnosis or "N/A"

        # Try to extract medications from structured clinical_data
        medications = "N/A"
        try:
            parsed = json.loads(record.clinical_data or "")
            if isinstance(parsed, dict):
                rx = parsed.get("prescriptions")
                if rx and isinstance(rx, list):
                    medications = "; ".join(
                        f"{p.get('type', '')} {p.get('medicine', '')} {p.get('dosage', '')}".strip()
                        for p in rx if isinstance(p, dict)
                    )
        except (json.JSONDecodeError, ValueError):
            pass

        template = _PROMPTS.get(record.record_type, _DEFAULT_PROMPT)
        return template.format(
            record_type=record.record_type.value,
            date=record.record_date,
            diagnosis=diagnosis,
            data=data_preview,
            medications=medications,
        )

    async def generate_record_insight(self, record_id: "UUID") -> AIInsight | None:
        """Generate an AI insight for a newly created health record.

        Uses AIService internally with a fresh session since this
        may run as a fire-and-forget background task.
        """
        db = SessionLocal()
        try:
            result = await db.execute(
                select(HealthRecord).where(HealthRecord.id == record_id)
            )
            record = result.scalar_one_or_none()
            if not record:
                logger.warning("Record %s not found for insight generation", record_id)
                return None

            ai_service = AIService(db)
            prompt = self._build_prompt(record)

            insight = await ai_service.generate_insight(
                prompt=prompt,
                health_record_id=record.id,
                member_id=record.family_member_id,
                comprehensive=True,
            )
            await db.commit()
            logger.info("Generated AI insight for record %s", record.id)
            return insight
        except Exception:
            await db.rollback()
            logger.exception("Failed to generate insight for record %s", record_id)
            return None
        finally:
            await db.close()


def spawn_insight_task(record_id: "UUID") -> None:
    """Fire-and-forget insight generation — errors are logged, never raised."""
    async def _run():
        svc = InsightService(None)  # type: ignore  # creates own session
        await svc.generate_record_insight(record_id)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        logger.warning("No running event loop — skipping insight generation")


def spawn_insight_verification_task(insight_id: "UUID", health_context: str) -> None:
    """Fire-and-forget insight cross-verification using a different AI provider."""
    async def _run():
        db = SessionLocal()
        try:
            result = await db.execute(
                select(AIInsight).where(AIInsight.id == insight_id)
            )
            insight = result.scalar_one_or_none()
            if not insight or insight.verification_status != "pending":
                return

            ai_service = AIService(db)
            from app.services.verification_service import VerificationService
            verification_svc = VerificationService(db, ai_service)
            await verification_svc.verify_insight(insight, health_context)
            await db.commit()
            logger.info("Verified insight %s", insight_id)
        except Exception:
            await db.rollback()
            logger.exception("Failed to verify insight %s", insight_id)
            # Mark as unverifiable so the UI doesn't spin forever
            try:
                result2 = await db.execute(
                    select(AIInsight).where(AIInsight.id == insight_id)
                )
                stuck = result2.scalar_one_or_none()
                if stuck and stuck.verification_status == "pending":
                    stuck.verification_status = "unverifiable"
                    stuck.verification_summary = "Verification could not be completed."
                    await db.commit()
            except Exception:
                await db.rollback()
        finally:
            await db.close()

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        logger.warning("No running event loop — skipping insight verification")
