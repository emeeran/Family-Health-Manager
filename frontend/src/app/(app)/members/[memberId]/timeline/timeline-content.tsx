import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { RecordTypeBadge } from "@/components/records/record-type-badge";
import { EmptyState } from "@/components/shared/empty-state";
import {
  Clock,
  Filter,
  ChevronDown,
  Activity,
  Droplets,
  AlertTriangle,
  Pill,
  TestTube,
  Stethoscope,
  FileText,
  ChevronRight,
} from "lucide-react";
import { formatDate } from "@/lib/utils";
import { deserializeClinicalData } from "@/lib/clinical-data";
import type { HealthRecordResponse } from "@/lib/types/health-record";
import type { FamilyMemberResponse } from "@/lib/types/member";
import type { RecordType } from "@/lib/types/enums";

/* ── Types ── */

interface AbnormalResult {
  name: string;
  result: string;
  ref: string;
  note: string;
}

interface ExtractedMetrics {
  hba1c: { value: number; category: string } | null;
  glucose: { value: number; timing: string } | null;
  prescriptionCount: number;
  labTestCount: number;
  chiefComplaint: string | null;
  abnormals: AbnormalResult[];
}

/* ── Filter groups ── */

const FILTER_OPTIONS: {
  key: string;
  label: string;
  type: RecordType | null;
  icon: React.ReactNode;
}[] = [
  { key: "all", label: "All", type: null, icon: <Filter className="h-3 w-3" /> },
  {
    key: "doctor_visit",
    label: "Visits",
    type: "doctor_visit",
    icon: <Stethoscope className="h-3 w-3" />,
  },
  { key: "lab_report", label: "Labs", type: "lab_report", icon: <TestTube className="h-3 w-3" /> },
  {
    key: "blood_glucose",
    label: "Glucose",
    type: "blood_glucose",
    icon: <Droplets className="h-3 w-3" />,
  },
  { key: "vitals", label: "Vitals", type: "vitals", icon: <Activity className="h-3 w-3" /> },
  {
    key: "misc_record",
    label: "Other",
    type: "misc_record",
    icon: <FileText className="h-3 w-3" />,
  },
];

/* ── Data extraction helpers ── */

function getHba1cCategory(val: number): string {
  if (val < 5.7) return "Normal";
  if (val < 6.5) return "Prediabetes";
  return "Diabetes";
}

function extractMetrics(clinicalData: string): ExtractedMetrics {
  const parsed = deserializeClinicalData(clinicalData);
  const result: ExtractedMetrics = {
    hba1c: null,
    glucose: null,
    prescriptionCount: 0,
    labTestCount: 0,
    chiefComplaint: null,
    abnormals: [],
  };

  if (parsed.isStructured) {
    result.chiefComplaint = parsed.fields.chief_complaint || null;

    // Prescriptions
    const rxs = parsed.tableData["prescriptions"] || [];
    result.prescriptionCount = rxs.length;

    // Lab results
    const labs = parsed.tableData["lab_results"] || parsed.tableRows || [];
    result.labTestCount = labs.length;

    // Extract HbA1c
    for (const lab of labs) {
      const name = (lab.test_name || "").toLowerCase();
      const val = parseFloat(lab.result || "");
      if (!isNaN(val)) {
        if (name.includes("hba1c") && !result.hba1c) {
          result.hba1c = { value: val, category: getHba1cCategory(val) };
        }
        if (
          (name.includes("glucose") || name.includes("blood sugar")) &&
          name.includes("postprandial") &&
          !result.glucose
        ) {
          result.glucose = { value: val, timing: "PP" };
        }
        if (
          (name.includes("glucose") || name.includes("blood sugar")) &&
          !name.includes("postprandial") &&
          name.includes("fasting") &&
          !result.glucose
        ) {
          result.glucose = { value: val, timing: "Fasting" };
        }
        if ((name.includes("glucose") || name.includes("blood sugar")) && !result.glucose) {
          result.glucose = { value: val, timing: "" };
        }
      }

      // Collect abnormals
      const note = (lab.note || "").toLowerCase();
      if (note.includes("elevated") || note.includes("high") || note.includes("above target")) {
        result.abnormals.push({
          name: lab.test_name || "",
          result: lab.result || "",
          ref: lab.ref_value || "",
          note: lab.note || "",
        });
      }
    }

    // Blood glucose type records
    if (parsed.fields.glucose_value) {
      const gVal = parseFloat(parsed.fields.glucose_value);
      if (!isNaN(gVal)) {
        result.glucose = {
          value: gVal,
          timing: (parsed.fields.meal_timing || "").replace(/_/g, " "),
        };
      }
    }
    if (parsed.fields.hba1c_value) {
      const hVal = parseFloat(parsed.fields.hba1c_value);
      if (!isNaN(hVal)) {
        result.hba1c = { value: hVal, category: getHba1cCategory(hVal) };
      }
    }
  } else {
    // Unstructured — try regex for glucose / HbA1c
    const text = parsed.fields.clinical_data || clinicalData;
    const hba1cMatch = text.match(/hba1c[^:]*?[:\s]+([\d.]+)/i);
    if (hba1cMatch) {
      const val = parseFloat(hba1cMatch[1]);
      if (!isNaN(val)) result.hba1c = { value: val, category: getHba1cCategory(val) };
    }
    const glucoseMatch = text.match(/(?:glucose|blood sugar)[^:]*?[:\s]+([\d.]+)/i);
    if (glucoseMatch) {
      const val = parseFloat(glucoseMatch[1]);
      if (!isNaN(val)) result.glucose = { value: val, timing: "" };
    }
  }

  return result;
}

/* ── Diabetes Summary Card ── */

function DiabetesSummaryCard({ items }: { items: HealthRecordResponse[] }) {
  const latestMetrics = useMemo(() => {
    let latestHba1c: { value: number; category: string; date: string } | null = null;
    let latestGlucose: { value: number; timing: string; date: string } | null = null;
    let totalPrescriptions = 0;
    let totalAbnormals = 0;

    for (const item of items) {
      const m = extractMetrics(item.clinical_data);
      if (m.hba1c && (!latestHba1c || item.record_date > latestHba1c.date)) {
        latestHba1c = { ...m.hba1c, date: item.record_date };
      }
      if (m.glucose && (!latestGlucose || item.record_date > latestGlucose.date)) {
        latestGlucose = { ...m.glucose, date: item.record_date };
      }
      totalPrescriptions = Math.max(totalPrescriptions, m.prescriptionCount);
      totalAbnormals += m.abnormals.length;
    }

    return { latestHba1c, latestGlucose, totalPrescriptions, totalAbnormals };
  }, [items]);

  if (!latestMetrics.latestHba1c && !latestMetrics.latestGlucose) return null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {/* HbA1c */}
      <div className="flex items-center gap-3 rounded-xl border border-border/60 bg-card px-4 py-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-500/10">
          <Activity className="h-4 w-4 text-blue-500" />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Latest HbA1c</p>
          {latestMetrics.latestHba1c ? (
            <div className="flex items-center gap-1.5">
              <p className="text-lg font-bold leading-none">{latestMetrics.latestHba1c.value}%</p>
              <span
                className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-md ${
                  latestMetrics.latestHba1c.category === "Normal"
                    ? "bg-green-500/10 text-green-600"
                    : latestMetrics.latestHba1c.category === "Prediabetes"
                      ? "bg-amber-500/10 text-amber-600"
                      : "bg-red-500/10 text-red-600"
                }`}
              >
                {latestMetrics.latestHba1c.category}
              </span>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">N/A</p>
          )}
        </div>
      </div>

      {/* Glucose */}
      <div className="flex items-center gap-3 rounded-xl border border-border/60 bg-card px-4 py-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-500/10">
          <Droplets className="h-4 w-4 text-amber-500" />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Latest Glucose</p>
          {latestMetrics.latestGlucose ? (
            <div className="flex items-center gap-1">
              <p className="text-lg font-bold leading-none">{latestMetrics.latestGlucose.value}</p>
              <span className="text-xs text-muted-foreground">mg/dL</span>
              {latestMetrics.latestGlucose.timing && (
                <span className="text-[10px] text-muted-foreground">
                  ({latestMetrics.latestGlucose.timing})
                </span>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">N/A</p>
          )}
        </div>
      </div>

      {/* Medications */}
      <div className="flex items-center gap-3 rounded-xl border border-border/60 bg-card px-4 py-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-500/10">
          <Pill className="h-4 w-4 text-violet-500" />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Medications</p>
          <p className="text-lg font-bold leading-none">{latestMetrics.totalPrescriptions}</p>
          <p className="text-[10px] text-muted-foreground">in latest visit</p>
        </div>
      </div>

      {/* Abnormal flags */}
      <div className="flex items-center gap-3 rounded-xl border border-border/60 bg-card px-4 py-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-red-500/10">
          <AlertTriangle className="h-4 w-4 text-red-500" />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Abnormal Tests</p>
          <p className="text-lg font-bold leading-none">{latestMetrics.totalAbnormals}</p>
          <p className="text-[10px] text-muted-foreground">across all records</p>
        </div>
      </div>
    </div>
  );
}

/* ── Structured Preview (per card) ── */

function StructuredPreview({ record }: { record: HealthRecordResponse }) {
  const metrics = useMemo(() => extractMetrics(record.clinical_data), [record.clinical_data]);

  // Count displayable elements
  const hasContent =
    metrics.chiefComplaint ||
    metrics.prescriptionCount > 0 ||
    metrics.labTestCount > 0 ||
    metrics.hba1c ||
    metrics.glucose ||
    metrics.abnormals.length > 0;

  if (!hasContent) {
    // Fallback: show raw text (truncated)
    const text = record.clinical_data;
    if (!text) return null;
    try {
      const parsed = JSON.parse(text);
      if (parsed._type === "structured") {
        return (
          <p className="text-xs text-muted-foreground mt-1">
            Structured health record with multiple data sections
          </p>
        );
      }
    } catch {
      /* not JSON */
    }
    return <p className="text-xs text-muted-foreground line-clamp-2 mt-1">{text}</p>;
  }

  return (
    <div className="mt-2 space-y-1.5">
      {/* Chief complaint */}
      {metrics.chiefComplaint && (
        <p className="text-xs text-muted-foreground italic">{metrics.chiefComplaint}</p>
      )}

      {/* Key metrics row */}
      {(metrics.hba1c || metrics.glucose) && (
        <div className="flex flex-wrap items-center gap-1.5">
          {metrics.hba1c && (
            <span
              className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                metrics.hba1c.category === "Normal"
                  ? "bg-green-500/10 text-green-600"
                  : metrics.hba1c.category === "Prediabetes"
                    ? "bg-amber-500/10 text-amber-600"
                    : "bg-red-500/10 text-red-600"
              }`}
            >
              <Activity className="h-3 w-3" />
              HbA1c {metrics.hba1c.value}%
            </span>
          )}
          {metrics.glucose && (
            <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-600">
              <Droplets className="h-3 w-3" />
              {metrics.glucose.value} mg/dL
              {metrics.glucose.timing ? ` (${metrics.glucose.timing})` : ""}
            </span>
          )}
        </div>
      )}

      {/* Counts + abnormals */}
      <div className="flex flex-wrap items-center gap-1.5">
        {metrics.prescriptionCount > 0 && (
          <span className="inline-flex items-center gap-1 rounded-md bg-violet-500/10 px-2 py-0.5 text-[11px] font-semibold text-violet-600">
            <Pill className="h-3 w-3" />
            {metrics.prescriptionCount} Rx
          </span>
        )}
        {metrics.labTestCount > 0 && (
          <span className="inline-flex items-center gap-1 rounded-md bg-blue-500/10 px-2 py-0.5 text-[11px] font-semibold text-blue-600">
            <TestTube className="h-3 w-3" />
            {metrics.labTestCount} tests
          </span>
        )}
        {metrics.abnormals.length > 0 && (
          <span className="inline-flex items-center gap-1 rounded-md bg-red-500/10 px-2 py-0.5 text-[11px] font-semibold text-red-600">
            <AlertTriangle className="h-3 w-3" />
            {metrics.abnormals.length} abnormal
          </span>
        )}
      </div>

      {/* Top abnormal highlights */}
      {metrics.abnormals.length > 0 && (
        <div className="flex flex-col gap-0.5 mt-1">
          {metrics.abnormals.slice(0, 4).map((ab, i) => (
            <div key={i} className="flex items-center gap-2 text-[11px]">
              <span className="text-red-500 font-medium truncate max-w-[140px]">{ab.name}</span>
              <span className="text-muted-foreground">
                {ab.result}
                {ab.ref && <span className="text-red-400"> (ref: {ab.ref})</span>}
              </span>
            </div>
          ))}
          {metrics.abnormals.length > 4 && (
            <span className="text-[10px] text-muted-foreground">
              +{metrics.abnormals.length - 4} more abnormal results
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Props ── */

interface TimelineContentProps {
  items: HealthRecordResponse[];
  member: FamilyMemberResponse;
  hasMore?: boolean;
  onLoadMore?: () => void;
  loadingMore?: boolean;
  onFilterChange?: (recordType: RecordType | null) => void;
  activeFilter?: RecordType | null;
}

/* ── Main component ── */

export function TimelineContent({
  items,
  member,
  hasMore = false,
  onLoadMore,
  loadingMore = false,
  onFilterChange,
  activeFilter: _activeFilter,
}: TimelineContentProps) {
  const [localFilter, setLocalFilter] = useState<string>("all");

  const filteredItems = useMemo(() => {
    if (localFilter === "all") return items;
    const group = FILTER_OPTIONS.find((g) => g.key === localFilter);
    if (group?.type) return items.filter((item) => item.record_type === group.type);
    return items;
  }, [items, localFilter]);

  function handleFilterChange(key: string) {
    setLocalFilter(key);
    const group = FILTER_OPTIONS.find((g) => g.key === key);
    onFilterChange?.(group?.type ?? null);
  }

  /* ── Empty state ── */
  if (items.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Link to={`/members/${member.id}`} className="hover:underline">
            {member.first_name} {member.last_name}
          </Link>
          <span>/</span>
          <span className="text-foreground">Timeline</span>
        </div>
        <EmptyState
          icon={<Clock className="h-12 w-12" />}
          title="No timeline entries"
          description="Health records will appear here in chronological order."
        />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Breadcrumbs */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/members" className="hover:underline">
          Members
        </Link>
        <span>/</span>
        <Link to={`/members/${member.id}`} className="hover:underline">
          {member.first_name} {member.last_name}
        </Link>
        <span>/</span>
        <span className="text-foreground">Timeline</span>
      </div>

      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Timeline</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {items.length} record{items.length !== 1 ? "s" : ""}
            {localFilter !== "all" && ` · filtered`}
          </p>
        </div>
      </div>

      {/* Diabetes summary */}
      <DiabetesSummaryCard items={items} />

      {/* Filter bar */}
      <div className="flex items-center gap-1 flex-wrap">
        {FILTER_OPTIONS.map((g) => (
          <button
            key={g.key}
            onClick={() => handleFilterChange(g.key)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
              localFilter === g.key
                ? "bg-(--brand-primary)/10 text-(--brand-primary) dark:text-(--brand-accent) shadow-sm"
                : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            }`}
          >
            {g.icon}
            {g.label}
          </button>
        ))}
      </div>

      {/* Timeline */}
      {filteredItems.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-sm text-muted-foreground">No records match this filter.</p>
        </div>
      ) : (
        <div className="relative space-y-0">
          {filteredItems.map((item, idx) => (
            <TimelineItem
              key={item.id}
              item={item}
              memberId={member.id}
              isLast={idx === filteredItems.length - 1}
            />
          ))}
        </div>
      )}

      {/* Load more */}
      {hasMore && (
        <div className="flex justify-center pt-2">
          <button
            onClick={onLoadMore}
            disabled={loadingMore}
            className="inline-flex items-center gap-2 rounded-lg border border-border/60 px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all disabled:opacity-50"
          >
            <ChevronDown className={`h-4 w-4 ${loadingMore ? "animate-bounce" : ""}`} />
            {loadingMore ? "Loading..." : "Load more records"}
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Timeline item ── */

function TimelineItem({
  item,
  memberId,
  isLast,
}: {
  item: HealthRecordResponse;
  memberId: string;
  isLast: boolean;
}) {
  const isDoctorVisit = item.record_type === "doctor_visit";
  const isLab = item.record_type === "lab_report";
  const dotColor = isDoctorVisit
    ? "bg-blue-500"
    : isLab
      ? "bg-teal-500"
      : item.record_type === "blood_glucose"
        ? "bg-amber-500"
        : item.record_type === "vitals"
          ? "bg-green-500"
          : "bg-primary";

  return (
    <div className="relative pl-8 pb-8">
      {/* Vertical line */}
      {!isLast && <div className="absolute left-[11px] top-6 bottom-0 w-px bg-border" />}
      {/* Dot */}
      <div className="absolute left-0 top-1.5 h-6 w-6 rounded-full bg-muted flex items-center justify-center">
        <div className={`h-2.5 w-2.5 rounded-full ${dotColor}`} />
      </div>

      <Card className="group hover:shadow-md hover:border-border transition-all duration-200">
        <CardContent className="pt-4 pb-4">
          <Link to={`/members/${memberId}/records/${item.id}`} className="block">
            {/* Header row */}
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2">
                <RecordTypeBadge type={item.record_type} />
                {item.next_review_date && (
                  <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-600">
                    Follow-up {formatDate(item.next_review_date)}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>{formatDate(item.record_date)}</span>
                {item.record_time && <span>{item.record_time}</span>}
              </div>
            </div>

            {/* Diagnosis */}
            {item.diagnosis && <p className="text-sm font-semibold">{item.diagnosis}</p>}

            {/* Provider */}
            {item.provider_name && (
              <p className="text-xs text-muted-foreground mt-0.5">{item.provider_name}</p>
            )}

            {/* Structured preview */}
            <StructuredPreview record={item} />

            {/* View detail chevron */}
            <div className="flex items-center justify-end mt-2">
              <span className="text-xs text-muted-foreground/50 group-hover:text-(--brand-primary) transition-colors flex items-center gap-0.5">
                View details <ChevronRight className="h-3 w-3" />
              </span>
            </div>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
