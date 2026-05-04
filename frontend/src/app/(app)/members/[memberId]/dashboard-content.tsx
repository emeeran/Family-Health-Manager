import React, { useState, useEffect, lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  BMI_CATEGORY_COLORS,
  HBA1C_CATEGORY_COLORS,
} from "@/lib/constants";
import {
  deleteMember,
  getBmiHistory,
  getHba1cHistory,
  getPreventiveRecommendations,
  createPreventiveReminder,
  getLatestDrugInteractions,
  getLatestPreConsultationNote,
  getLatestInsight,
} from "@/lib/api/members";
import { listReminders } from "@/lib/api/reminders";
import { getRiskAssessment } from "@/lib/api/dashboard";
import { formatDate } from "@/lib/utils";
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
} from "lucide-react";
import type {
  MemberDashboardResponse,
  BmiHistoryEntry,
  Hba1cHistoryEntry,
  PreventiveRecommendation,
} from "@/lib/types/member";
import type { GeneratedInsight } from "@/lib/api/members";
import type { DrugInteraction } from "@/lib/types/member";
import type { ReminderResponse } from "@/lib/types/reminder";

/* ── Lazy-loaded recharts (~200KB saved from initial chunk) ── */

// Lazy wrapper components that dynamically import recharts only when charts render
const LazyBmiChart = lazy(() =>
  import("recharts").then((mod) => ({
    default: ({
      data,
      minBmi,
      maxBmi,
    }: {
      data: { date: string; bmi: number }[];
      minBmi: number;
      maxBmi: number;
    }) => (
      <mod.ResponsiveContainer width="100%" height={180}>
        <mod.LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
          <mod.CartesianGrid strokeDasharray="3 3" className="opacity-30" />
          <mod.XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <mod.YAxis domain={[minBmi, maxBmi]} tick={{ fontSize: 11 }} />
          <mod.Tooltip contentStyle={{ fontSize: 12 }} />
          <mod.Line
            type="monotone"
            dataKey="bmi"
            stroke="var(--chart-1)"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        </mod.LineChart>
      </mod.ResponsiveContainer>
    ),
  }))
);

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

/* ── Chart loading fallback ── */

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

function _scoreTextColor(score: number): string {
  if (score >= 75) return "text-green-600 dark:text-green-400";
  if (score >= 50) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = d.getTime() - now.getTime();
  const absDays = Math.abs(Math.round(diffMs / (1000 * 60 * 60 * 24)));
  if (absDays === 0) return "Today";
  if (diffMs < 0) {
    if (absDays === 1) return "Yesterday";
    return `${absDays}d ago`;
  }
  if (absDays === 1) return "Tomorrow";
  return `In ${absDays} days`;
}

/* ── Health Score Ring (small inline version) ── */

function HealthScoreRing({
  score,
  size = 44,
  strokeWidth = 3,
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
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="font-bold text-sm" style={{ color }}>
          {score}
        </span>
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

/* ── Expanded BMI Chart ── */

function _ExpandedBmiChart({
  data,
  currentBmi,
}: {
  data: BmiHistoryEntry[];
  currentBmi: number | null;
}) {
  const chartData = data.map((d) => ({ date: d.date.slice(0, 10), bmi: d.bmi }));
  const first = data[0].bmi;
  const last = data[data.length - 1].bmi;
  const bmis = data.map((d) => d.bmi);
  const minBmi = Math.floor(Math.min(...bmis) - 1);
  const maxBmi = Math.ceil(Math.max(...bmis) + 1);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-semibold text-foreground/70">BMI Trend</p>
        <div className="flex items-center gap-3">
          <span className="text-sm text-foreground/70">
            {first} → <span className="font-bold">{last}</span>
            {currentBmi && <span className="ml-1">(now: {currentBmi})</span>}
          </span>
          <TrendBadge first={first} latest={last} lowerIsBetter={false} />
        </div>
      </div>
      <Suspense fallback={<ChartFallback />}>
        <LazyBmiChart data={chartData} minBmi={minBmi} maxBmi={maxBmi} />
      </Suspense>
    </div>
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

  // Single data point — show value prominently, no chart yet
  if (data.length === 1) {
    return (
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-semibold text-foreground/70">HbA1c</p>
          <div className="flex items-center gap-3">
            <span className="text-lg font-bold">{last}%</span>
            <Badge
              variant="secondary"
              className={`text-xs px-2 py-0.5 font-semibold ${HBA1C_CATEGORY_COLORS[category] ?? ""}`}
            >
              {category}
            </Badge>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">Add more readings to see trends over time.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-semibold text-foreground/70">HbA1c Trend</p>
        <div className="flex items-center gap-3">
          <span className="text-sm text-foreground/70">
            {first}% → <span className="font-bold">{last}%</span>
          </span>
          <Badge
            variant="secondary"
            className={`text-xs px-2 py-0.5 font-semibold ${HBA1C_CATEGORY_COLORS[category] ?? ""}`}
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
const CATEGORY_ICON: Record<string, string> = {
  vaccination: "💉",
  screening: "🔍",
  lab: "🧪",
  "follow-up": "📅",
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
      <Card className="flex flex-col">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-blue-500" />
            Preventive Care
          </CardTitle>
        </CardHeader>
        <CardContent className="flex-1">
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 bg-muted animate-pulse rounded" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (recommendations.length === 0) return null;

  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-blue-500" />
          Preventive Care
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0 ml-auto">
            {recommendations.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0 flex-1">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="py-2.5 px-4 font-medium">Priority</th>
                <th className="py-2.5 px-4 font-medium">Recommendation</th>
                <th className="py-2.5 px-4 font-medium hidden sm:table-cell">Details</th>
                <th className="py-2.5 px-4 font-medium hidden md:table-cell">Frequency</th>
                <th className="py-2.5 px-4 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {recommendations.map((rec, i) => (
                <tr
                  key={i}
                  className="border-b last:border-b-0 hover:bg-muted/50 transition-colors"
                >
                  <td className="py-2.5 px-4">
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        className={`inline-block h-2 w-2 rounded-full ${PRIORITY_DOT[rec.priority] || PRIORITY_DOT.low}`}
                      />
                      <span className="text-xs font-medium capitalize">
                        {PRIORITY_LABEL[rec.priority] || rec.priority}
                      </span>
                    </span>
                  </td>
                  <td className="py-2.5 px-4">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="text-xs">{CATEGORY_ICON[rec.category] || "📋"}</span>
                      <span className="font-medium">{rec.title}</span>
                    </span>
                  </td>
                  <td className="py-2.5 px-4 text-xs text-muted-foreground hidden sm:table-cell">
                    {rec.description}
                  </td>
                  <td className="py-2.5 px-4 text-xs text-muted-foreground hidden md:table-cell">
                    {rec.due_interval_months === 0
                      ? "One-time"
                      : rec.due_interval_months >= 12
                        ? `Every ${rec.due_interval_months / 12}y`
                        : `Every ${rec.due_interval_months}mo`}
                  </td>
                  <td className="py-2.5 px-4 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs"
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

/* ── Score Breakdown ── */

function ScoreBreakdown({
  breakdown,
}: {
  breakdown: Record<string, { score: number; max: number; label: string }>;
}) {
  return (
    <div className="space-y-2 mt-3">
      {Object.entries(breakdown).map(([key, val]) => {
        const pct = Math.round((val.score / val.max) * 100);
        const color = pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500";
        return (
          <div key={key} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="capitalize text-muted-foreground">{key.replace(/_/g, " ")}</span>
              <span className="font-medium">
                {val.score}/{val.max}
              </span>
            </div>
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── Quick Actions Config ── */

const quickActions = [
  {
    label: "Add Record",
    icon: Plus,
    hrefSuffix: "/records/new",
    color: "bg-blue-500/15 text-blue-600 hover:bg-blue-100 border-blue-200",
  },
  {
    label: "All Records",
    icon: FileText,
    hrefSuffix: "/records",
    color: "bg-teal-500/15 text-teal-600 hover:bg-teal-100 border-teal-200",
  },
  {
    label: "Timeline",
    icon: Activity,
    hrefSuffix: "/timeline",
    color: "bg-amber-500/15 text-amber-600 hover:bg-amber-100 border-amber-200",
  },
  {
    label: "Lab Records",
    icon: FlaskConical,
    hrefSuffix: "/lab-records",
    color: "bg-emerald-500/15 text-emerald-600 hover:bg-emerald-100 border-emerald-200",
  },
  {
    label: "Providers",
    icon: Users,
    hrefSuffix: "/providers",
    color: "bg-violet-500/15 text-violet-600 hover:bg-violet-100 border-violet-200",
  },
  {
    label: "Ask AI",
    icon: Sparkles,
    hrefSuffix: "/ai",
    color: "bg-rose-500/15 text-rose-600 hover:bg-rose-100 border-rose-200",
  },
];

const ALLERGY_SEVERITY_COLORS: Record<string, string> = {
  mild: "bg-green-100 text-green-800 border-green-300",
  moderate: "bg-amber-100 text-amber-800 border-amber-300",
  severe: "bg-red-100 text-red-800 border-red-300",
};

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
  const [showScoreBreakdown, setShowScoreBreakdown] = useState(false);
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

  const [_bmiHistory, setBmiHistory] = useState<BmiHistoryEntry[]>([]);
  const [hba1cHistory, setHba1cHistory] = useState<Hba1cHistoryEntry[]>([]);
  const [memberReminders, setMemberReminders] = useState<ReminderResponse[]>([]);
  const [drugInteractions, setDrugInteractions] = useState<DrugInteraction[]>([]);
  const [riskAssessment, setRiskAssessment] = useState<{
    risk_level: string;
    factors: { factor: string; severity: string; description: string }[];
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getBmiHistory(member.id),
      getRiskAssessment(member.id).catch(() => null),
      getHba1cHistory(member.id),
      listReminders().catch(() => []),
      getLatestDrugInteractions(member.id).catch(() => ({ interactions: [] })),
      getLatestPreConsultationNote(member.id).catch(() => ({ note: null })),
      getLatestInsight(member.id).catch(() => null),
    ])
      .then(([bmi, risk, hba1c, reminders, drugResult, preConsultResult, insightResult]) => {
        if (cancelled) return;
        setBmiHistory(bmi);
        if (risk) setRiskAssessment(risk);
        setHba1cHistory(hba1c);
        if (drugResult?.interactions) setDrugInteractions(drugResult.interactions);
        if (preConsultResult?.note) setPreConsultNote(preConsultResult.note);
        if (insightResult) setInsight(insightResult);
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
    const fmtMd = (s: string) => s.replace(/\*\*/g, "").replace(/\*/g, "");
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

    // ── Medical history parsed ──
    const histParts: string[] = [];
    if (brief_medical_history) {
      const sections = brief_medical_history
        .split(";")
        .map((s: string) => s.trim())
        .filter(Boolean);
      for (const sec of sections) {
        histParts.push(esc(sec));
      }
    }

    // ── Medications table ──
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

    // ── Drug interactions table ──
    const diRows =
      drugInteractions.length > 0
        ? drugInteractions
            .map((di) => {
              const riskColors: Record<string, string> = {
                high: "#DC2626",
                moderate: "#FFA500",
                low: "#87CEFA",
              };
              const riskLabels: Record<string, string> = {
                high: "HIGH",
                moderate: "MODERATE",
                low: "LOW",
              };
              const bg = riskColors[di.severity] || riskColors.moderate;
              const label = riskLabels[di.severity] || "MODERATE";
              return `<tr><td style="${tc};font-weight:600">${esc(di.drugs.join(" + "))}</td><td style="${tc}"><span style="display:inline-block;padding:1px 8px;border-radius:3px;background:${bg};color:white;font-size:9px;font-weight:bold;letter-spacing:0.04em">${label}</span></td><td style="${tc}">${esc(di.description)}</td><td style="${tc}">${esc(di.recommendation)}</td></tr>`;
            })
            .join("")
        : `<tr><td colspan="4" style="${tc};text-align:center;color:#999">No interactions found</td></tr>`;

    // ── AI insights ──
    let insightContent = "";
    if (insight) {
      const lines = fmtMd(insight.response)
        .split("\n")
        .filter((l: string) => l.trim());
      const numbered = lines
        .map((l: string, i: number) => `${i + 1}. ${esc(l.replace(/^\d+\.\s*/, ""))}`)
        .join("<br>");
      insightContent = numbered;
    }

    const html = `<!DOCTYPE html><html><head><title>${esc(mn)} — Health Profile</title>
<style>
  @page { margin: 1in 1.2in; }
  * { margin: 0; box-sizing: border-box; }
  body { font-family: Arial, Helvetica, sans-serif; color: #1f2937; line-height: 1.5; font-size: 11px; }
  table { width: 100%; border-collapse: collapse; }
  h2 { font-size: 12px; text-decoration: underline; margin: 14px 0 6px; }
</style></head>
<body>

<!-- Header -->
<div style="font-size:10px;color:#6b7280;margin-bottom:4px">${now}, ${time}</div>
<div style="text-align:center;margin-bottom:12px">
  <div style="font-size:14px;font-weight:bold">${esc(mn)} — Health Profile</div>
</div>

<!-- Patient info -->
<div style="margin-bottom:10px">
  <div style="font-size:14px;font-weight:bold">${esc(mn)}</div>
  <div style="font-size:12px;color:#4b5563">${age}y &bull; ${GENDER_LABELS[member.gender]}${member.blood_group ? ` &bull; Blood: ${esc(member.blood_group)}` : ""} &bull; Score: ${health_score}/100</div>
  <div style="font-size:10px;font-style:italic;color:#9ca3af">Exported ${now}</div>
</div>

${
  histParts.length > 0
    ? `
<!-- Medical History -->
<h2>Medical History</h2>
<div style="font-size:11px;line-height:1.5;margin-bottom:8px">
  ${histParts.map((h) => esc(h)).join("<br>")}
</div>
`
    : ""
}
${member.family_history ? `<div style="font-size:11px;margin-bottom:8px"><b>Family History:</b> ${esc(member.family_history)}</div>` : ""}

<!-- Medications Table -->
<h2>Medications (${meds.length})</h2>
<table>
  <thead><tr>
    <th style="${th}">TYPE</th>
    <th style="${th}">MEDICINE</th>
    <th style="${th}">DOSE</th>
    <th style="${th}">WHEN</th>
    <th style="${th}">DR.</th>
    <th style="${th}">DATE</th>
  </tr></thead>
  <tbody>${medRows}</tbody>
</table>

<!-- Drug Interactions Table -->
<h2>Drug Interactions${drugInteractions.length > 0 ? ` (${drugInteractions.length})` : ""}</h2>
<table>
  <thead><tr>
    <th style="${th}">DRUGS</th>
    <th style="${th}">RISK</th>
    <th style="${th}">DESCRIPTION</th>
    <th style="${th}">RECOMMENDATION</th>
  </tr></thead>
  <tbody>${diRows}</tbody>
</table>

${
  insight
    ? `
<!-- AI Health Insights -->
<h2>AI Health Insights</h2>
<div style="font-size:11px;line-height:1.5">${insightContent}</div>
`
    : ""
}

<!-- Footer -->
<div style="margin-top:20px;padding-top:6px;border-top:1px solid #d1d5db;display:flex;justify-content:space-between;font-size:9px;color:#9ca3af">
  <span>${insight ? `Generated ${new Date(insight.generated_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })} via ${esc(insight.provider_used)}` : ""}</span>
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
        (s) => `
      <div style="margin-bottom:14px;padding-left:12px;border-left:3px solid #14B8A6">
        <div style="font-weight:bold;font-size:11px;margin-bottom:4px;color:#0f766e">${esc(s.title)}</div>
        <div style="font-size:10px;line-height:1.7;color:#374151">
          ${esc(s.body)
            .replace(/\[ \]/g, "☐")
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/\*([^*]+)\*/g, "<em>$1</em>")
            .replace(/\n/g, "<br>")}
        </div>
      </div>`
      )
      .join("");
    const html = `<!DOCTYPE html><html><head><title>Pre-Consultation Note — ${esc(mn)}</title>
<style>
  @page { margin: 0.75in 1in; }
  * { margin: 0; box-sizing: border-box; }
  body { font-family: Arial, Helvetica, sans-serif; color: #1f2937; font-size: 11px; }
</style></head>
<body>
<div style="text-align:center;margin-bottom:16px;border-bottom:2px solid #14B8A6;padding-bottom:12px">
  <div style="font-size:14px;font-weight:bold">${esc(mn)} — Pre-Consultation Note</div>
  <div style="font-size:10px;color:#6b7280;margin-top:4px">${dateStr} &middot; via ${esc(preConsultNote.provider_used)}</div>
  <div style="font-size:9px;color:#9ca3af;margin-top:2px">Exported ${now}</div>
</div>
${sectionHtml}
<div style="margin-top:16px;padding-top:6px;border-top:1px solid #d1d5db;font-size:9px;color:#9ca3af">
  AI-generated for informational purposes only. Review with your healthcare provider.
</div>
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

  // Full-page pre-consultation note viewer
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

  // Full-page report
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

  const _hasHba1c = hba1cHistory.length >= 1; // used for HbA1c vitals badge
  const memberName = `${member.first_name} ${member.last_name}`;
  const hasAllergies = member.allergies && member.allergies.length > 0;
  const hasEmergency = member.emergency_contact_name || member.emergency_contact_phone;

  return (
    <div className="space-y-5 max-w-[1600px] mx-auto">
      {/* Print header */}
      <div className="hidden print:block mb-6 pb-4 border-b-2 border-gray-900">
        <h1 className="text-xl font-bold">{memberName} — Health Profile</h1>
        <p className="text-xs text-gray-500 mt-1">
          Generated {new Date().toLocaleDateString()} · Health Score: {health_score}/100
        </p>
      </div>

      {/* ── SECTION 1: Profile Header with Medical History ── */}
      <div className="rounded-2xl border bg-card shadow-sm overflow-hidden">
        <div className="h-1.5 bg-gradient-to-r from-(--brand-accent) to-(--brand-primary)" />
        <div className="px-6 py-5">
          {/* Top row: breadcrumb + actions */}
          <div className="flex items-center justify-between gap-4 flex-wrap mb-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Link to="/members" className="hover:text-primary transition-colors">
                Members
              </Link>
              <span className="text-muted-foreground/30">/</span>
              <span className="text-foreground font-medium">{memberName}</span>
            </div>
            <div className="flex items-center gap-3 print:hidden">
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExportPDF}
                  className="gap-1.5 h-9"
                >
                  <Printer className="h-4 w-4" />
                  PDF
                </Button>
                <Link to={`/members/${member.id}/edit`}>
                  <Button variant="outline" size="sm" className="h-9">
                    Edit
                  </Button>
                </Link>
              </div>
            </div>
          </div>

          {/* Main profile row */}
          <div className="flex items-start gap-5">
            {/* Avatar */}
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-(--brand-accent) to-(--brand-primary) text-white font-bold text-xl shadow-lg shrink-0">
              {member.first_name[0]}
              {member.last_name[0]}
            </div>
            {/* Info block */}
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl font-bold tracking-tight">{memberName}</h1>
              <div className="flex items-center gap-2.5 mt-2 flex-wrap">
                <Badge variant="secondary" className="text-[11px] font-semibold px-2.5 py-0.5">
                  {RELATIONSHIP_LABELS[member.relationship]}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {age}y · {GENDER_LABELS[member.gender]}
                </span>
                {member.blood_group && (
                  <Badge className="bg-red-50 text-red-700 border border-red-200 text-[11px] font-bold px-2.5 py-0.5">
                    {member.blood_group}
                  </Badge>
                )}
                {hasEmergency && (
                  <span className="text-sm text-muted-foreground flex items-center gap-1">
                    <Phone className="h-3.5 w-3.5" />
                    {member.emergency_contact_name}
                    {member.emergency_contact_phone && (
                      <span className="text-muted-foreground/70">
                        {member.emergency_contact_phone}
                      </span>
                    )}
                  </span>
                )}
              </div>

              {/* Medical history section */}
              {brief_medical_history &&
                (() => {
                  const parts = brief_medical_history
                    .split("; ")
                    .reduce((acc: Record<string, string>, part) => {
                      const idx = part.indexOf(":");
                      if (idx > 0) acc[part.slice(0, idx).trim()] = part.slice(idx + 1).trim();
                      return acc;
                    }, {});
                  const conditions = (parts["Conditions"] || "")
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean);
                  const surgeries = (parts["Surgeries"] || "")
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean);
                  const allergies = (parts["Allergies"] || "")
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean);
                  return (
                    <div className="mt-5 space-y-3">
                      {conditions.length > 0 && (
                        <div className="flex items-start gap-3">
                          <span className="text-xs font-bold text-blue-700 dark:text-blue-400 uppercase tracking-wide mt-1.5 shrink-0 w-24">
                            Conditions
                          </span>
                          <div className="flex flex-wrap gap-2">
                            {conditions.map((c, i) => (
                              <span
                                key={i}
                                className="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-semibold bg-blue-100 text-blue-800 border border-blue-300 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-700"
                              >
                                {c}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {allergies.length > 0 && (
                        <div className="flex items-start gap-3">
                          <span className="text-xs font-bold text-amber-700 dark:text-amber-400 uppercase tracking-wide mt-1.5 shrink-0 w-24">
                            Allergies
                          </span>
                          <div className="flex flex-wrap gap-2">
                            {allergies.map((a, i) => (
                              <span
                                key={i}
                                className="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-semibold bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-700"
                              >
                                {a}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {surgeries.length > 0 && (
                        <div className="flex items-start gap-3">
                          <span className="text-xs font-bold text-purple-700 dark:text-purple-400 uppercase tracking-wide mt-1.5 shrink-0 w-24">
                            Surgeries
                          </span>
                          <div className="flex flex-wrap gap-2">
                            {surgeries.map((s, i) => (
                              <span
                                key={i}
                                className="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-semibold bg-purple-50 text-purple-800 border border-purple-200 dark:bg-purple-900/40 dark:text-purple-300 dark:border-purple-700"
                              >
                                {s}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}
              {member.family_history && (
                <div className="mt-4 flex items-start gap-3">
                  <span className="text-xs font-bold text-emerald-700 dark:text-emerald-400 uppercase tracking-wide mt-1 shrink-0 w-24">
                    Family Hx
                  </span>
                  <p className="text-sm text-foreground leading-relaxed">{member.family_history}</p>
                </div>
              )}
            </div>
          </div>

          {/* Health Score + Risk — bottom of card */}
          <div className="mt-5 pt-4 border-t print:hidden">
            <div className="flex items-center justify-between gap-4">
              {/* Health Score with breakdown */}
              <div className="flex items-center gap-4 flex-1">
                <button
                  onClick={() => setShowScoreBreakdown(!showScoreBreakdown)}
                  className="flex items-center gap-2.5 rounded-xl border bg-background px-4 py-2 cursor-pointer hover:bg-muted/50 transition-colors shadow-sm"
                >
                  <HealthScoreRing score={health_score} size={36} strokeWidth={3} />
                  <div className="text-left">
                    <p className="text-base font-bold leading-none tabular-nums">
                      {health_score}
                      <span className="text-sm text-muted-foreground font-normal">/100</span>
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">Health Score</p>
                  </div>
                </button>
                {/* Score breakdown inline */}
                {dashboard.score_breakdown &&
                  Object.keys(dashboard.score_breakdown).length > 0 &&
                  !showScoreBreakdown && (
                    <div className="hidden md:flex items-center gap-3">
                      {Object.entries(dashboard.score_breakdown)
                        .slice(0, 4)
                        .map(([key, val]) => {
                          const pct = Math.round((val.score / val.max) * 100);
                          return (
                            <div key={key} className="flex items-center gap-1.5">
                              <div className="h-1.5 w-12 bg-muted rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500"}`}
                                  style={{ width: `${pct}%` }}
                                />
                              </div>
                              <span className="text-[11px] text-muted-foreground font-medium capitalize">
                                {key.replace(/_/g, " ")}
                              </span>
                            </div>
                          );
                        })}
                    </div>
                  )}
              </div>
              {/* Risk assessment */}
              {riskAssessment && (
                <div className="flex items-center gap-3">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-sm font-bold ${riskAssessment.risk_level === "high" ? "bg-red-50 text-red-700 border-red-200" : riskAssessment.risk_level === "moderate" ? "bg-amber-50 text-amber-700 border-amber-200" : "bg-emerald-50 text-emerald-700 border-emerald-200"}`}
                  >
                    <span
                      className={`inline-block h-2 w-2 rounded-full ${riskAssessment.risk_level === "high" ? "bg-red-500" : riskAssessment.risk_level === "moderate" ? "bg-amber-500" : "bg-emerald-500"}`}
                    />
                    {riskAssessment.risk_level === "high"
                      ? "High Risk"
                      : riskAssessment.risk_level === "moderate"
                        ? "Moderate Risk"
                        : "Low Risk"}
                  </span>
                  {riskAssessment.factors.length > 0 && (
                    <div className="flex items-center gap-1.5">
                      {riskAssessment.factors.slice(0, 3).map((f, i) => (
                        <Badge
                          key={i}
                          variant="outline"
                          className={`text-[11px] font-semibold ${f.severity === "high" ? "text-red-600 border-red-200" : f.severity === "moderate" ? "text-amber-600 border-amber-200" : "text-blue-600 border-blue-200"}`}
                        >
                          {f.factor}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            {/* Expanded score breakdown */}
            {dashboard.score_breakdown && showScoreBreakdown && (
              <div className="mt-4 p-4 bg-muted/30 rounded-xl border">
                <ScoreBreakdown breakdown={dashboard.score_breakdown} />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── SECTION 2: Key Vitals ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-6 gap-3">
        {member.bmi && (
          <div
            className={`rounded-xl border p-4 text-center shadow-sm transition-shadow hover:shadow-md ${member.bmi_category ? BMI_CATEGORY_COLORS[member.bmi_category] || "" : "bg-muted"}`}
          >
            <Activity className="h-4 w-4 mx-auto mb-2 opacity-50" />
            <p className="text-2xl font-bold tracking-tight">{member.bmi.toFixed(1)}</p>
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mt-0.5">
              BMI
            </p>
            {member.bmi_category && (
              <p className="text-xs font-semibold mt-1 opacity-80">{member.bmi_category}</p>
            )}
          </div>
        )}
        {hba1cHistory.length > 0 &&
          (() => {
            const latest = hba1cHistory[hba1cHistory.length - 1].hba1c_value;
            const cat = getHba1cCategory(latest);
            return (
              <div
                className={`rounded-xl border p-4 text-center shadow-sm transition-shadow hover:shadow-md ${HBA1C_CATEGORY_COLORS[cat] || ""}`}
              >
                <FlaskConical className="h-4 w-4 mx-auto mb-2 opacity-50" />
                <p className="text-2xl font-bold tracking-tight">{latest}%</p>
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mt-0.5">
                  HbA1c
                </p>
                <p className="text-xs font-semibold mt-1 opacity-80">{cat}</p>
              </div>
            );
          })()}
        <div className="rounded-xl border bg-violet-50 border-violet-200 p-4 text-center shadow-sm transition-shadow hover:shadow-md">
          <Activity className="h-4 w-4 mx-auto mb-2 text-violet-400" />
          <p className="text-2xl font-bold tracking-tight text-violet-700">
            {active_medications_count}
          </p>
          <p className="text-xs font-semibold uppercase tracking-wider text-violet-500 mt-0.5">
            Medications
          </p>
        </div>
        {active_conditions_count > 0 && (
          <div className="rounded-xl border bg-rose-50 border-rose-200 p-4 text-center shadow-sm transition-shadow hover:shadow-md">
            <Activity className="h-4 w-4 mx-auto mb-2 text-rose-400" />
            <p className="text-2xl font-bold tracking-tight text-rose-700">
              {active_conditions_count}
            </p>
            <p className="text-xs font-semibold uppercase tracking-wider text-rose-500 mt-0.5">
              Conditions
            </p>
          </div>
        )}
        {hasAllergies &&
          member.allergies!.map((a, i) => (
            <div
              key={i}
              className={`rounded-xl border p-4 text-center shadow-sm transition-shadow hover:shadow-md ${ALLERGY_SEVERITY_COLORS[a.severity] ?? ALLERGY_SEVERITY_COLORS.mild}`}
            >
              <p className="text-sm font-bold">{a.name}</p>
              <p className="text-xs font-semibold mt-1 uppercase tracking-wider opacity-70">
                {a.severity} allergy
              </p>
            </div>
          ))}
        {hasEmergency && (
          <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-center shadow-sm">
            <Phone className="h-4 w-4 mx-auto mb-2 text-blue-500" />
            <p className="text-sm font-bold text-blue-800 truncate">
              {member.emergency_contact_name}
            </p>
            <p className="text-xs text-blue-600/70 mt-0.5">{member.emergency_contact_phone}</p>
          </div>
        )}
      </div>

      {/* ── SECTION 3: Quick Actions ── */}
      <div className="flex items-center gap-2 flex-wrap print:hidden">
        {quickActions.map((action) => {
          const Icon = action.icon;
          return (
            <Link
              key={action.hrefSuffix}
              to={`/members/${member.id}${action.hrefSuffix}`}
              className={`inline-flex items-center gap-1.5 rounded-xl border px-3.5 py-2 text-sm font-semibold transition-colors shadow-sm ${action.color}`}
            >
              <Icon className="h-4 w-4" />
              {action.label}
            </Link>
          );
        })}
      </div>

      {/* ── SECTION 4: Reminders + HbA1c Trend ── */}
      {(memberReminders.length > 0 || hba1cHistory.length >= 1) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {hba1cHistory.length >= 1 && (
            <Card className="shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold">HbA1c Trend</CardTitle>
              </CardHeader>
              <CardContent>
                <ExpandedHba1cChart data={hba1cHistory} />
              </CardContent>
            </Card>
          )}
          {memberReminders.length > 0 && (
            <Card className="overflow-hidden shadow-sm">
              <div className="h-1 bg-gradient-to-r from-amber-400 to-blue-500" />
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Bell className="h-4 w-4 text-blue-500" />
                  Upcoming
                  <Badge variant="secondary" className="text-xs">
                    {memberReminders.length}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {memberReminders.map((rem) => (
                    <div
                      key={rem.id}
                      className="flex items-center justify-between rounded-xl bg-muted/40 px-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-semibold truncate">{rem.title}</p>
                        <p className="text-xs text-muted-foreground">
                          {formatRelativeTime(rem.start_datetime)}
                        </p>
                      </div>
                      <Badge variant="outline" className="text-xs shrink-0 ml-2">
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

      {/* ── SECTION 5: Medications (full width) ── */}
      <ActiveMedicationsTable memberId={member.id} medications={active_medications ?? []} />

      {/* ── SECTION 5.5: Chronic Condition Charts ── */}
      <ChronicConditionCharts memberId={member.id} />

      {/* ── SECTION 6: AI Cards Row ── */}
      <div className="grid gap-5 md:grid-cols-2">
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

      {/* ── SECTION 7: Care Cards ── */}
      <div className="grid gap-5 md:grid-cols-2 print:hidden">
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
