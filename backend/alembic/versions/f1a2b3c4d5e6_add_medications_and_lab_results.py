"""Add medications and lab_results tables with backfill

Revision ID: f1a2b3c4d5e6
Revises: d4e5f6a7b8c9, e3f4df27a556
Create Date: 2026-06-01

Creates `medications` and `lab_results` tables, then backfills them
from existing structured clinical_data JSON in health_records.
"""
import json
import re
from datetime import date, timedelta
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = ("d4e5f6a7b8c9", "e3f4df27a556")
branch_labels = None
depends_on = None


def parse_duration(duration_str: str | None) -> int:
    """Parse a human-readable duration into days. Returns 30 on failure."""
    if not duration_str:
        return 30
    text = str(duration_str).strip().lower()
    m = re.match(r"([0-9]+)\s*days?", text)
    if m:
        return int(m.group(1))
    m = re.match(r"([0-9]+)\s*weeks?", text)
    if m:
        return int(m.group(1)) * 7
    m = re.match(r"([0-9]+)\s*months?", text)
    if m:
        return int(m.group(1)) * 30
    m = re.match(r"([0-9]+)$", text)
    if m:
        return int(m.group(1))
    return 30


def upgrade() -> None:
    # ── Create medications table ──────────────────────────────────────
    op.create_table(
        "medications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("family_member_id", sa.String(36),
                  sa.ForeignKey("family_members.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("health_record_id", sa.String(36),
                  sa.ForeignKey("health_records.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("medicine", sa.Text(), nullable=False),
        sa.Column("medicine_key", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), server_default=""),
        sa.Column("dosage", sa.Text(), server_default=""),
        sa.Column("timing", sa.Text(), server_default=""),
        sa.Column("duration", sa.Text(), server_default=""),
        sa.Column("duration_days", sa.Integer(), server_default=sa.text("30")),
        sa.Column("note", sa.Text(), server_default=""),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), server_default="active"),
        sa.Column("prescription_index", sa.Integer(), server_default=sa.text("0")),
        sa.Column("provider_name", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_medications_member_status", "medications",
                     ["family_member_id", "status"])
    op.create_index("ix_medications_member_key", "medications",
                     ["family_member_id", "medicine_key"])
    op.create_index("ix_medications_record_id", "medications",
                     ["health_record_id"])

    # ── Create lab_results table ──────────────────────────────────────
    op.create_table(
        "lab_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("family_member_id", sa.String(36),
                  sa.ForeignKey("family_members.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("health_record_id", sa.String(36),
                  sa.ForeignKey("health_records.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("test_name", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("units", sa.Text(), server_default=""),
        sa.Column("ref_value", sa.Text(), server_default=""),
        sa.Column("note", sa.Text(), server_default=""),
        sa.Column("record_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_lab_results_member_test", "lab_results",
                     ["family_member_id", "test_name"])
    op.create_index("ix_lab_results_member_date", "lab_results",
                     ["family_member_id", "record_date"])
    op.create_index("ix_lab_results_record_id", "lab_results",
                     ["health_record_id"])

    # ── Backfill from existing health_records ─────────────────────────
    conn = op.get_bind()
    today = date.today()

    records = conn.execute(
        sa.text(
            "SELECT id, family_member_id, record_date, clinical_data, provider_id "
            "FROM health_records "
            "WHERE clinical_data LIKE '%_type%' AND is_deleted = 0 "
            "ORDER BY record_date ASC, created_at ASC"
        )
    ).fetchall()

    # Resolve provider names
    provider_map: dict[str, str] = {}
    if records:
        pids = {str(r.provider_id) for r in records if r.provider_id}
        if pids:
            providers = conn.execute(
                sa.text("SELECT id, name FROM providers WHERE id IN :pids"),
                {"pids": tuple(pids)},
            ).fetchall()
            provider_map = {str(p.id): p.name for p in providers}

    med_rows: list[dict] = []
    lab_rows: list[dict] = []

    for r in records:
        try:
            parsed = json.loads(r.clinical_data)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(parsed, dict) or parsed.get("_type") != "structured":
            continue
        if parsed.get("_medication_sync") is False:
            continue

        record_id = str(r.id)
        member_id = str(r.family_member_id)
        record_date = r.record_date
        p_name = provider_map.get(str(r.provider_id), "") if r.provider_id else ""

        # ── Prescriptions → medications ───────────────────────────────
        prescriptions = parsed.get("prescriptions", [])
        if isinstance(prescriptions, list):
            for i, rx in enumerate(prescriptions):
                medicine = (rx.get("medicine") or "").strip()
                if not medicine:
                    continue
                medicine_key = medicine.lower().split()[0] if medicine.split() else ""
                duration_days = parse_duration(rx.get("duration"))
                end_date = record_date + timedelta(days=duration_days) if record_date else None
                status = "active" if end_date and end_date >= today else "completed"

                med_rows.append({
                    "id": str(uuid4()),
                    "family_member_id": member_id,
                    "health_record_id": record_id,
                    "medicine": medicine,
                    "medicine_key": medicine_key,
                    "type": rx.get("type", ""),
                    "dosage": rx.get("dosage", ""),
                    "timing": rx.get("timing", ""),
                    "duration": rx.get("duration", ""),
                    "duration_days": duration_days,
                    "note": rx.get("note", ""),
                    "start_date": record_date,
                    "end_date": end_date,
                    "status": status,
                    "prescription_index": i,
                    "provider_name": p_name,
                    "created_at": r.record_date,
                    "updated_at": r.record_date,
                })

        # ── Tests / lab_results → lab_results ─────────────────────────
        tests = parsed.get("lab_results") or parsed.get("tests") or []
        if isinstance(tests, list):
            for t in tests:
                test_name = (t.get("test_name") or "").strip()
                result_val = (t.get("result") or "").strip()
                if not test_name or not result_val:
                    continue
                lab_rows.append({
                    "id": str(uuid4()),
                    "family_member_id": member_id,
                    "health_record_id": record_id,
                    "test_name": test_name,
                    "result": result_val,
                    "units": t.get("units", ""),
                    "ref_value": t.get("ref_value", ""),
                    "note": t.get("note", ""),
                    "record_date": record_date,
                    "created_at": r.record_date,
                })

    # Batch insert medications
    if med_rows:
        conn.execute(
            sa.text(
                "INSERT INTO medications "
                "(id, family_member_id, health_record_id, medicine, medicine_key, "
                "type, dosage, timing, duration, duration_days, note, "
                "start_date, end_date, status, prescription_index, provider_name, "
                "created_at, updated_at) "
                "VALUES (:id, :family_member_id, :health_record_id, :medicine, "
                ":medicine_key, :type, :dosage, :timing, :duration, :duration_days, "
                ":note, :start_date, :end_date, :status, :prescription_index, "
                ":provider_name, :created_at, :updated_at)"
            ),
            med_rows,
        )

    # Batch insert lab_results
    if lab_rows:
        conn.execute(
            sa.text(
                "INSERT INTO lab_results "
                "(id, family_member_id, health_record_id, test_name, result, "
                "units, ref_value, note, record_date, created_at) "
                "VALUES (:id, :family_member_id, :health_record_id, :test_name, "
                ":result, :units, :ref_value, :note, :record_date, :created_at)"
            ),
            lab_rows,
        )


def downgrade() -> None:
    op.drop_index("ix_lab_results_record_id", table_name="lab_results")
    op.drop_index("ix_lab_results_member_date", table_name="lab_results")
    op.drop_index("ix_lab_results_member_test", table_name="lab_results")
    op.drop_table("lab_results")

    op.drop_index("ix_medications_record_id", table_name="medications")
    op.drop_index("ix_medications_member_key", table_name="medications")
    op.drop_index("ix_medications_member_status", table_name="medications")
    op.drop_table("medications")
