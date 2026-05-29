import React, { useState, useEffect, useMemo, lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { InsightCard } from "@/components/members/insight-card";
import { PreConsultationCard } from "@/components/members/pre-consultation-card";
import { ActiveMedicationsTable } from "@/components/members/active-medications-table";
import { DrugInteractionReport } from "@/components/members/drug-interaction-report";
import { VaccinationsSection } from "@/components/members/vaccinations-section";
import { ChronicConditionCharts } from "@/components/members/chronic-condition-charts";
import { ProvidersUhidCard } from "@/components/members/providers-uhid-card";
import {
  InsightReport,
  PreConsultationNoteViewer,
  parseSections,
} from "@/components/members/insight-report-viewer";
import {
  GENDER_LABELS,
  RELATIONSHIP_LABELS,
  HBA1C_CATEGORY_COLORS,
  RECORD_TYPE_LABELS,
} from "@/lib/constants";
import {
  deleteMember,
  getHba1cHistory,
  getPreventiveRecommendations,
  createPreventiveReminder,
  getLatestDrugInteractions,
  getLatestPreConsultationNote,
  getLatestInsight,
} from "@/lib/api/members";
import { listReminders } from "@/lib/api/reminders";
import { listRecords } from "@/lib/api/records";
import { getRiskAssessment } from "@/lib/api/dashboard";
import { formatDate, formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

import {
  FileText,
  Activity,
  FlaskConical,
  Users,
  Sparkles,
  Plus,
  Phone,
  Printer,
  TrendingUp,
  TrendingDown,
  Minus,
  ShieldCheck,
  Bell,
  CalendarDays,
  BarChart3,
} from "lucide-react";
import type {
  MemberDashboardResponse,
  Hba1cHistoryEntry,
  PreventiveRecommendation,
} from "@/lib/types/member";
import type { GeneratedInsight } from "@/lib/api/members";
import type { DrugInteraction } from "@/lib/types/member";
import type { ReminderResponse } from "@/lib/types/reminder";
import type { HealthRecordResponse } from "@/lib/types/health-record";

/* ── Lazy-loaded recharts ── */

const LazyHba1cChart = lazy(() =>
  import("recharts").then((mod) => ({
    default: ({
      data,
      minV,
      maxV,
      strokeColor,
    }: {
      data: { date: string; hba1c: number }[];
      minV: number;
      maxV: number;
      strokeColor: string;
    }) => (
      <mod.ResponsiveContainer width="100%" height={220}>
        <mod.LineChart data={data} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
          <defs>
            <linearGradient id="hba1cGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={strokeColor} stopOpacity={0.15} />
              <stop offset="95%" stopColor={strokeColor} stopOpacity={0} />
            </linearGradient>
          </defs>
          <mod.CartesianGrid strokeDasharray="3 3" className="opacity-30" />
          <mod.XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <mod.YAxis domain={[minV, maxV]} tick={{ fontSize: 11 }} />
          <mod.Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e5e7eb" }}
          />
          <mod.ReferenceLine
            y={5.7}
            stroke="#f59e0b"
            strokeDasharray="5 5"
            label={{ value: "Prediabetes", fontSize: 10, fill: "#f59e0b" }}
          />
          <mod.ReferenceLine
            y={6.5}
            stroke="#ef4444"
            strokeDasharray="5 5"
            label={{ value: "Diabetes", fontSize: 10, fill: "#ef4444" }}
          />
          <mod.Area type="monotone" dataKey="hba1c" stroke="none" fill="url(#hba1cGrad)" />
          <mod.Line
            type="monotone"
            dataKey="hba1c"
            stroke={strokeColor}
            strokeWidth={2.5}
            dot={{ r: 4, fill: strokeColor, stroke: "#fff", strokeWidth: 2 }}
            activeDot={{ r: 6, fill: strokeColor, stroke: "#fff", strokeWidth: 2 }}
          />
        </mod.LineChart>
      </mod.ResponsiveContainer>
    ),
  }))
);

function ChartFallback() {
  return (
    <div className="flex items-center justify-center h-[180px] text-sm text-muted-foreground">
      Loading chart...
    </div>
  );
}

/* ── Helpers ── */

function getHba1cCategory(value: number): string {
  if (value < 5.7) return "Normal";
  if (value < 6.5) return "Prediabetes";
  return "Diabetes";
}

function scoreColor(score: number): string {
  if (score >= 75) return "#16a34a";
  if (score >= 50) return "#d97706";
  return "#dc2626";
}

function scoreTextColor(score: number): string {
  if (score >= 75) return "text-green-600";
  if (score >= 50) return "text-amber-600";
  return "text-red-600";
}

/* ── Health Score Ring ── */

function HealthScoreRing({
  score,
  size = 56,
  strokeWidth = 4,
}: {
  score: number;
  size?: number;
  strokeWidth?: number;
}) {
  const r = (size - strokeWidth * 2) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = scoreColor(score);
  const cx = size / 2;

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle
          cx={cx}
          cy={cx}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-muted/20"
        />
        <circle
          cx={cx}
          cy={cx}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cx})`}
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-bold leading-none" style={{ color, fontSize: size * 0.3 }}>
          {score}
        </span>
        <span className="text-[8px] text-muted-foreground -mt-0.5">/100</span>
      </div>
    </div>
  );
}

/* ── Trend Badge ── */

function TrendBadge({
  first,
  latest,
  lowerIsBetter = false,
}: {
  first: number;
  latest: number;
  lowerIsBetter?: boolean;
}) {
  const delta = latest - first;
  const absDelta = Math.abs(delta);
  if (absDelta < 0.1) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Minus className="h-3 w-3" />
        Stable
      </span>
    );
  }
  const improved = lowerIsBetter ? delta < 0 : delta > 0;
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium ${improved ? "text-green-600" : "text-red-500"}`}
    >
      {delta > 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
      {improved ? "Improving" : "Worsening"}
    </span>
  );
}

/* ── Expanded HbA1c Chart ── */

function ExpandedHba1cChart({ data }: { data: Hba1cHistoryEntry[] }) {
  const chartData = data.map((d) => ({ date: d.date.slice(0, 10), hba1c: d.hba1c_value }));
  const first = data[0].hba1c_value;
  const last = data[data.length - 1].hba1c_value;
  const category = getHba1cCategory(last);
  const vals = data.map((d) => d.hba1c_value);
  const minV = Math.floor(Math.min(...vals) * 10 - 5) / 10;
  const maxV = Math.ceil(Math.max(...vals) * 10 + 5) / 10;
  const strokeColor =
    category === "Normal" ? "#10b981" : category === "Prediabetes" ? "#f59e0b" : "#ef4444";

  if (data.length === 1) {
    return (
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold text-muted-foreground">HbA1c</p>
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold">{last}%</span>
            <Badge
              variant="secondary"
              className={`text-[10px] px-1.5 py-0 font-semibold ${HBA1C_CATEGORY_COLORS[category] ?? ""}`}
            >
              {category}
            </Badge>
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">
          Add more readings to see trends over time.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold text-muted-foreground">HbA1c Trend</p>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {first}% → <span className="font-bold text-foreground">{last}%</span>
          </span>
          <Badge
            variant="secondary"
            className={`text-[10px] px-1.5 py-0 font-semibold ${HBA1C_CATEGORY_COLORS[category] ?? ""}`}
          >
            {category}
          </Badge>
          <TrendBadge first={first} latest={last} lowerIsBetter={true} />
        </div>
      </div>
      <Suspense fallback={<ChartFallback />}>
        <LazyHba1cChart data={chartData} minV={minV} maxV={maxV} strokeColor={strokeColor} />
      </Suspense>
    </div>
  );
}

/* ── Preventive Care Table ── */

const PRIORITY_DOT: Record<string, string> = {
  high: "bg-red-500",
  medium: "bg-amber-500",
  low: "bg-blue-500",
};
const PRIORITY_LABEL: Record<string, string> = {
  high: "Due now",
  medium: "Upcoming",
  low: "Optional",
};

function PreventiveCareTable({ memberId }: { memberId: string }) {
  const [recommendations, setRecommendations] = useState<PreventiveRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [settingReminder, setSettingReminder] = useState<string | null>(null);

  useEffect(() => {
    getPreventiveRecommendations(memberId)
      .then((res) => setRecommendations(res.recommendations || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [memberId]);

  async function handleSetReminder(rec: PreventiveRecommendation) {
    setSettingReminder(rec.title);
    try {
      await createPreventiveReminder(memberId, rec);
      toast.success(`Reminder set: ${rec.title}`);
    } catch {
      toast.error("Failed to create reminder");
    } finally {
      setSettingReminder(null);
    }
  }

  if (loading) {
    return (
      <Card className="shadow-none">
        <CardContent className="pt-4 pb-3 space-y-2">
          <div className="text-sm font-semibold flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-blue-500" />
            Preventive Care
          </div>
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-8 bg-muted animate-pulse rounded" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (recommendations.length === 0) return null;

  return (
    <Card className="shadow-none">
      <CardContent className="pt-4 pb-3">
        <div className="text-sm font-semibold flex items-center gap-2 mb-3">
          <ShieldCheck className="h-4 w-4 text-blue-500" />
          Preventive Care
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0 ml-auto">
            {recommendations.length}
          </Badge>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-[10px] text-muted-foreground uppercase tracking-wider">
                <th className="py-2 px-3 font-medium">Priority</th>
                <th className="py-2 px-3 font-medium">Recommendation</th>
                <th className="py-2 px-3 font-medium hidden sm:table-cell">Details</th>
                <th className="py-2 px-3 font-medium hidden md:table-cell">Frequency</th>
                <th className="py-2 px-3 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {recommendations.map((rec, i) => (
                <tr
                  key={i}
                  className="border-b last:border-b-0 hover:bg-muted/30 transition-colors"
                >
                  <td className="py-2 px-3">
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        className={`inline-block h-2 w-2 rounded-full ${PRIORITY_DOT[rec.priority] || PRIORITY_DOT.low}`}
                      />
                      <span className="text-xs font-medium capitalize">
                        {PRIORITY_LABEL[rec.priority] || rec.priority}
                      </span>
                    </span>
                  </td>
                  <td className="py-2 px-3">
                    <span className="font-medium text-xs">{rec.title}</span>
                  </td>
                  <td className="py-2 px-3 text-xs text-muted-foreground hidden sm:table-cell">
                    {rec.description}
                  </td>
                  <td className="py-2 px-3 text-xs text-muted-foreground hidden md:table-cell">
                    {rec.due_interval_months === 0
                      ? "One-time"
                      : rec.due_interval_months >= 12
                        ? `Every ${rec.due_interval_months / 12}y`
                        : `Every ${rec.due_interval_months}mo`}
                  </td>
                  <td className="py-2 px-3 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 text-[11px] px-2"
                      disabled={settingReminder === rec.title}
                      onClick={() => handleSetReminder(rec)}
                    >
                      <Bell className="h-3 w-3 mr-1" />
                      {settingReminder === rec.title ? "..." : "Remind"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ── Score Breakdown (local expanded version) ── */

function ScoreBreakdownExpanded({
  breakdown,
}: {
  breakdown: Record<string, { score: number; max: number; label: string }>;
}) {
  const entries = Object.entries(breakdown);
  if (entries.length === 0) return null;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2">
      {entries.map(([key, val]) => {
        const pct = Math.round((val.score / val.max) * 100);
        const barColor = pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500";
        const textColor =
          pct >= 80 ? "text-green-600" : pct >= 50 ? "text-amber-600" : "text-red-600";
        return (
          <div key={key} className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground capitalize">
                {val.label || key.replace(/_/g, " ")}
              </span>
              <span className={`text-[11px] font-bold ${textColor}`}>
                {val.score}/{val.max}
              </span>
            </div>
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── Quick Actions ── */

const quickActions = [
  {
    label: "Record",
    icon: Plus,
    hrefSuffix: "/records/new",
    color: "text-blue-600 hover:bg-blue-50",
  },
  {
    label: "Records",
    icon: FileText,
    hrefSuffix: "/records",
    color: "text-teal-600 hover:bg-teal-50",
  },
  {
    label: "Timeline",
    icon: Activity,
    hrefSuffix: "/timeline",
    color: "text-amber-600 hover:bg-amber-50",
  },
  {
    label: "Labs",
    icon: FlaskConical,
    hrefSuffix: "/lab-records",
    color: "text-emerald-600 hover:bg-emerald-50",
  },
  {
    label: "Providers",
    icon: Users,
    hrefSuffix: "/providers",
    color: "text-violet-600 hover:bg-violet-50",
  },
  { label: "AI", icon: Sparkles, hrefSuffix: "/ai", color: "text-rose-600 hover:bg-rose-50" },
];

const TYPE_COLORS: Record<string, string> = {
  lab_report: "bg-blue-500",
  blood_glucose: "bg-violet-500",
  doctor_visit: "bg-emerald-500",
  hba1c: "bg-rose-500",
  prescription: "bg-amber-500",
  vaccination: "bg-teal-500",
  imaging: "bg-indigo-500",
  other: "bg-gray-400",
};

function ActivityCell({ count, label }: { count: number; label: string }) {
  const opacity = count === 0 ? 0.08 : count <= 1 ? 0.25 : count <= 3 ? 0.5 : count <= 5 ? 0.75 : 1;
  return (
    <div
      title={`${label}: ${count} records`}
      className="h-3.5 w-3.5 rounded-sm bg-primary cursor-default"
      style={{ opacity }}
    />
  );
}

/* ── Main Component ── */

interface MemberDashboardContentProps {
  dashboard: MemberDashboardResponse;
}

export function MemberDashboardContent({ dashboard }: MemberDashboardContentProps) {
  const navigate = useNavigate();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [insight, setInsight] = useState<GeneratedInsight | null>(null);
  const [preConsultNote, setPreConsultNote] = useState<GeneratedInsight | null>(null);
  const [showPreConsult, setShowPreConsult] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [showScoreDetail, setShowScoreDetail] = useState(false);
  const {
    member,
    brief_medical_history,
    active_medications,
    active_conditions_count,
    active_medications_count,
    age,
    health_score,
    provider_assignments,
  } = dashboard;

  const [hba1cHistory, setHba1cHistory] = useState<Hba1cHistoryEntry[]>([]);
  const [memberReminders, setMemberReminders] = useState<ReminderResponse[]>([]);
  const [drugInteractions, setDrugInteractions] = useState<DrugInteraction[]>([]);
  const [riskAssessment, setRiskAssessment] = useState<{
    risk_level: string;
    factors: { factor: string; severity: string; description: string }[];
  } | null>(null);
  const [memberRecords, setMemberRecords] = useState<HealthRecordResponse[]>([]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getRiskAssessment(member.id).catch(() => null),
      getHba1cHistory(member.id),
      listReminders().catch(() => []),
      getLatestDrugInteractions(member.id).catch(() => ({ interactions: [] })),
      getLatestPreConsultationNote(member.id).catch(() => ({ note: null })),
      getLatestInsight(member.id).catch(() => null),
      listRecords(member.id, { limit: 200 }).catch(() => []),
    ])
      .then(([risk, hba1c, reminders, drugResult, preConsultResult, insightResult, records]) => {
        if (cancelled) return;
        if (risk) setRiskAssessment(risk);
        setHba1cHistory(hba1c);
        if (drugResult?.interactions) setDrugInteractions(drugResult.interactions);
        if (preConsultResult?.note) setPreConsultNote(preConsultResult.note);
        if (insightResult) setInsight(insightResult);
        if (records) setMemberRecords(records.filter((r: HealthRecordResponse) => !r.is_deleted));
        setMemberReminders(
          reminders
            .filter(
              (r: ReminderResponse) =>
                r.is_active &&
                r.family_member_id === member.id &&
                new Date(r.start_datetime) > new Date()
            )
            .sort(
              (a: ReminderResponse, b: ReminderResponse) =>
                new Date(a.start_datetime).getTime() - new Date(b.start_datetime).getTime()
            )
            .slice(0, 3)
        );
      })
      .catch((err) => {
        console.error("[dashboard] fetchData error:", err);
      });
    return () => {
      cancelled = true;
    };
  }, [member.id]);

  async function handleDelete() {
    try {
      await deleteMember(member.id);
      toast.success("Member deleted");
      navigate("/members");
    } catch {
      toast.error("Failed to delete member");
    }
  }

  function handleExportPDF() {
    const esc = (s: string) =>
      s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const mn = `${member.first_name} ${member.last_name}`;
    const now = new Date().toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
    const time = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    const meds = active_medications ?? [];
    const tc = "border:1px solid #CCCCCC;padding:4px 6px;font-size:10px;";
    const th = tc + "background:#F5F5F5;font-weight:bold;font-size:9px;text-align:left;";

    // Parse medical history into labelled sections with bold conditions
    const boldDisease = (text: string) =>
      esc(text).replace(
        /\b(T2D|HT|Hypertension|Diabetes|Parkinson's Disease|Parkinson|Hypothyroidism|Hyperthyroidism|COPD|CKD|CAD|CHF|AFib|Asthma|Arthritis|Osteoarthritis|Rheumatoid|Lupus|Epilepsy|Sclerosis|Cancer|Carcinoma|Melanoma|Neuropathy|Cardiomyopathy|Arrhythmia|Fibromyalgia|Endometriosis|PCOS|Gout|Anemia|Thalassemia|Migraine|GERD|IBS|IBD|Crohn's|Colitis|Cirrhosis|Hepatitis|NASH|NAFLD)\b/gi,
        "<strong>$&</strong>"
      );

    const histParts: string[] = [];
    if (brief_medical_history) {
      const rawParts = brief_medical_history
        .split(";")
        .map((s: string) => s.trim())
        .filter(Boolean);
      for (const part of rawParts) {
        const colonIdx = part.indexOf(":");
        if (colonIdx > 0) {
          const label = part.slice(0, colonIdx).trim();
          const items = part.slice(colonIdx + 1).trim();
          if (label === "Conditions" || label === "Surgeries") {
            histParts.push(
              `<span style="color:#2563eb;font-weight:bold">${esc(label)}:</span> ${boldDisease(items)}`
            );
          } else {
            histParts.push(`<span style="font-weight:600">${esc(label)}:</span> ${esc(items)}`);
          }
        } else {
          histParts.push(boldDisease(part));
        }
      }
    }

    const medRows = meds
      .map((m) => {
        const dose = m.dosage || "--";
        const t = m.timing ? m.timing.replace(/_/g, " ") : "--";
        const prov = m.provider_name || "--";
        const date = m.prescribed_date
          ? new Date(m.prescribed_date).toLocaleDateString("en-GB", {
              day: "2-digit",
              month: "short",
              year: "numeric",
            })
          : "--";
        return `<tr><td style="${tc}">${esc(m.type || "--")}</td><td style="${tc};font-weight:600">${esc(m.medicine)}</td><td style="${tc};white-space:nowrap">${esc(dose)}</td><td style="${tc}">${esc(t)}</td><td style="${tc}">${esc(prov)}</td><td style="${tc};white-space:nowrap">${date}</td></tr>`;
      })
      .join("");

    // Parse insight into sections
    let insightHtml = "";
    if (insight) {
      const skipPatterns = [
        "drug analysis",
        "drug interaction",
        "medication analysis",
        "section-3",
        "section 3",
      ];
      const lines = insight.response.split("\n");
      const sections: { title: string; body: string[] }[] = [];
      let current = { title: "", body: [] as string[] };

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        // Match ### Heading, ## Heading, **Heading**, or numbered heading like "1. Heading"
        const headingMatch = trimmed.match(/^#{1,3}\s+(.+)/) || trimmed.match(/^\*\*(.+?)\*\*$/);
        if (headingMatch) {
          if (current.body.length > 0 || current.title) sections.push(current);
          current = { title: headingMatch[1].replace(/\*\*/g, "").trim(), body: [] };
        } else {
          current.body.push(trimmed);
        }
      }
      if (current.body.length > 0 || current.title) sections.push(current);

      const filtered = sections.filter(
        (s) => !skipPatterns.some((sk) => s.title.toLowerCase().includes(sk))
      );

      const sectionParts = filtered.map((s) => {
        // Clean up body lines: render bold/italic, convert bullet markers
        const bodyLines = s.body.map((l) => {
          let html = esc(l)
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/\*([^*]+)\*/g, "<em>$1</em>");
          // Convert "- item" or "• item" to indented bullet
          if (/^[-•]/.test(l.trim())) {
            html = `<span style="display:inline-block;margin-left:16px">&bull; ${html.replace(/^[-•]\s*/, "")}</span>`;
          }
          // Convert numbered items like "1. text" to indented numbered list
          const numMatch = l.trim().match(/^(\d+)\.\s+(.+)/);
          if (numMatch && !/^#{1,3}/.test(l.trim())) {
            html = `<span style="display:inline-block;margin-left:16px">${numMatch[1]}. ${esc(
              numMatch[2]
            )
              .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
              .replace(/\*([^*]+)\*/g, "<em>$1</em>")}</span>`;
          }
          return html;
        });

        const bodyHtml = bodyLines.join("<br>");
        return s.title
          ? `<div style="margin-bottom:14px;padding:8px 0 8px 14px;border-left:3px solid #6366f1"><div style="font-weight:bold;font-size:13px;color:#1f2937;margin-bottom:5px">${esc(s.title)}</div><div style="font-size:12px;line-height:1.8;color:#374151">${bodyHtml}</div></div>`
          : `<div style="margin-bottom:14px;font-size:12px;line-height:1.8;color:#374151">${bodyHtml}</div>`;
      });

      if (sectionParts.length > 0) {
        const generatedDate = new Date(insight.generated_at).toLocaleDateString("en-GB", {
          day: "2-digit",
          month: "short",
          year: "numeric",
        });
        const provider = esc(insight.provider_used || "AI");
        insightHtml = `<h2>Health Insights</h2>${sectionParts.join("")}<div style="font-size:10px;color:#9ca3af;margin-top:10px;padding-top:8px;border-top:1px solid #e5e7eb;font-style:italic">Generated ${generatedDate} by ${provider} — for informational purposes only, not medical advice.</div>`;
      }
    }

    const html = `<!DOCTYPE html><html><head><title>${esc(mn)} — Health Profile</title>
<style>
  @page { margin: 0.75in 1in; }
  * { margin: 0; box-sizing: border-box; }
  body { font-family: Arial, Helvetica, sans-serif; color: #1f2937; line-height: 1.7; font-size: 13px; text-align: justify; }
  table { width: 100%; border-collapse: collapse; text-align: left; }
  th, td { font-size: 11px; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: #6366f1; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; margin: 20px 0 10px; }
  .header-bar { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 3px solid #1f2937; padding-bottom: 10px; margin-bottom: 16px; }
  .header-bar h1 { font-size: 20px; font-weight: bold; color: #111827; margin: 0; }
  .header-bar .meta { font-size: 10px; color: #9ca3af; text-align: right; line-height: 1.6; }
  .profile-grid { display: grid; grid-template-columns: 130px 1fr; gap: 4px 16px; font-size: 13px; margin-bottom: 4px; }
  .profile-label { font-weight: 600; color: #6b7280; }
  .profile-value { color: #1f2937; }
  .score-badge { display: inline-block; padding: 3px 14px; border-radius: 12px; font-weight: bold; font-size: 13px; color: white; }
</style></head>
<body>
<div class="header-bar">
  <div>
    <h1>${esc(mn)}</h1>
    <div style="font-size:12px;color:#6b7280;margin-top:2px">Health Profile</div>
  </div>
  <div class="meta">
    Exported ${now}, ${time}<br>Family Health Manager
  </div>
</div>

<div class="profile-grid">
  <span class="profile-label">Name</span><span class="profile-value">${esc(mn)}</span>
  <span class="profile-label">Age / Gender</span><span class="profile-value">${age}y &middot; ${GENDER_LABELS[member.gender]}</span>
  ${member.blood_group ? `<span class="profile-label">Blood Group</span><span class="profile-value" style="color:#dc2626;font-weight:bold">${esc(member.blood_group)}</span>` : ""}
</div>

${histParts.length > 0 ? `<h2>Medical History</h2><div style="line-height:1.8;margin-bottom:6px">${histParts.join("<br>")}</div>` : ""}
${member.family_history ? `<div style="margin-top:8px"><b>Family History:</b> ${esc(member.family_history)}</div>` : ""}
${insightHtml}
<h2>Medications (${meds.length})</h2>
<table><thead><tr><th style="${th}">TYPE</th><th style="${th}">MEDICINE</th><th style="${th}">DOSE</th><th style="${th}">WHEN</th><th style="${th}">DR.</th><th style="${th}">DATE</th></tr></thead><tbody>${medRows}</tbody></table>
<div style="margin-top:24px;padding-top:8px;border-top:1px solid #d1d5db;display:flex;justify-content:space-between;font-size:10px;color:#9ca3af">
  <span>Family Health Manager</span>
  <span>Page 1</span>
</div>
</body></html>`;

    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(html);
    win.document.close();
    setTimeout(() => win.print(), 200);
  }

  function handlePreConsultPDF() {
    if (!preConsultNote) return;
    const esc = (s: string) =>
      s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const mn = `${member.first_name} ${member.last_name}`;
    const now = new Date().toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
    const dateStr = new Date(preConsultNote.generated_at).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
    const sections = parseSections(preConsultNote.response);
    const sectionHtml = sections
      .map(
        (s) =>
          `<div style="margin-bottom:14px;padding-left:12px;border-left:3px solid #14B8A6"><div style="font-weight:bold;font-size:11px;margin-bottom:4px;color:#0f766e">${esc(s.title)}</div><div style="font-size:10px;line-height:1.7;color:#374151">${esc(
            s.body
          )
            .replace(/\[ \]/g, "☐")
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/\*([^*]+)\*/g, "<em>$1</em>")
            .replace(/\n/g, "<br>")}</div></div>`
      )
      .join("");
    const html = `<!DOCTYPE html><html><head><title>Pre-Consultation Note — ${esc(mn)}</title>
<style>@page { margin: 0.75in 1in; } * { margin: 0; box-sizing: border-box; } body { font-family: Arial, Helvetica, sans-serif; color: #1f2937; font-size: 11px; }</style></head>
<body>
<div style="text-align:center;margin-bottom:16px;border-bottom:2px solid #14B8A6;padding-bottom:12px"><div style="font-size:14px;font-weight:bold">${esc(mn)} — Pre-Consultation Note</div><div style="font-size:10px;color:#6b7280;margin-top:4px">${dateStr} &middot; via ${esc(preConsultNote.provider_used)}</div><div style="font-size:9px;color:#9ca3af;margin-top:2px">Exported ${now}</div></div>
${sectionHtml}
<div style="margin-top:16px;padding-top:6px;border-top:1px solid #d1d5db;font-size:9px;color:#9ca3af">AI-generated for informational purposes only. Review with your healthcare provider.</div>
</body></html>`;
    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(html);
    win.document.close();
    setTimeout(() => win.print(), 200);
  }

  function handleInsightReady(result: GeneratedInsight) {
    setInsight(result);
    setShowReport(true);
  }

  const memberName = `${member.first_name} ${member.last_name}`;
  const hasAllergies = member.allergies && member.allergies.length > 0;
  const hasEmergency = member.emergency_contact_name || member.emergency_contact_phone;

  // Computed data
  const recordTypeDist = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of memberRecords) {
      const type = r.record_type || "unknown";
      counts[type] = (counts[type] || 0) + 1;
    }
    return Object.entries(counts).sort(([, a], [, b]) => b - a);
  }, [memberRecords]);

  const activityHeatmap = useMemo(() => {
    const now = new Date();
    const cells: { date: string; count: number; dayLabel: string }[] = [];
    for (let i = 83; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const dateStr = d.toISOString().slice(0, 10);
      const dayLabel = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
      const count = memberRecords.filter(
        (r) => r.record_date === dateStr || r.created_at.slice(0, 10) === dateStr
      ).length;
      cells.push({ date: dateStr, count, dayLabel });
    }
    return cells;
  }, [memberRecords]);

  const lastRecordDate = useMemo(() => {
    if (memberRecords.length === 0) return null;
    const sorted = [...memberRecords].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
    return sorted[0].record_date || sorted[0].created_at.slice(0, 10);
  }, [memberRecords]);

  const recordsThisMonth = useMemo(() => {
    const now = new Date();
    const thisMonth = now.getFullYear() * 12 + now.getMonth();
    return memberRecords.filter(
      (r) =>
        new Date(r.created_at).getFullYear() * 12 + new Date(r.created_at).getMonth() === thisMonth
    ).length;
  }, [memberRecords]);

  // Parse medical history for compact display
  const medHistoryTags = useMemo(() => {
    if (!brief_medical_history)
      return { conditions: [] as string[], allergies: [] as string[], surgeries: [] as string[] };
    const parts = brief_medical_history.split("; ").reduce((acc: Record<string, string>, part) => {
      const idx = part.indexOf(":");
      if (idx > 0) acc[part.slice(0, idx).trim()] = part.slice(idx + 1).trim();
      return acc;
    }, {});
    return {
      conditions: (parts["Conditions"] || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      allergies: (parts["Allergies"] || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      surgeries: (parts["Surgeries"] || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
  }, [brief_medical_history]);

  // Score breakdown compact bars
  const scoreBreakdown = dashboard.score_breakdown || {};
  const hasBreakdown = Object.keys(scoreBreakdown).length > 0;

  // Risk config
  const riskLevel = riskAssessment?.risk_level;
  const riskDot =
    riskLevel === "high"
      ? "bg-red-500"
      : riskLevel === "moderate"
        ? "bg-amber-500"
        : riskLevel === "low"
          ? "bg-emerald-500"
          : null;

  // Early returns — AFTER all hooks
  if (showPreConsult && preConsultNote) {
    return (
      <PreConsultationNoteViewer
        response={preConsultNote.response}
        provider={preConsultNote.provider_used}
        generatedAt={preConsultNote.generated_at}
        verification={preConsultNote.verification}
        memberName={`${member.first_name} ${member.last_name}`}
        onBack={() => setShowPreConsult(false)}
        onExportPDF={handlePreConsultPDF}
      />
    );
  }

  if (showReport && insight) {
    return (
      <Suspense
        fallback={
          <div className="flex items-center justify-center py-12">
            <p className="text-muted-foreground">Loading report...</p>
          </div>
        }
      >
        <InsightReport
          response={insight.response}
          provider={insight.provider_used}
          generatedAt={insight.generated_at}
          verification={insight.verification}
          memberName={`${member.first_name} ${member.last_name}`}
          memberDob={formatDate(member.date_of_birth)}
          memberGender={GENDER_LABELS[member.gender]}
          onBack={() => setShowReport(false)}
        />
      </Suspense>
    );
  }

  return (
    <div className="space-y-3 max-w-[1400px] mx-auto">
      {/* Print header */}
      <div className="hidden print:block mb-6 pb-4 border-b-2 border-gray-900">
        <h1 className="text-xl font-bold">{memberName} — Health Profile</h1>
        <p className="text-xs text-gray-500 mt-1">
          Generated {new Date().toLocaleDateString()} · Health Score: {health_score}/100
        </p>
      </div>

      {/* ═══ HERO: Profile Card ═══ */}
      <Card className="shadow-none">
        <CardContent className="p-4 sm:p-5">
          {/* Row 1: Breadcrumb + actions */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Link to="/members" className="hover:text-primary transition-colors">
                Members
              </Link>
              <span className="text-muted-foreground/30">/</span>
              <span className="text-foreground font-medium">{memberName}</span>
            </div>
            <div className="flex items-center gap-1.5 print:hidden">
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportPDF}
                className="gap-1 h-7 text-xs rounded-lg px-2.5"
              >
                <Printer className="h-3 w-3" />
                PDF
              </Button>
              <Link to={`/members/${member.id}/edit`}>
                <Button variant="outline" size="sm" className="h-7 text-xs rounded-lg px-2.5">
                  Edit
                </Button>
              </Link>
            </div>
          </div>

          {/* Row 2: Two-column — Identity | Score */}
          <div className="flex items-center gap-5 mb-4">
            {/* Left: Avatar + Identity */}
            <div className="flex items-center gap-3.5 flex-1 min-w-0">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary font-bold text-xl shrink-0">
                {member.first_name[0]}
                {member.last_name[0]}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h1 className="text-xl font-bold tracking-tight truncate">{memberName}</h1>
                  {riskDot && (
                    <Badge
                      className={`text-[10px] font-bold px-2 py-0.5 ${riskLevel === "high" ? "bg-red-100 text-red-700 border border-red-200" : riskLevel === "moderate" ? "bg-amber-100 text-amber-700 border border-amber-200" : "bg-emerald-100 text-emerald-700 border border-emerald-200"}`}
                    >
                      <span className={`inline-block h-1.5 w-1.5 rounded-full mr-1 ${riskDot}`} />
                      {riskLevel === "high"
                        ? "High"
                        : riskLevel === "moderate"
                          ? "Moderate"
                          : "Low"}{" "}
                      Risk
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                    {RELATIONSHIP_LABELS[member.relationship]}
                  </Badge>
                  <span>
                    {age}y · {GENDER_LABELS[member.gender]}
                  </span>
                  {member.blood_group && (
                    <span className="font-semibold text-red-600">{member.blood_group}</span>
                  )}
                </div>
                {/* Compact medical history */}
                {medHistoryTags.conditions.length > 0 && (
                  <p className="text-[11px] text-muted-foreground mt-1 truncate">
                    {medHistoryTags.conditions.join(", ")}
                  </p>
                )}
              </div>
            </div>

            {/* Right: Health Score */}
            <button
              onClick={() => setShowScoreDetail(!showScoreDetail)}
              className="shrink-0 cursor-pointer flex flex-col items-center gap-1 p-2 rounded-xl hover:bg-muted/50 transition-colors"
              title="Click to toggle score breakdown"
            >
              <HealthScoreRing score={health_score} size={68} strokeWidth={4.5} />
              <span className={`text-xs font-bold ${scoreTextColor(health_score)}`}>
                {health_score >= 75 ? "Excellent" : health_score >= 50 ? "Good" : "Needs Attention"}
              </span>
            </button>
          </div>

          {/* Row 3: Key metrics grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
            <div className="rounded-lg bg-muted/40 px-3 py-2">
              <p className="text-lg font-bold">{memberRecords.length}</p>
              <p className="text-[10px] text-muted-foreground">Records</p>
            </div>
            <div className="rounded-lg bg-muted/40 px-3 py-2">
              <p className="text-lg font-bold">{active_medications_count}</p>
              <p className="text-[10px] text-muted-foreground">Medications</p>
            </div>
            {active_conditions_count > 0 && (
              <div className="rounded-lg bg-muted/40 px-3 py-2">
                <p className="text-lg font-bold">{active_conditions_count}</p>
                <p className="text-[10px] text-muted-foreground">Conditions</p>
              </div>
            )}
            {provider_assignments && provider_assignments.length > 0 && (
              <div className="rounded-lg bg-muted/40 px-3 py-2">
                <p className="text-lg font-bold">{provider_assignments.length}</p>
                <p className="text-[10px] text-muted-foreground">Providers</p>
              </div>
            )}
            {drugInteractions.length > 0 && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2">
                <p className="text-lg font-bold text-red-700">{drugInteractions.length}</p>
                <p className="text-[10px] text-red-600">Interactions</p>
              </div>
            )}
            {recordsThisMonth > 0 && (
              <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2">
                <p className="text-lg font-bold text-emerald-700">{recordsThisMonth}</p>
                <p className="text-[10px] text-emerald-600">This Month</p>
              </div>
            )}
            {hasAllergies && (
              <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2">
                <p className="text-lg font-bold text-amber-700">{member.allergies!.length}</p>
                <p className="text-[10px] text-amber-600">
                  Allerg{member.allergies!.length !== 1 ? "ies" : "y"}
                </p>
              </div>
            )}
            {lastRecordDate && (
              <div className="rounded-lg bg-muted/40 px-3 py-2">
                <p className="text-xs font-bold">{formatDate(lastRecordDate)}</p>
                <p className="text-[10px] text-muted-foreground">Last Record</p>
              </div>
            )}
          </div>

          {/* Allergies + Surgeries row (compact) */}
          {(medHistoryTags.allergies.length > 0 ||
            medHistoryTags.surgeries.length > 0 ||
            hasEmergency) && (
            <div className="flex items-center gap-3 mt-3 flex-wrap text-xs text-muted-foreground">
              {medHistoryTags.allergies.length > 0 && (
                <span>
                  <span className="font-semibold text-amber-600">Allergies: </span>
                  {medHistoryTags.allergies.join(", ")}
                </span>
              )}
              {medHistoryTags.surgeries.length > 0 && (
                <span>
                  <span className="font-semibold text-purple-600">Surgeries: </span>
                  {medHistoryTags.surgeries.join(", ")}
                </span>
              )}
              {hasEmergency && (
                <span>
                  <Phone className="h-3 w-3 inline mr-1" />
                  {member.emergency_contact_name}
                  {member.emergency_contact_phone && (
                    <span className="ml-1 opacity-60">{member.emergency_contact_phone}</span>
                  )}
                </span>
              )}
            </div>
          )}

          {/* Risk factors */}
          {riskAssessment && riskAssessment.factors.length > 0 && (
            <div className="flex items-center gap-1.5 mt-2 flex-wrap">
              {riskAssessment.factors.slice(0, 4).map((f, i) => (
                <Badge
                  key={i}
                  variant="outline"
                  className={`text-[10px] font-semibold px-1.5 py-0 ${f.severity === "high" ? "text-red-600 border-red-200 bg-red-50" : f.severity === "moderate" ? "text-amber-600 border-amber-200 bg-amber-50" : "text-blue-600 border-blue-200 bg-blue-50"}`}
                >
                  {f.factor}
                </Badge>
              ))}
            </div>
          )}

          {/* Expanded score breakdown (toggle) */}
          {showScoreDetail && hasBreakdown && (
            <div className="mt-3 pt-3 border-t">
              <ScoreBreakdownExpanded breakdown={scoreBreakdown} />
            </div>
          )}
        </CardContent>
      </Card>

      {/* ═══ VITALS: Compact stat cards row ═══ */}
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2">
        {member.bmi && (
          <Card className="shadow-none">
            <CardContent className="pt-3 pb-2 text-center">
              <p className="text-lg font-bold tracking-tight">{member.bmi.toFixed(1)}</p>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                BMI
              </p>
              {member.bmi_category && (
                <p className="text-[10px] font-medium mt-0.5 text-muted-foreground">
                  {member.bmi_category}
                </p>
              )}
            </CardContent>
          </Card>
        )}
        {hba1cHistory.length > 0 &&
          (() => {
            const latest = hba1cHistory[hba1cHistory.length - 1].hba1c_value;
            const cat = getHba1cCategory(latest);
            return (
              <Card className="shadow-none">
                <CardContent className="pt-3 pb-2 text-center">
                  <p className="text-lg font-bold tracking-tight">{latest}%</p>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    HbA1c
                  </p>
                  <p className="text-[10px] font-medium mt-0.5 text-muted-foreground">{cat}</p>
                </CardContent>
              </Card>
            );
          })()}
        <Card className="shadow-none">
          <CardContent className="pt-3 pb-2 text-center">
            <p className="text-lg font-bold tracking-tight">{active_medications_count}</p>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Medications
            </p>
          </CardContent>
        </Card>
        {active_conditions_count > 0 && (
          <Card className="shadow-none">
            <CardContent className="pt-3 pb-2 text-center">
              <p className="text-lg font-bold tracking-tight">{active_conditions_count}</p>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Conditions
              </p>
            </CardContent>
          </Card>
        )}
        {hasAllergies &&
          member.allergies!.map((a, i) => (
            <Card key={i} className="shadow-none">
              <CardContent className="pt-3 pb-2 text-center">
                <p className="text-xs font-bold truncate">{a.name}</p>
                <p className="text-[10px] font-medium mt-0.5 text-muted-foreground capitalize">
                  {a.severity}
                </p>
              </CardContent>
            </Card>
          ))}
        {hasEmergency && (
          <Card className="shadow-none">
            <CardContent className="pt-3 pb-2 text-center">
              <Phone className="h-3 w-3 mx-auto mb-1 text-muted-foreground" />
              <p className="text-[11px] font-bold truncate">{member.emergency_contact_name}</p>
              {member.emergency_contact_phone && (
                <p className="text-[10px] text-muted-foreground truncate">
                  {member.emergency_contact_phone}
                </p>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* ═══ QUICK ACTIONS ═══ */}
      <div className="flex items-center gap-1 print:hidden">
        {quickActions.map((action) => {
          const Icon = action.icon;
          return (
            <Link
              key={action.hrefSuffix}
              to={`/members/${member.id}${action.hrefSuffix}`}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${action.color}`}
            >
              <Icon className="h-3.5 w-3.5" />
              {action.label}
            </Link>
          );
        })}
      </div>

      {/* ═══ CHARTS ROW: HbA1c + Reminders ═══ */}
      {(memberReminders.length > 0 || hba1cHistory.length >= 1) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {hba1cHistory.length >= 1 && (
            <Card className="shadow-none">
              <CardContent className="pt-4 pb-3">
                <div className="text-sm font-semibold mb-3">HbA1c Trend</div>
                <ExpandedHba1cChart data={hba1cHistory} />
              </CardContent>
            </Card>
          )}
          {memberReminders.length > 0 && (
            <Card className="shadow-none">
              <CardContent className="pt-4 pb-3 space-y-2.5">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <Bell className="h-4 w-4 text-blue-500" />
                  Upcoming Reminders
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                    {memberReminders.length}
                  </Badge>
                </div>
                <div className="space-y-1.5">
                  {memberReminders.map((rem) => (
                    <div
                      key={rem.id}
                      className="flex items-center justify-between rounded-lg bg-muted/30 px-3 py-2"
                    >
                      <div className="min-w-0">
                        <p className="text-xs font-semibold truncate">{rem.title}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {formatRelativeTime(rem.start_datetime)}
                        </p>
                      </div>
                      <Badge variant="outline" className="text-[10px] shrink-0 ml-2">
                        {rem.reminder_type}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ═══ MEDICATIONS ═══ */}
      <ActiveMedicationsTable memberId={member.id} medications={active_medications ?? []} />

      {/* ═══ CHRONIC CONDITIONS ═══ */}
      <ChronicConditionCharts memberId={member.id} />

      {/* ═══ RECORDS + ACTIVITY ═══ */}
      <div className="grid gap-3 md:grid-cols-2">
        <Card className="shadow-none">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-semibold flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-blue-500" />
                Records by Type
              </div>
              <span className="text-[10px] text-muted-foreground">
                {memberRecords.length} total
              </span>
            </div>
            {recordTypeDist.length > 0 ? (
              <div className="space-y-2">
                {recordTypeDist.map(([type, count]) => {
                  const pct =
                    memberRecords.length > 0 ? Math.round((count / memberRecords.length) * 100) : 0;
                  return (
                    <div key={type} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium">
                          {(RECORD_TYPE_LABELS as Record<string, string>)[type] || type}
                        </span>
                        <span className="text-muted-foreground tabular-nums">
                          {count} ({pct}%)
                        </span>
                      </div>
                      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${TYPE_COLORS[type] || "bg-gray-400"}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="flex items-center gap-2 py-4 text-muted-foreground">
                <FileText className="h-4 w-4" />
                <span className="text-xs">No records yet</span>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-semibold flex items-center gap-2">
                <CalendarDays className="h-4 w-4 text-violet-500" />
                Activity (12 weeks)
              </div>
              <span className="text-[10px] text-muted-foreground">
                {memberRecords.length} records
              </span>
            </div>
            <div className="flex items-center gap-[3px] flex-wrap">
              {activityHeatmap.map((cell) => (
                <ActivityCell key={cell.date} count={cell.count} label={cell.dayLabel} />
              ))}
            </div>
            <div className="flex items-center justify-between mt-2 text-[10px] text-muted-foreground">
              <span>Less</span>
              <div className="flex items-center gap-1">
                <div className="h-2.5 w-2.5 rounded-sm bg-primary/10" />
                <div className="h-2.5 w-2.5 rounded-sm bg-primary/25" />
                <div className="h-2.5 w-2.5 rounded-sm bg-primary/50" />
                <div className="h-2.5 w-2.5 rounded-sm bg-primary/75" />
                <div className="h-2.5 w-2.5 rounded-sm bg-primary" />
              </div>
              <span>More</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ═══ AI CARDS ═══ */}
      <div className="grid gap-3 md:grid-cols-2">
        <PreConsultationCard
          memberId={member.id}
          memberFirstName={member.first_name}
          existingNote={preConsultNote}
          onNoteReady={setPreConsultNote}
          onViewNote={() => setShowPreConsult(true)}
        />
        <InsightCard
          memberId={member.id}
          memberFirstName={member.first_name}
          existingInsight={insight}
          onInsightReady={handleInsightReady}
          onViewReport={() => setShowReport(true)}
        />
      </div>

      {/* ═══ CARE CARDS ═══ */}
      <div className="grid gap-3 md:grid-cols-2 print:hidden">
        <DrugInteractionReport
          memberId={member.id}
          medicationCount={active_medications?.length ?? 0}
        />
        <ProvidersUhidCard memberId={member.id} assignments={provider_assignments} />
        <PreventiveCareTable memberId={member.id} />
        <VaccinationsSection memberId={member.id} />
      </div>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Family Member"
        description="Are you sure you want to delete this family member? Their health records will also be removed."
        onConfirm={handleDelete}
      />
    </div>
  );
}
