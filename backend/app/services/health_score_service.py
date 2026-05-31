"""Health score computation — shared across routers and services."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from app.models.base import RecordType


def compute_health_score(
    member,  # FamilyMember — avoid circular import by not typing
    conditions_count: int,
    active_medications: list,
    recent_records: list,
    age: int,
) -> tuple[int, dict]:
    """Compute enhanced health score with category breakdown.

    Returns (total_score, breakdown_dict) where breakdown contains
    per-category scores with labels explaining the assessment.
    """
    breakdown: dict[str, dict] = {}
    total = 0

    # 1. BMI component (0-20)
    bmi_score = 10  # default: no data
    bmi_label = "No BMI data available"
    if member.height_cm and member.weight_kg and member.height_cm > 0:
        hm = member.height_cm / 100
        bmi = round(member.weight_kg / (hm * hm), 1)
        if 18.5 <= bmi < 25:
            bmi_score = 20
            bmi_label = f"BMI {bmi} — normal range"
        elif 25 <= bmi < 30:
            bmi_score = 14
            bmi_label = f"BMI {bmi} — overweight"
        elif 30 <= bmi < 35:
            bmi_score = 8
            bmi_label = f"BMI {bmi} — obese class I"
        else:
            bmi_score = 5
            bmi_label = f"BMI {bmi} — obese class II+"
    total += bmi_score
    breakdown["bmi"] = {"score": bmi_score, "max": 20, "label": bmi_label}

    # 2. Conditions management (0-20) — reward having recent checkups
    cond_score = 20
    cond_label = "No known chronic conditions"
    if conditions_count > 0:
        six_months_ago = date.today() - timedelta(days=182)
        has_recent_visit = any(
            r.record_type == RecordType.DOCTOR_VISIT and r.record_date >= six_months_ago
            for r in recent_records
        )
        if has_recent_visit:
            cond_score = 16
            cond_label = f"{conditions_count} condition(s), recent checkup within 6 months"
        else:
            cond_score = 8
            cond_label = f"{conditions_count} condition(s), no recent checkup"
    total += cond_score
    breakdown["conditions_management"] = {"score": cond_score, "max": 20, "label": cond_label}

    # 3. Lab compliance (0-20) — are recent labs within reference range?
    lab_score = 10  # neutral: no lab data
    lab_label = "No recent lab data"
    lab_records = [r for r in recent_records if r.record_type in (RecordType.LAB_REPORT, RecordType.BLOOD_GLUCOSE)]
    if lab_records:
        normal_count = 0
        abnormal_count = 0
        for r in lab_records[:5]:
            try:
                parsed = json.loads(r.clinical_data or "")
                for key in ("tests", "lab_results"):
                    for t in parsed.get(key) or []:
                        if isinstance(t, dict):
                            note = (t.get("note") or "").lower()
                            if "critical" in note or "high" in note or "elevated" in note or "low" in note:
                                abnormal_count += 1
                            elif "normal" in note or "well" in note:
                                normal_count += 1
            except (json.JSONDecodeError, ValueError):
                continue
        if abnormal_count == 0 and normal_count > 0:
            lab_score = 20
            lab_label = "All recent lab results normal"
        elif normal_count >= abnormal_count:
            lab_score = 14
            lab_label = f"Mostly normal ({normal_count} normal, {abnormal_count} flagged)"
        elif abnormal_count > 0:
            lab_score = 6
            lab_label = f"{abnormal_count} abnormal result(s) flagged"
    total += lab_score
    breakdown["lab_compliance"] = {"score": lab_score, "max": 20, "label": lab_label}

    # 4. Medication tracking (0-15) — reward tracking, not penalize count
    med_count = len(active_medications)
    if med_count == 0:
        med_score = 15
        med_label = "No active medications"
    else:
        med_score = 12
        med_label = f"{med_count} medication(s) actively tracked"
        has_followup = any(r.next_review_date for r in recent_records[:5])
        if has_followup:
            med_score = 15
            med_label = f"{med_count} medication(s) tracked with follow-up scheduled"
    total += med_score
    breakdown["medication_tracking"] = {"score": med_score, "max": 15, "label": med_label}

    # 5. Profile completeness (0-15)
    profile_score = 0
    profile_items = []
    if member.blood_group:
        profile_score += 5
        profile_items.append("blood group")
    if member.emergency_contact_name or member.emergency_contact_phone:
        profile_score += 5
        profile_items.append("emergency contact")
    if member.medical_history_summary:
        profile_score += 5
        profile_items.append("medical history")
    if member.allergies_json:
        try:
            allergies = json.loads(member.allergies_json)
            if isinstance(allergies, list) and len(allergies) > 0:
                profile_items.append("allergies")
        except (ValueError, json.JSONDecodeError):
            pass
    missing = 15 - profile_score
    profile_label = f"Complete ({', '.join(profile_items)})" if profile_score >= 15 else f"Missing {missing} pts of data"
    total += profile_score
    breakdown["profile_completeness"] = {"score": profile_score, "max": 15, "label": profile_label}

    # 6. Record recency (0-10) — reward keeping records up to date
    recency_score = 0
    if recent_records:
        latest = recent_records[0].record_date
        days_since = (date.today() - latest).days
        if days_since <= 30:
            recency_score = 10
            recency_label = f"Last record {days_since} days ago"
        elif days_since <= 90:
            recency_score = 7
            recency_label = f"Last record {days_since} days ago"
        elif days_since <= 180:
            recency_score = 4
            recency_label = f"Last record {days_since // 30} months ago"
        else:
            recency_score = 1
            recency_label = f"Last record over {days_since // 30} months ago"
    else:
        recency_score = 0
        recency_label = "No records yet"
    total += recency_score
    breakdown["record_recency"] = {"score": recency_score, "max": 10, "label": recency_label}

    return min(100, total), breakdown


def get_conditions_count(medical_history_summary: str | None) -> int:
    """Parse the number of conditions from a medical_history_summary string.

    Expected format: "Conditions: X, Y; Surgeries: Z" — extracts count from
    the comma-separated list after the "Conditions:" label.
    """
    if not medical_history_summary:
        return 0
    for part in medical_history_summary.split("; "):
        if part.startswith("Conditions:"):
            return len([x.strip() for x in part.replace("Conditions:", "").split(",") if x.strip()])
    return 0


def extract_hba1c_history(records: list) -> list[dict]:
    """Extract HbA1c history from a list of HealthRecord ORM objects.

    Scans clinical_data JSON for direct `hba1c_value` fields or lab results
    containing HbA1c/A1c/Glycated test names.
    Returns [{"date": "YYYY-MM-DD", "hba1c_value": float}, ...].
    """
    history: list[dict] = []
    for r in records:
        try:
            data = json.loads(r.clinical_data) if r.clinical_data else {}
            if not isinstance(data, dict):
                continue
            if "hba1c_value" in data:
                history.append({
                    "date": r.record_date.isoformat(),
                    "hba1c_value": float(data["hba1c_value"]),
                })
                continue
            for key in ("lab_results", "tests"):
                lab_list = data.get(key)
                if not isinstance(lab_list, list):
                    continue
                for test in lab_list:
                    if not isinstance(test, dict):
                        continue
                    name = (test.get("test_name") or "").lower()
                    if "hba1c" in name or "glycated" in name or "glycosylated" in name or "a1c" in name:
                        result_str = test.get("result", "")
                        match = re.search(r"(\d+\.?\d*)", str(result_str))
                        if match:
                            val = float(match.group(1))
                            if 3.0 <= val <= 15.0:
                                history.append({
                                    "date": r.record_date.isoformat(),
                                    "hba1c_value": val,
                                })
                                break
                else:
                    continue
                break
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return history
