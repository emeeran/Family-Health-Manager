import { forwardRef, useMemo, Suspense } from "react";
import type { HealthRecordResponse } from "@/lib/types/health-record";
import type { FamilyMemberResponse } from "@/lib/types/member";
import { MarkdownRenderer } from "@/components/shared/lazy-markdown";
import { formatDate } from "@/lib/utils";

/**
 * "Medical Records Transcription Report" view.
 *
 * Renders the persisted AI-generated report (record.transcription_report) when
 * present, otherwise assembles a deterministic template from the record's
 * structured fields + member demographics. The same markdown→HTML path is used
 * for both so the output is consistent and exportable (the host can grab the
 * ref'd container for html2pdf export).
 */
export interface TranscriptionReportViewProps {
  record: HealthRecordResponse;
  member?: FamilyMemberResponse | null;
  /** Compact styling for hover popouts (smaller text, tighter spacing). */
  compact?: boolean;
  /** Render in fixed black-on-white document style (for print/export). */
  documentStyle?: boolean;
  className?: string;
}

type Row = Record<string, string>;

function parseClinicalData(raw: string): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function computeAge(dob?: string | null): number | null {
  if (!dob) return null;
  const d = new Date(dob);
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - d.getFullYear();
  const m = now.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) age--;
  return age >= 0 ? age : null;
}

function genderLabel(g?: string | null): string | null {
  if (!g) return null;
  const map: Record<string, string> = {
    male: "Male",
    female: "Female",
    other: "Other",
    prefer_not_to_say: "Prefer not to say",
  };
  return map[g] ?? g;
}

/** Build the canonical report layout deterministically (no AI). */
function buildTemplateMarkdown(
  record: HealthRecordResponse,
  member?: FamilyMemberResponse | null
): string {
  const parsed = parseClinicalData(record.clinical_data);
  const str = (key: string): string => {
    const v = parsed?.[key];
    if (v == null) return "";
    const s = typeof v === "string" ? v : String(v);
    return s.trim();
  };
  const arr = (...keys: string[]): Row[] => {
    for (const k of keys) {
      const v = parsed?.[k];
      if (Array.isArray(v) && v.length > 0) return v as Row[];
    }
    return [];
  };

  const prescriptions = arr("prescriptions");
  const labs = arr("lab_tests", "lab_results", "tests");
  const chiefComplaint = str("chief_complaint");
  const existingConditions = str("existing_conditions");
  const investigations = str("investigations");
  const notesText = str("_notes") || str("notes");
  const diagnosis = record.diagnosis || "";

  const institution = record.provider_name || "Family Health Manager";
  const L: string[] = [`# ${institution}`, "## Medical Records Transcription Report"];
  L.push(`**Document Date:** ${formatDate(record.record_date)}`);
  L.push("");

  // §1 Patient Identification & Demographics
  const demo: string[] = [];
  if (member) {
    demo.push(`- **Patient Name:** ${`${member.first_name} ${member.last_name}`.trim()}`);
  }
  if (member?.patient_id) demo.push(`- **Patient ID / ID No:** ${member.patient_id}`);
  const age = computeAge(member?.date_of_birth);
  const ageGender = [age != null ? `${age} Years` : "", genderLabel(member?.gender)]
    .filter(Boolean)
    .join(" / ");
  if (ageGender) demo.push(`- **Age / Gender:** ${ageGender}`);
  let regDate = `- **Registration Date:** ${formatDate(record.record_date)}`;
  if (record.record_time) regDate += ` ${record.record_time}`;
  demo.push(regDate);
  if (member?.phone) demo.push(`- **Contact No:** ${member.phone}`);
  if (member?.address) demo.push(`- **Primary Address:** ${member.address}`);
  if (demo.length) {
    L.push("### 1. PATIENT IDENTIFICATION & DEMOGRAPHICS");
    L.push(...demo);
    L.push("");
  }

  // §2 Outpatient Consultation & Clinical Findings
  const s2: string[] = [];
  if (record.provider_name) s2.push(`- **Consultant Physician:** ${record.provider_name}`);
  const vitals = [
    str("blood_pressure") && `BP ${str("blood_pressure")} mmHg`,
    str("heart_rate") && `Pulse ${str("heart_rate")} bpm`,
    str("temperature") && `Temp ${str("temperature")} °F`,
    str("weight") && `Weight ${str("weight")} kg`,
    str("height") && `Height ${str("height")} cm`,
  ].filter(Boolean);
  if (vitals.length) s2.push(`- **Vitals & Physical Findings:** ${vitals.join(" · ")}`);
  if (chiefComplaint) s2.push(`- **History & Symptoms:** ${chiefComplaint}`);
  if (diagnosis) s2.push(`- **Provisional Diagnosis:** ${diagnosis}`);
  if (existingConditions) s2.push(`- **Existing Conditions:** ${existingConditions}`);
  if (s2.length) {
    L.push("### 2. OUTPATIENT CONSULTATION & CLINICAL FINDINGS");
    L.push(...s2);
    L.push("");
  }

  // §3 Treatment Plan & Medical Orders
  if (prescriptions.length) {
    L.push("### 3. TREATMENT PLAN & MEDICAL ORDERS");
    L.push("| Medication / Clinical Order | Dosage & Instructions |");
    L.push("|---|---|");
    for (const rx of prescriptions) {
      const order = `${rx.type || ""} ${rx.medicine || ""}`.trim();
      const instr = [rx.dosage, rx.timing, rx.duration].filter(Boolean).join(" · ");
      L.push(`| ${order || "—"} | ${instr || rx.note || ""} |`);
    }
    if (record.next_review_date) {
      L.push("");
      L.push(`- **Follow-up:** ${formatDate(record.next_review_date)}`);
    }
    if (investigations) L.push(`- **Investigations:** ${investigations}`);
    L.push("");
  }

  // §4 Diagnostic Summary
  if (labs.length) {
    L.push("### 4. DIAGNOSTIC SUMMARY");
    L.push("| Test Name | Observed Value | Normal Reference Range | Note |");
    L.push("|---|---|---|---|");
    for (const lt of labs) {
      L.push(
        `| ${lt.test_name || ""} | ${lt.result || ""} | ${lt.ref_value || ""} | ${lt.note || ""} |`
      );
    }
    L.push("");
  }

  // Free-text notes (advice / imaging not captured as tables)
  if (notesText) {
    L.push("### Notes");
    L.push(notesText);
    L.push("");
  }

  L.push(
    "_This document serves as a verified structured transcription summary of the referenced record._"
  );
  return L.join("\n");
}

export const TranscriptionReportView = forwardRef<HTMLDivElement, TranscriptionReportViewProps>(
  function TranscriptionReportView({ record, member, compact, documentStyle, className }, ref) {
    const md = useMemo(
      () =>
        record.transcription_report?.trim()
          ? record.transcription_report
          : buildTemplateMarkdown(record, member),
      [record, member]
    );

    const color = documentStyle
      ? "text-black prose-headings:text-black prose-strong:text-black prose-th:bg-gray-100"
      : "text-foreground prose-headings:text-foreground prose-strong:text-foreground prose-th:bg-muted/50";

    return (
      <div
        ref={ref}
        className={[
          "transcription-report prose prose-sm max-w-none prose-headings:font-semibold",
          "prose-table:text-[11px] prose-th:px-1.5 prose-th:py-0.5 prose-td:px-1.5 prose-td:py-0.5",
          "prose-h2:text-base prose-h2:mt-0 prose-h3:text-[13px] prose-h3:mt-2",
          color,
          compact ? "text-[11px] leading-snug" : "text-[13px]",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <Suspense fallback={null}>
          <MarkdownRenderer content={md} />
        </Suspense>
      </div>
    );
  }
);
