"""Synthetic golden documents + ground truth for extraction accuracy eval.

All patient/provider names are fictional — no real PHI. Documents are plain
text (the OCR/transcription output the extractor consumes after OCR), so the
harness measures the LLM extraction + parsing accuracy, which is what accuracy
work (Phase 3) targets.
"""
from dataclasses import dataclass
from datetime import date

from app.models.base import RecordType
from app.schemas.health_record import ExtractedFields


@dataclass
class GoldenDoc:
    name: str
    text: str
    expected: ExtractedFields


GOLDEN_DOCUMENTS: list[GoldenDoc] = [
    GoldenDoc(
        name="clean_prescription",
        text=(
            "Dr. Ada Test, Test Clinic\n"
            "Date: 2024-01-15\n\n"
            "Patient: Test Patient\n"
            "Chief Complaint: Hypertension follow-up\n"
            "Vitals: BP 130/85, Weight 75 kg, Height 170 cm\n"
            "Diagnosis: Essential Hypertension\n\n"
            "Rx:\n"
            "Tab Amlodipine 5mg 1-0-1 after food 30 days\n"
            "Tab Metoprolol 50mg 1-0-1 before food 30 days\n\n"
            "Follow up: 2024-02-15"
        ),
        expected=ExtractedFields(
            record_type=RecordType.DOCTOR_VISIT,
            record_date=date(2024, 1, 15),
            chief_complaint="Hypertension follow-up",
            diagnosis="Essential Hypertension",
            provider_name="Dr. Ada Test, Test Clinic",
            blood_pressure="130/85",
            weight="75",
            height="170",
            next_review_date=date(2024, 2, 15),
            prescriptions=[
                {"type": "Tab", "medicine": "Amlodipine 5mg", "dosage": "1-0-1",
                 "duration": "30 days", "timing": "after_food", "note": ""},
                {"type": "Tab", "medicine": "Metoprolol 50mg", "dosage": "1-0-1",
                 "duration": "30 days", "timing": "before_food", "note": ""},
            ],
        ),
    ),
    GoldenDoc(
        name="lab_report",
        text=(
            "City Test Laboratory\n"
            "Report Date: 2024-03-10\n\n"
            "HbA1c: 8.9 % (< 6.0 %)\n"
            "Fasting Glucose: 142 mg/dL (70-100 mg/dL)\n"
            "Total Cholesterol: 195 mg/dL (< 200 mg/dL)\n\n"
            "Diagnosis: Type 2 Diabetes, Dyslipidemia"
        ),
        expected=ExtractedFields(
            record_type=RecordType.LAB_REPORT,
            record_date=date(2024, 3, 10),
            diagnosis="Type 2 Diabetes, Dyslipidemia",
            provider_name="City Test Laboratory",
            lab_tests=[
                {"test_name": "HbA1c", "result": "8.9", "units": "%",
                 "ref_value": "< 6.0 %", "note": "Elevated"},
                {"test_name": "Fasting Glucose", "result": "142", "units": "mg/dL",
                 "ref_value": "70-100 mg/dL", "note": "High"},
                {"test_name": "Total Cholesterol", "result": "195", "units": "mg/dL",
                 "ref_value": "< 200 mg/dL", "note": "Borderline"},
            ],
        ),
    ),
    GoldenDoc(
        name="multi_med_visit",
        text=(
            "General Hospital\n"
            "2024-04-05\n\n"
            "Patient: Test Patient\n"
            "Rx:\n"
            "Tab Atorvastatin 20mg 1-0-0 at night 90 days\n"
            "Tab Levothyroxine 50mcg 1-0-0 empty stomach lifelong\n"
            "Syp Testazine 2 puffs SOS\n\n"
            "Next review: 2024-05-05"
        ),
        expected=ExtractedFields(
            record_type=RecordType.DOCTOR_VISIT,
            record_date=date(2024, 4, 5),
            provider_name="General Hospital",
            next_review_date=date(2024, 5, 5),
            prescriptions=[
                {"type": "Tab", "medicine": "Atorvastatin 20mg", "dosage": "1-0-0",
                 "duration": "90 days", "timing": "bedtime", "note": ""},
                {"type": "Tab", "medicine": "Levothyroxine 50mcg", "dosage": "1-0-0",
                 "duration": "lifelong", "timing": "empty_stomach", "note": ""},
                {"type": "Syp", "medicine": "Testazine", "dosage": "2 puffs",
                 "timing": "sos", "note": ""},
            ],
        ),
    ),
    GoldenDoc(
        name="eyeglass_rx",
        text=(
            "Vision Center\n"
            "2024-07-01\n\n"
            "RE: +2.50 / -0.50 x 140  VA 6/6\n"
            "LE: +1.25 / -0.75 x 090  VA 6/6\n"
            "ADD: +2.50\n"
            "PD: 32/32"
        ),
        expected=ExtractedFields(
            record_type=RecordType.RX_EYEGLASS,
            record_date=date(2024, 7, 1),
            provider_name="Vision Center",
            eyeglass={
                "re_sph": "+2.50", "re_cyl": "-0.50", "re_axs": "140", "re_va": "6/6",
                "le_sph": "+1.25", "le_cyl": "-0.75", "le_axs": "090", "le_va": "6/6",
                "add_power": "+2.50", "pd": "32/32",
            },
        ),
    ),
    GoldenDoc(
        name="vitals_visit",
        text=(
            "Health Center\n"
            "2024-06-18 10:30\n\n"
            "Patient: Test Patient\n"
            "Weight 80 kg, Height 175 cm, BP 128/82, HR 72, Temp 98.6 F\n"
            "Diagnosis: Routine checkup, healthy"
        ),
        expected=ExtractedFields(
            record_type=RecordType.DOCTOR_VISIT,
            record_date=date(2024, 6, 18),
            record_time="10:30",
            weight="80",
            height="175",
            blood_pressure="128/82",
            heart_rate="72",
            temperature="98.6",
            provider_name="Health Center",
            diagnosis="Routine checkup, healthy",
        ),
    ),
]
