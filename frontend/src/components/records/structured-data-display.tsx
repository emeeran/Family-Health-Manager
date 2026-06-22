import React, { useMemo, type ComponentType } from "react";
import {
  Flame,
  Droplets,
  Heart,
  Activity,
  Droplet,
  Zap,
  Shield,
  ArrowLeftRight,
  Stethoscope,
} from "lucide-react";
import { deserializeClinicalData } from "@/lib/clinical-data";
import { formatDate } from "@/lib/utils";
import type { RecordType } from "@/lib/types/enums";

/* ──────────────────────────────────────────────
   Interfaces
   ────────────────────────────────────────────── */

interface StructuredDataDisplayProps {
  recordType: RecordType;
  clinicalData: string;
  memberName?: string;
  memberAge?: number;
  memberGender?: string;
  memberBloodGroup?: string;
  providerName?: string;
  recordDate?: string;
  recordTime?: string;
  diagnosis?: string;
  nextReviewDate?: string;
}

/* ──────────────────────────────────────────────
   Test Categorization
   ────────────────────────────────────────────── */

interface TestCategory {
  name: string;
  icon: ComponentType<{ className?: string }>;
  iconBg: string;
  keywords: string[];
}

const TEST_CATEGORIES: TestCategory[] = [
  {
    name: "Liver Function Test",
    icon: Flame,
    iconBg: "bg-orange-500",
    keywords: [
      "bilirubin",
      "total protein",
      "albumin",
      "globulin",
      "a/g ratio",
      "sgot",
      "sgpt",
      "ast",
      "alt",
      "alkaline phosphatase",
      "gamma",
      "ggt",
      "gamma gt",
    ],
  },
  {
    name: "Complete Blood Count",
    icon: Droplets,
    iconBg: "bg-red-500",
    keywords: [
      "hemoglobin",
      "hgb",
      "pcv",
      "hematocrit",
      "rbc",
      "mcv",
      "mch",
      "mchc",
      "rdw",
      "tlc",
      "wbc",
      "total leukocyte",
      "neutrophil",
      "lymphocyte",
      "monocyte",
      "eosinophil",
      "basophil",
      "platelet",
      "esr",
      "pdw",
      "mpv",
      "total count",
    ],
  },
  {
    name: "Lipid Profile",
    icon: Heart,
    iconBg: "bg-pink-500",
    keywords: [
      "cholesterol",
      "triglyceride",
      "hdl",
      "ldl",
      "vldl",
      "non-hdl",
      "tc/hdl",
      "ldl/hdl",
      "total cholesterol",
    ],
  },
  {
    name: "Diabetes Monitoring",
    icon: Activity,
    iconBg: "bg-blue-500",
    keywords: [
      "glucose",
      "hba1c",
      "glycated",
      "fasting sugar",
      "post prandial",
      "pp sugar",
      "fbs",
      "ppbs",
      "random blood sugar",
      "rbs",
    ],
  },
  {
    name: "Renal Function Test",
    icon: Droplet,
    iconBg: "bg-emerald-500",
    keywords: ["urea", "creatinine", "egfr", "bun", "uric acid", "blood urea", "gfr"],
  },
  {
    name: "Electrolytes",
    icon: Zap,
    iconBg: "bg-cyan-500",
    keywords: ["sodium", "potassium", "chloride", "bicarbonate"],
  },
  {
    name: "Coagulation Profile",
    icon: Shield,
    iconBg: "bg-purple-500",
    keywords: [
      "pt",
      "inr",
      "aptt",
      "prothrombin",
      "thromboplastin",
      "bleeding time",
      "clotting time",
    ],
  },
  {
    name: "Pancreatic Enzymes",
    icon: Flame,
    iconBg: "bg-amber-500",
    keywords: ["amylase", "lipase"],
  },
  {
    name: "Urine Analysis",
    icon: Droplet,
    iconBg: "bg-yellow-500",
    keywords: [
      "specific gravity",
      "pus cells",
      "epithelial cells",
      "casts",
      "crystals",
      "bacteria",
      "urine",
      "urobilin",
      "colour",
      "color",
      "appearance",
      "ketone",
      "nitrite",
      "leukocyte",
    ],
  },
  {
    name: "Thyroid Profile",
    icon: Activity,
    iconBg: "bg-indigo-500",
    keywords: ["t3", "t4", "tsh", "thyroid", "triiodothyronine", "thyroxine"],
  },
  {
    name: "Vascular Assessment",
    icon: ArrowLeftRight,
    iconBg: "bg-rose-500",
    keywords: ["abi", "tbi", "vascular", "doppler", "ankle", "brachial", "toe"],
  },
  {
    name: "Prostate Assessment",
    icon: Stethoscope,
    iconBg: "bg-violet-500",
    keywords: ["psa", "prostate", "free psa", "total psa"],
  },
];

/** Map test rows into categorized groups, preserving TEST_CATEGORIES order */
function categorizeTests(rows: Record<string, string>[]): Map<string, Record<string, string>[]> {
  const buckets = new Map<string, Record<string, string>[]>();
  const uncategorized: Record<string, string>[] = [];

  for (const row of rows) {
    const name = (row.test_name || "").toLowerCase();
    let matched = false;

    for (const cat of TEST_CATEGORIES) {
      if (cat.keywords.some((kw) => name.includes(kw))) {
        const list = buckets.get(cat.name) || [];
        list.push(row);
        buckets.set(cat.name, list);
        matched = true;
        break;
      }
    }

    if (!matched) uncategorized.push(row);
  }

  if (uncategorized.length > 0) buckets.set("Other Tests", uncategorized);
  return buckets;
}

/** Return category config by name */
function getCategoryConfig(name: string): TestCategory | undefined {
  return TEST_CATEGORIES.find((c) => c.name === name);
}

/** Build an ordered map (follows TEST_CATEGORIES sequence, then "Other Tests") */
function orderedCategories(rows: Record<string, string>[]): Map<string, Record<string, string>[]> {
  const raw = categorizeTests(rows);
  const ordered = new Map<string, Record<string, string>[]>();

  for (const cat of TEST_CATEGORIES) {
    const catRows = raw.get(cat.name);
    if (catRows) ordered.set(cat.name, catRows);
  }

  const other = raw.get("Other Tests");
  if (other) ordered.set("Other Tests", other);

  return ordered;
}

/* ──────────────────────────────────────────────
   Unit Extraction
   ────────────────────────────────────────────── */

const KNOWN_UNITS: [string, string][] = [
  // Diabetes
  ["glucose", "mg/dL"],
  ["hba1c", "%"],
  ["glycated hemoglobin", "%"],
  // CBC
  ["hemoglobin", "g/dL"],
  ["rbc", "million/µL"],
  ["total leukocyte", "cells/µL"],
  ["tlc", "cells/µL"],
  ["wbc", "cells/µL"],
  ["platelet", "lakhs/µL"],
  ["mcv", "fL"],
  ["mch", "pg"],
  ["mchc", "g/dL"],
  ["rdw", "%"],
  ["esr", "mm/hr"],
  ["pcv", "%"],
  ["hematocrit", "%"],
  ["neutrophil", "%"],
  ["lymphocyte", "%"],
  ["monocyte", "%"],
  ["eosinophil", "%"],
  ["basophil", "%"],
  // Lipid
  ["cholesterol", "mg/dL"],
  ["triglyceride", "mg/dL"],
  ["hdl", "mg/dL"],
  ["ldl", "mg/dL"],
  ["vldl", "mg/dL"],
  // Liver
  ["bilirubin", "mg/dL"],
  ["sgot", "U/L"],
  ["sgpt", "U/L"],
  ["ast", "U/L"],
  ["alt", "U/L"],
  ["alkaline phosphatase", "U/L"],
  ["gamma gt", "U/L"],
  ["ggt", "U/L"],
  ["albumin", "g/dL"],
  ["total protein", "g/dL"],
  ["globulin", "g/dL"],
  // Renal
  ["urea", "mg/dL"],
  ["creatinine", "mg/dL"],
  ["egfr", "mL/min/1.73m²"],
  ["uric acid", "mg/dL"],
  // Electrolytes
  ["sodium", "mEq/L"],
  ["potassium", "mEq/L"],
  ["chloride", "mEq/L"],
  // Pancreatic
  ["amylase", "U/L"],
  ["lipase", "U/L"],
  // PSA
  ["psa", "ng/mL"],
  // Thyroid
  ["tsh", "mIU/L"],
  ["t3", "ng/dL"],
  ["t4", "µg/dL"],
];

function extractResultAndUnits(result: string, testName: string): { value: string; units: string } {
  // "296 mg/dL" → { value: "296", units: "mg/dL" }
  const match = result.match(/^([\d.]+)\s+(.+)$/);
  if (match) return { value: match[1], units: match[2].trim() };

  // Lookup known units by test name
  const lower = testName.toLowerCase();
  for (const [key, unit] of KNOWN_UNITS) {
    if (lower.includes(key)) return { value: result, units: unit };
  }
  return { value: result, units: "" };
}

/* ──────────────────────────────────────────────
   Shared Components
   ────────────────────────────────────────────── */

function FieldRow({ label, value, unit }: { label: string; value: string; unit?: string }) {
  if (!value) return null;
  return (
    <div className="flex justify-between py-1.5 border-b border-border/50 last:border-0">
      <span className="text-muted-foreground text-sm">{label}</span>
      <span className="text-sm font-medium">
        {value}
        {unit && <span className="text-muted-foreground font-normal ml-1">{unit}</span>}
      </span>
    </div>
  );
}

/* ──────────────────────────────────────────────
   Lab Section — one category
   ────────────────────────────────────────────── */

const LabSection = React.memo(function LabSection({
  categoryName,
  rows,
}: {
  categoryName: string;
  rows: Record<string, string>[];
}) {
  const config = getCategoryConfig(categoryName);
  const Icon = config?.icon || Stethoscope;
  const iconBg = config?.iconBg || "bg-gray-500";

  return (
    <div className="mb-5 last:mb-0">
      {/* Category header */}
      <div className="flex items-center gap-2 mb-2">
        <div
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${iconBg} text-white`}
        >
          <Icon className="h-3 w-3" />
        </div>
        <h3 className="text-xs font-bold uppercase tracking-wider text-gray-700 dark:text-gray-300">
          {categoryName}
        </h3>
      </div>

      {/* 5-column results table */}
      <table className="w-full text-sm border-collapse border border-gray-200 dark:border-gray-700 print:border-gray-400">
        <thead>
          <tr className="bg-gray-50 dark:bg-gray-800/50 print:bg-gray-100">
            <th className="py-1.5 px-3 text-left text-[11px] font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700 w-8">
              #
            </th>
            <th className="py-1.5 px-3 text-left text-[11px] font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
              Parameter
            </th>
            <th className="py-1.5 px-3 text-left text-[11px] font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
              Result
            </th>
            <th className="py-1.5 px-3 text-left text-[11px] font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
              Units
            </th>
            <th className="py-1.5 px-3 text-left text-[11px] font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
              Reference Range
            </th>
            <th className="py-1.5 px-3 text-left text-[11px] font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
              Notes
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const { value, units } = extractResultAndUnits(row.result || "", row.test_name || "");
            return (
              <tr
                key={i}
                className="border-b border-gray-100 dark:border-gray-800 last:border-0 print:border-gray-300"
              >
                <td className="py-1.5 px-3 text-muted-foreground text-xs">{i + 1}</td>
                <td className="py-1.5 px-3 font-medium text-gray-800 dark:text-gray-200">
                  {row.test_name || "—"}
                </td>
                <td className="py-1.5 px-3 tabular-nums">{value || "—"}</td>
                <td className="py-1.5 px-3 text-muted-foreground">{units || "—"}</td>
                <td className="py-1.5 px-3 text-muted-foreground tabular-nums">
                  {row.ref_value || "—"}
                </td>
                <td className="py-1.5 px-3 text-muted-foreground">{row.note || ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
});

/* ──────────────────────────────────────────────
   Doctor Visit Display
   ────────────────────────────────────────────── */

interface DoctorVisitDisplayProps {
  fields: Record<string, string>;
  tableData: Record<string, Record<string, string>[]>;
  notes: string;
  memberName?: string;
  memberAge?: number;
  memberGender?: string;
  memberBloodGroup?: string;
  providerName?: string;
  recordDate?: string;
  recordTime?: string;
  diagnosis?: string;
  nextReviewDate?: string;
}

const DoctorVisitDisplay = React.memo(function DoctorVisitDisplay({
  fields,
  tableData,
  notes,
  memberName,
  memberAge,
  memberGender,
  memberBloodGroup,
  providerName,
  recordDate,
  recordTime: _recordTime,
  diagnosis,
  nextReviewDate,
}: DoctorVisitDisplayProps) {
  const prescriptions = useMemo(() => tableData["prescriptions"] || [], [tableData]);
  const labResults = useMemo(() => tableData["lab_results"] || [], [tableData]);
  const hasLabResults = labResults.length > 0;
  const hasPrescriptions = prescriptions.length > 0;
  const categories = useMemo(
    () =>
      hasLabResults ? orderedCategories(labResults) : new Map<string, Record<string, string>[]>(),
    [hasLabResults, labResults]
  );

  const formattedDate = recordDate ? formatDate(recordDate) : null;
  const formattedReview = nextReviewDate ? formatDate(nextReviewDate) : null;

  // Build sections array for rendering with explicit borders
  const sections: { label: string; content: React.ReactNode }[] = [];

  // Structured header matching the reference format
  const hasHeader =
    formattedDate ||
    memberName ||
    providerName ||
    diagnosis ||
    fields.chief_complaint ||
    fields.existing_conditions ||
    formattedReview;

  if (hasHeader) {
    sections.push({
      label: "",
      content: (
        <div className="space-y-2.5 pb-1">
          {/* Row 1: Date + Review */}
          {(formattedDate || formattedReview) && (
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
              {formattedDate && (
                <div>
                  <span className="font-semibold">Date:</span> {formattedDate}
                </div>
              )}
              {formattedReview && (
                <div>
                  <span className="font-semibold">Review:</span> {formattedReview}
                </div>
              )}
            </div>
          )}
          {/* Row 2: Patient + Provider */}
          {(memberName || providerName) && (
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
              {memberName && (
                <div>
                  <span className="font-semibold">Patient:</span> {memberName}
                  {memberAge !== undefined && memberGender && ` (${memberAge}y, ${memberGender})`}
                  {memberBloodGroup && ` · BG: ${memberBloodGroup}`}
                </div>
              )}
              {providerName && (
                <div>
                  <span className="font-semibold">Provider:</span> {providerName}
                </div>
              )}
            </div>
          )}
          {/* Chief Complaint */}
          {fields.chief_complaint && (
            <div className="text-sm">
              <span className="font-semibold">Chief Complaint:</span> {fields.chief_complaint}
            </div>
          )}
          {/* Diagnosis */}
          {diagnosis && (
            <div className="text-sm">
              <span className="font-semibold">Diagnosis:</span> {diagnosis}
            </div>
          )}
          {/* Existing Conditions */}
          {fields.existing_conditions && (
            <div className="text-sm">
              <span className="font-semibold">Existing Conditions:</span>{" "}
              {fields.existing_conditions}
            </div>
          )}
        </div>
      ),
    });
  }

  if (fields.chief_complaint && !hasHeader) {
    sections.push({
      label: "Chief Complaint",
      content: (
        <p className="text-sm whitespace-pre-wrap leading-relaxed">{fields.chief_complaint}</p>
      ),
    });
  }

  if (fields.investigations) {
    sections.push({
      label: "Investigations",
      content: (
        <p className="text-sm whitespace-pre-wrap leading-relaxed">{fields.investigations}</p>
      ),
    });
  }

  if (hasPrescriptions) {
    sections.push({
      label: "Prescription",
      content: (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse border border-gray-200 dark:border-gray-700">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-800/50">
                <th className="py-1.5 px-3 text-left text-[11px] font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  Type
                </th>
                <th className="py-1.5 px-3 text-left text-[11px] font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  Medicine
                </th>
                <th className="py-1.5 px-3 text-left text-[11px] font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  Dosage
                </th>
                <th className="py-1.5 px-3 text-left text-[11px] font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  Duration
                </th>
                <th className="py-1.5 px-3 text-left text-[11px] font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  Timing
                </th>
                <th className="py-1.5 px-3 text-left text-[11px] font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  Note
                </th>
              </tr>
            </thead>
            <tbody>
              {prescriptions.map((row, i) => (
                <tr key={i} className="border-b border-gray-100 dark:border-gray-800 last:border-0">
                  <td className="py-1.5 px-3">{row.type || ""}</td>
                  <td className="py-1.5 px-3 font-medium">{row.medicine || ""}</td>
                  <td className="py-1.5 px-3">{row.dosage || ""}</td>
                  <td className="py-1.5 px-3">{row.duration || ""}</td>
                  <td className="py-1.5 px-3">{row.timing ? row.timing.replace(/_/g, " ") : ""}</td>
                  <td className="py-1.5 px-3 text-muted-foreground">{row.note || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ),
    });
  }

  if (hasLabResults) {
    sections.push({
      label: "Lab Results",
      content: (
        <div className="lab-report-container">
          {/* Patient info bar */}
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs text-muted-foreground/60">
              DAWNSTAR Family Health Keeper
              {recordDate && ` · ${formatDate(recordDate)}`}
            </p>
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              {memberName && <span>{memberName}</span>}
              {memberAge !== undefined && memberGender && (
                <>
                  <span className="text-muted-foreground/40">·</span>
                  <span>
                    {memberAge}y / {memberGender}
                  </span>
                </>
              )}
              {memberBloodGroup && (
                <>
                  <span className="text-muted-foreground/40">·</span>
                  <span>BG: {memberBloodGroup}</span>
                </>
              )}
            </div>
          </div>

          {/* Categorized test sections */}
          {Array.from(categories.entries()).map(([catName, rows]) => (
            <LabSection key={catName} categoryName={catName} rows={rows} />
          ))}

          <div className="text-[11px] text-muted-foreground mt-3 pt-2 border-t border-gray-200 dark:border-gray-700">
            {labResults.length} test{labResults.length !== 1 ? "s" : ""} reported
          </div>
        </div>
      ),
    });
  }

  if (notes && notes.trim().length > 0) {
    // Skip displaying notes that are just a filename or very short source reference
    const trimmed = notes.trim();
    const looksLikeFileName =
      /\.(pdf|png|jpg|jpeg|doc|docx)$/i.test(trimmed) && trimmed.length < 80;
    if (!looksLikeFileName) {
      sections.push({
        label: "Notes",
        content: <p className="text-sm whitespace-pre-wrap leading-relaxed">{notes}</p>,
      });
    }
  }

  return (
    <div>
      {sections.map((section, i) => (
        <div
          key={section.label}
          className={i > 0 ? "border-t border-gray-200 dark:border-gray-700 pt-4 mt-4" : ""}
        >
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            {section.label}
          </p>
          {section.content}
        </div>
      ))}
    </div>
  );
});

/* ──────────────────────────────────────────────
   Consolidated Lab Report (standalone)
   ────────────────────────────────────────────── */

interface ConsolidatedLabReportProps {
  tableRows: Record<string, string>[];
  notes: string;
  memberName?: string;
  memberAge?: number;
  memberGender?: string;
  memberBloodGroup?: string;
  providerName?: string;
  recordDate?: string;
  recordTime?: string;
}

const ConsolidatedLabReport = React.memo(function ConsolidatedLabReport({
  tableRows,
  notes,
  memberName,
  memberAge,
  memberGender,
  memberBloodGroup,
  providerName,
  recordDate,
  recordTime,
}: ConsolidatedLabReportProps) {
  const categories = useMemo(() => orderedCategories(tableRows), [tableRows]);

  if (tableRows.length === 0 && !notes) {
    return <p className="text-sm text-muted-foreground">No test data.</p>;
  }

  const dateStr = recordDate ? formatDate(recordDate) : "";
  const reportId = recordDate ? `LR-${recordDate.replace(/-/g, "")}` : "LR-00000000";

  return (
    <div className="lab-report-container">
      {/* ── Report Header ── */}
      <div className="border-b-2 border-gray-300 dark:border-gray-600 pb-3 mb-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold tracking-tight text-gray-900 dark:text-gray-100">
              Consolidated Lab Report
            </h2>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              DAWNSTAR Family Health Keeper
            </p>
          </div>
          <div className="text-right text-[11px] text-muted-foreground">
            <p>
              Report ID: <span className="font-mono">{reportId}</span>
            </p>
            <p>
              {dateStr}
              {recordTime ? ` at ${recordTime}` : ""}
            </p>
          </div>
        </div>
      </div>

      {/* ── Patient Info ── */}
      <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-[13px] mb-4 pb-3 border-b border-border/50">
        {memberName && (
          <div className="flex gap-2">
            <span className="text-muted-foreground w-24 shrink-0 text-[11px] uppercase tracking-wider">
              Patient
            </span>
            <span className="font-semibold">{memberName}</span>
          </div>
        )}
        {memberAge !== undefined && memberGender && (
          <div className="flex gap-2">
            <span className="text-muted-foreground w-24 shrink-0 text-[11px] uppercase tracking-wider">
              Age / Sex
            </span>
            <span>
              {memberAge} yrs / {memberGender}
            </span>
          </div>
        )}
        {memberBloodGroup && (
          <div className="flex gap-2">
            <span className="text-muted-foreground w-24 shrink-0 text-[11px] uppercase tracking-wider">
              Blood Group
            </span>
            <span className="font-semibold">{memberBloodGroup}</span>
          </div>
        )}
        {providerName && (
          <div className="flex gap-2">
            <span className="text-muted-foreground w-24 shrink-0 text-[11px] uppercase tracking-wider">
              Lab / Provider
            </span>
            <span>{providerName}</span>
          </div>
        )}
      </div>

      {/* ── Categorized Test Sections ── */}
      {Array.from(categories.entries()).map(([catName, rows]) => (
        <LabSection key={catName} categoryName={catName} rows={rows} />
      ))}

      {/* ── Notes ── */}
      {notes &&
        notes.trim().length > 0 &&
        !/\.(pdf|png|jpg|jpeg|doc|docx)$/i.test(notes.trim()) && (
          <div className="mb-4 mt-4 pt-2 border-t border-gray-200 dark:border-gray-700">
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">
              Notes
            </p>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">{notes}</p>
          </div>
        )}

      {/* ── Footer ── */}
      <div className="pt-3 mt-4 border-t-2 border-gray-300 dark:border-gray-600">
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          <strong>Disclaimer:</strong> This report is auto-generated from recorded data and is for
          informational purposes only. Values should be reviewed by a qualified healthcare
          professional.
        </p>
        <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground/60">
          <span>DAWNSTAR Family Health Keeper</span>
          <span>
            {reportId} &middot; {dateStr}
          </span>
        </div>
      </div>
    </div>
  );
});

/* ──────────────────────────────────────────────
   Eyeglass Display
   ────────────────────────────────────────────── */

const EyeglassDisplay = React.memo(function EyeglassDisplay({
  fields,
  notes,
}: {
  fields: Record<string, string>;
  notes: string;
}) {
  return (
    <div className="space-y-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className="py-1.5 text-left text-muted-foreground"></th>
            <th className="py-1.5 text-center text-muted-foreground font-medium">SPH</th>
            <th className="py-1.5 text-center text-muted-foreground font-medium">CYL</th>
            <th className="py-1.5 text-center text-muted-foreground font-medium">AXS</th>
            <th className="py-1.5 text-center text-muted-foreground font-medium">VA</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-border/50">
            <td className="py-1.5 text-muted-foreground font-medium">RE</td>
            <td className="py-1.5 text-center">{fields.re_sph || "—"}</td>
            <td className="py-1.5 text-center">{fields.re_cyl || "—"}</td>
            <td className="py-1.5 text-center">{fields.re_axs || "—"}</td>
            <td className="py-1.5 text-center">{fields.re_va || "—"}</td>
          </tr>
          <tr className="border-b border-border/50">
            <td className="py-1.5 text-muted-foreground font-medium">LE</td>
            <td className="py-1.5 text-center">{fields.le_sph || "—"}</td>
            <td className="py-1.5 text-center">{fields.le_cyl || "—"}</td>
            <td className="py-1.5 text-center">{fields.le_axs || "—"}</td>
            <td className="py-1.5 text-center">{fields.le_va || "—"}</td>
          </tr>
          {(fields.add_power || fields.pd) && (
            <tr>
              <td className="py-1.5 text-muted-foreground font-medium">ADD</td>
              <td className="py-1.5 text-center" colSpan={2}>
                {fields.add_power || "—"}
              </td>
              <td className="py-1.5 text-muted-foreground font-medium text-right">PD:</td>
              <td className="py-1.5 text-center">{fields.pd || "—"}</td>
            </tr>
          )}
        </tbody>
      </table>
      {notes && <p className="text-sm text-muted-foreground whitespace-pre-wrap">{notes}</p>}
    </div>
  );
});

/* ──────────────────────────────────────────────
   Blood Glucose Display
   ────────────────────────────────────────────── */

const BloodGlucoseDisplay = React.memo(function BloodGlucoseDisplay({
  fields,
}: {
  fields: Record<string, string>;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-baseline gap-2">
        {fields.glucose_value && (
          <>
            <span className="text-3xl font-bold">{fields.glucose_value}</span>
            <span className="text-muted-foreground">mg/dL</span>
          </>
        )}
      </div>
      {fields.meal_timing && (
        <FieldRow label="Timing" value={fields.meal_timing.replace(/_/g, " ")} />
      )}
    </div>
  );
});

/* ──────────────────────────────────────────────
   Main Display Component
   ────────────────────────────────────────────── */

export const StructuredDataDisplay = React.memo(function StructuredDataDisplay({
  recordType,
  clinicalData,
  memberName,
  memberAge,
  memberGender,
  memberBloodGroup,
  providerName,
  recordDate,
  recordTime,
  diagnosis,
  nextReviewDate,
}: StructuredDataDisplayProps) {
  const parsed = deserializeClinicalData(clinicalData);

  // Legacy plain text
  if (!parsed.isStructured) {
    return (
      <p className="text-sm whitespace-pre-wrap">{parsed.fields.clinical_data || clinicalData}</p>
    );
  }

  const { fields, tableRows, tableData, notes } = parsed;

  switch (recordType) {
    case "doctor_visit":
      return (
        <DoctorVisitDisplay
          fields={fields}
          tableData={tableData}
          notes={notes}
          memberName={memberName}
          memberAge={memberAge}
          memberGender={memberGender}
          memberBloodGroup={memberBloodGroup}
          providerName={providerName}
          recordDate={recordDate}
          recordTime={recordTime}
          diagnosis={diagnosis}
          nextReviewDate={nextReviewDate}
        />
      );
    case "lab_report":
      return (
        <ConsolidatedLabReport
          tableRows={tableRows}
          notes={notes}
          memberName={memberName}
          memberAge={memberAge}
          memberGender={memberGender}
          memberBloodGroup={memberBloodGroup}
          providerName={providerName}
          recordDate={recordDate}
          recordTime={recordTime}
        />
      );
    case "rx_eyeglass":
      return <EyeglassDisplay fields={fields} notes={notes} />;
    case "blood_glucose":
      return <BloodGlucoseDisplay fields={fields} />;
    default:
      return (
        <div className="space-y-2">
          {Object.entries(fields).map(([key, value]) =>
            value ? <FieldRow key={key} label={key.replace(/_/g, " ")} value={value} /> : null
          )}
          {notes && <p className="text-sm whitespace-pre-wrap">{notes}</p>}
        </div>
      );
  }
});
