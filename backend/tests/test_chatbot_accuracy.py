"""
Chatbot accuracy verification: direct AI context testing.

Builds real household context from the database, sends questions
directly to the AI, then saves results for independent model verification.
"""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.ai_service import AIService
from datetime import datetime


# Ground truth verified directly from database
GROUND_TRUTH = {
    "hba1c_history": [
        {"date": "12-Apr-2026", "value": "8.9%", "source": "doctor_visit lab_results"},
        {"date": "04-Sep-2025", "value": "8.7%", "source": "lab_report"},
        {"date": "25-May-2025", "value": "8.8%", "source": "lab_report"},
        {"date": "28-Jun-2019", "value": "6.7%", "source": "lab_report"},
        {"date": "25-May-2018", "value": "7.5%", "source": "lab_report"},
        {"date": "12-Sep-2015", "value": "9.3%", "source": "lab_report"},
    ],
    "family_member_count": 6,
    "family_members": ["Meeran Esmail", "Jenitha Meeran", "Ashik Nesin", "Reshman Susmi", "Tarika Nesin", "Tariq Al Fayad"],
    "meeran_conditions": ["T2DM (Type 2 Diabetes) since 2008", "Hypertension since 2003", "Parkinson's Disease since 2020", "Depression"],
    "latest_medications": ["HUMALOG LISPRO", "CYBLEX MV 80/0.2MG", "PIOZ MF 15MG", "GLUXIT S 10/100 MG", "Syndopa 110", "SENTIDOR OINTMENT"],
    "latest_visit": {"date": "12-Apr-2026", "next_review": "14-May-2026"},
}

TEST_QUESTIONS = [
    {
        "question": "When was the last HbA1c test done and what was the result?",
        "expected_facts": [
            "Last HbA1c date is 12-Apr-2026",
            "Last HbA1c value is 8.9%",
        ],
        "category": "date_accuracy",
    },
    {
        "question": "List all the HbA1c results in chronological order with dates and values",
        "expected_facts": [
            "12-Sep-2015: 9.3%",
            "25-May-2018: 7.5%",
            "28-Jun-2019: 6.7%",
            "25-May-2025: 8.8%",
            "04-Sep-2025: 8.7%",
            "12-Apr-2026: 8.9%",
        ],
        "category": "date_accuracy",
    },
    {
        "question": "How many family members are there and what are their names?",
        "expected_facts": ["6 family members including Tariq Al Fayad"],
        "category": "basic_facts",
    },
    {
        "question": "What chronic conditions does Meeran have?",
        "expected_facts": ["T2DM", "Hypertension", "Parkinson's Disease", "Depression"],
        "category": "condition_accuracy",
    },
    {
        "question": "What medications is Meeran currently taking?",
        "expected_facts": ["HUMALOG", "Syndopa 110", "CYBLEX MV", "PIOZ MF", "GLUXIT S"],
        "category": "medication_accuracy",
    },
    {
        "question": "When was the most recent doctor visit for Meeran?",
        "expected_facts": ["12-Apr-2026", "Next review 14-May-2026"],
        "category": "date_accuracy",
    },
]


def build_context_from_db(db_path: str, household_id: str) -> str:
    """Build the exact context the AI service would build from the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get all members
    members = conn.execute(
        "SELECT * FROM family_members WHERE household_id = ? AND is_active = 1",
        (household_id,),
    ).fetchall()

    context = "=== FAMILY HEALTH SUMMARY ===\n\n"

    members_data = []
    for member in members:
        first_name = member["first_name"]
        last_name = member["last_name"]
        dob = member["date_of_birth"]
        conditions = member["medical_history_summary"] or ""
        blood_group = member["blood_group"] or ""

        context += f"--- {first_name} {last_name} ---\n"

        # Format DOB
        try:
            parsed = datetime.strptime(dob, "%Y-%m-%d")
            context += f"DOB: {parsed.strftime('%d-%b-%Y')}\n"
        except (ValueError, TypeError):
            context += f"DOB: {dob}\n"

        if conditions:
            context += f"Conditions: {conditions}\n"
        if blood_group:
            context += f"Blood Group: {blood_group}\n"

        members_data.append({"id": member["id"], "name": f"{first_name} {last_name}"})

        # Get last 10 records for this member
        records = conn.execute(
            """SELECT record_date, record_type, diagnosis, clinical_data, prescription_text, next_review_date
               FROM health_records
               WHERE family_member_id = ? AND is_deleted = 0
               ORDER BY record_date DESC LIMIT 20""",
            (member["id"],),
        ).fetchall()

        if records:
            context += f"Recent Records ({len(records)}):\n"
            for r in records:
                try:
                    parsed = datetime.strptime(r["record_date"], "%Y-%m-%d")
                    date_str = parsed.strftime("%d-%b-%Y")
                except (ValueError, TypeError):
                    date_str = r["record_date"]

                context += f"  [{date_str}] {r['record_type']}"
                if r["diagnosis"]:
                    context += f" — {r['diagnosis']}"

                # Parse structured clinical data
                summary = AIService._summarize_clinical_data(r["clinical_data"])
                if summary:
                    context += f"\n    {summary}"
                if r["prescription_text"]:
                    context += f"\n    Rx: {r['prescription_text'][:300]}"
                context += "\n"
        context += "\n"

    # Build lab trends across ALL records
    context += build_lab_trends_from_db(conn, [m["id"] for m in members_data])

    conn.close()
    return context


def build_lab_trends_from_db(conn, member_ids):
    """Extract key lab trends from all records for given members."""
    KEY_TESTS = {"hba1c", "hb a1c", "glycosylated hb", "fasting glucose",
                 "postprandial blood glucose", "total cholesterol",
                 "ldl cholesterol", "hdl cholesterol", "triglyceride"}

    trends = {}
    placeholders = ",".join("?" * len(member_ids))
    records = conn.execute(
        f"SELECT record_date, clinical_data FROM health_records "
        f"WHERE family_member_id IN ({placeholders}) AND is_deleted = 0 "
        f"ORDER BY record_date ASC",
        member_ids,
    ).fetchall()

    for r in records:
        try:
            data = json.loads(r["clinical_data"])
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
                if any(kw in name for kw in KEY_TESTS):
                    display_name = t.get("test_name", "")
                    try:
                        parsed = datetime.strptime(r["record_date"], "%Y-%m-%d")
                        date_str = parsed.strftime("%d-%b-%Y")
                    except (ValueError, TypeError):
                        date_str = r["record_date"]
                    trends.setdefault(display_name, []).append((date_str, result, note))

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


async def run_tests():
    """Build context, send questions, save results for verification."""
    db_path = str(Path(__file__).parent.parent / "data" / "health.db")
    household_id = "ea8562b1814d459ab3e12ac5157bc61f"  # Meeran's household

    print("Building context from database...")
    context = build_context_from_db(db_path, household_id)

    # Save the context for review
    with open("tests/chatbot_context_snapshot.txt", "w") as f:
        f.write(context)
    print(f"Context saved ({len(context)} chars)\n")

    # Send questions via the AI service directly (no DB session needed)
    # We'll use a minimal mock to call _call_ai directly
    from unittest.mock import MagicMock
    service = AIService.__new__(AIService)
    service.db = MagicMock()

    results = []
    for i, test in enumerate(TEST_QUESTIONS):
        print(f"[{i+1}/{len(TEST_QUESTIONS)}] Q: {test['question']}")

        try:
            response, provider = await service._call_ai(test["question"], context)
            print(f"    Provider: {provider}")
            print(f"    A: {response[:400]}...")
        except Exception as e:
            response = f"ERROR: {e}"
            print(f"    A: {response}")

        results.append({
            "question": test["question"],
            "response": response,
            "expected_facts": test["expected_facts"],
            "category": test["category"],
            "provider": provider if 'provider' in dir() else "unknown",
        })
        print()

    # Save results
    output = {
        "ground_truth": GROUND_TRUTH,
        "context_sent_to_ai": context[:5000],  # First 5000 chars
        "test_results": results,
    }
    with open("tests/chatbot_test_results.json", "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("Results saved to tests/chatbot_test_results.json")
    return results


if __name__ == "__main__":
    asyncio.run(run_tests())
