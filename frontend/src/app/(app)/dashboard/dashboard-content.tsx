import React, { useState, useMemo, useEffect, Suspense } from "react";
import { Link } from "react-router-dom";
import {
  Users,
  Stethoscope,
  CalendarClock,
  Plus,
  UserPlus,
  Activity,
  Heart,
  FileText,
  Bell,
  AlertTriangle,
  Pill,
  ChevronRight,
  ShieldCheck,
  TrendingUp,
  Clock,
  BarChart3,
  Zap,
  ArrowRight,
  Sparkles,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  RELATIONSHIP_LABELS,
  RECORD_TYPE_LABELS,
  BMI_CATEGORY_COLORS,
  HBA1C_CATEGORY_COLORS,
} from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import { QuickAddRecordDialog } from "@/components/records/quick-add-record-dialog";
import { QuickLogInput } from "@/components/records/quick-log-input";
import { useRecordQuickView } from "@/components/records/record-quick-view-provider";
import { getLastUsedMember, setLastUsedMember } from "@/lib/member-context";
import { Hba1cModernChart } from "@/components/dashboard/hba1c-modern-chart";
import { getMemberDashboard } from "@/lib/api/members";
import { WelcomeCard } from "@/components/shared/welcome-card";
import { ReportGenerator } from "@/components/shared/report-generator";
import { AlertsFeed } from "@/components/dashboard/alerts-feed";
import { PreventiveTimeline } from "@/components/dashboard/preventive-timeline";
import { MedicationSummaryWidget } from "@/components/dashboard/medication-summary";
import { FamilyComparisonChart } from "@/components/dashboard/family-comparison-chart";
import { ScoreBreakdown } from "@/components/dashboard/score-breakdown";
import { useDashboardSummary } from "@/hooks/use-dashboard";
import { listHealthAlerts, dismissHealthAlert } from "@/lib/api/health-alerts";
import { toast } from "sonner";
import type { DashboardAlert } from "@/lib/types/dashboard";

const HealthTrendsChart = React.lazy(() =>
  import("@/components/dashboard/health-trends-chart").then((mod) => ({
    default: mod.HealthTrendsChart,
  }))
);
const RecordTypeChart = React.lazy(() =>
  import("@/components/dashboard/record-type-chart").then((mod) => ({
    default: mod.RecordTypeChart,
  }))
);

import type { FamilyMemberResponse } from "@/lib/types/member";
import type { ReminderResponse } from "@/lib/types/reminder";
import type { HealthRecordResponse } from "@/lib/types/health-record";

/* ── Helpers ── */

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

function extractPreview(
  clinicalData: string | null | undefined,
  diagnosis: string | null | undefined
): string {
  if (diagnosis) return diagnosis;
  if (!clinicalData) return "";
  try {
    const parsed = JSON.parse(clinicalData);
    if (parsed.chief_complaint) return parsed.chief_complaint;
    if (parsed.glucose_value) return `Glucose: ${parsed.glucose_value} mg/dL`;
    if (parsed.hba1c_value) return `HbA1c: ${parsed.hba1c_value}%`;
    if (Array.isArray(parsed.lab_results) && parsed.lab_results.length > 0)
      return `${parsed.lab_results.length} tests: ${parsed.lab_results
        .slice(0, 2)
        .map((t: { test_name?: string }) => t.test_name)
        .join(", ")}`;
  } catch {
    const first = clinicalData.split("\n")[0];
    return first.length > 60 ? first.slice(0, 60) + "..." : first;
  }
  return "";
}

function scoreColor(score: number): string {
  if (score >= 75) return "#16a34a";
  if (score >= 50) return "#d97706";
  return "#dc2626";
}

function riskColor(level: string): string {
  if (level === "low") return "text-emerald-600";
  if (level === "moderate") return "text-amber-600";
  return "text-red-600";
}

function riskBg(level: string): string {
  if (level === "low") return "bg-emerald-50 border-emerald-200";
  if (level === "moderate") return "bg-amber-50 border-amber-200";
  return "bg-red-50 border-red-200";
}

/* ── Health Score Ring ── */

function HealthScoreRing({
  score,
  size = 64,
  strokeWidth = 5,
  riskLevel,
}: {
  score: number;
  size?: number;
  strokeWidth?: number;
  riskLevel?: string;
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
        <span className="font-bold leading-none" style={{ color, fontSize: size * 0.28 }}>
          {score}
        </span>
        <span className="text-[10px] text-muted-foreground">/100</span>
      </div>
      {riskLevel && riskLevel !== "low" && (
        <span
          className={`absolute -top-1 -right-1 inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold text-white shadow-sm ${riskLevel === "high" ? "bg-red-500" : "bg-amber-500"}`}
        >
          !
        </span>
      )}
    </div>
  );
}

/* ── Props ── */

interface DashboardStats {
  providersCount: number;
  conversationsCount: number;
  unreadNotifications: number;
  upcomingReminders: ReminderResponse[];
}

interface DashboardContentProps {
  members: FamilyMemberResponse[];
  householdName: string;
  stats: DashboardStats;
  records: HealthRecordResponse[];
}

/* ── Main Component ── */

export function DashboardContent({
  members,
  householdName,
  stats,
  records,
}: DashboardContentProps) {
  const [quickAddOpen, setQuickAddOpen] = useState(false);
  const [quickLogMemberId, setQuickLogMemberId] = useState<string | null>(null);
  const { openQuickView } = useRecordQuickView();
  const activeMembers = useMemo(() => members.filter((m) => m.is_active), [members]);
  const activeCount = activeMembers.length;

  // Dashboard summary from new API
  const { summary, isLoading: summaryLoading, mutate: mutateSummary } = useDashboardSummary();

  // Health scores from summary (fallback to old per-member fetch)
  const [memberScores, setMemberScores] = useState<
    Record<
      string,
      {
        score: number;
        medications: number;
        conditions: number;
        riskLevel: string;
        breakdown: Record<string, { score: number; max: number; label: string }>;
      }
    >
  >({});
  const [scoresLoading, setScoresLoading] = useState(true);

  useEffect(() => {
    if (summary?.scores?.length) {
      const map: Record<
        string,
        {
          score: number;
          medications: number;
          conditions: number;
          riskLevel: string;
          breakdown: Record<string, { score: number; max: number; label: string }>;
        }
      > = {};
      for (const s of summary.scores) {
        map[s.member_id] = {
          score: s.health_score,
          medications: 0,
          conditions: 0,
          riskLevel: s.risk_level || "low",
          breakdown: s.score_breakdown || {},
        };
      }
      setMemberScores(map);
      setScoresLoading(false);
    } else if (!summaryLoading && activeMembers.length > 0) {
      Promise.all(
        activeMembers.map((m) =>
          getMemberDashboard(m.id)
            .then((d) => ({
              id: m.id,
              data: {
                score: d.health_score,
                medications: d.active_medications_count,
                conditions: d.active_conditions_count,
                riskLevel: d.health_score < 40 ? "high" : d.health_score <= 65 ? "moderate" : "low",
                breakdown: d.score_breakdown || {},
              },
            }))
            .catch(() => ({
              id: m.id,
              data: { score: 0, medications: 0, conditions: 0, riskLevel: "low", breakdown: {} },
            }))
        )
      ).then((results) => {
        const map: Record<
          string,
          {
            score: number;
            medications: number;
            conditions: number;
            riskLevel: string;
            breakdown: Record<string, { score: number; max: number; label: string }>;
          }
        > = {};
        for (const r of results) map[r.id] = r.data;
        setMemberScores(map);
        setScoresLoading(false);
      });
    } else if (!summaryLoading) {
      setScoresLoading(false);
    }
  }, [summary, summaryLoading, activeMembers]);

  // Restore last-used member on mount
  useEffect(() => {
    if (quickLogMemberId) return;
    const last = getLastUsedMember();
    if (last) {
      const match = activeMembers.find((m) => m.id === last.id);
      if (match) setQuickLogMemberId(match.id);
    }
  }, [quickLogMemberId, activeMembers]);

  const memberNames = useMemo(() => {
    const names: Record<string, string> = {};
    for (const m of members) names[m.id] = `${m.first_name} ${m.last_name}`;
    return names;
  }, [members]);

  const numericRecords = useMemo(
    () =>
      records.filter(
        (r) => ["blood_glucose", "lab_report", "hba1c"].includes(r.record_type) && !r.is_deleted
      ),
    [records]
  );

  const activeRecords = useMemo(() => records.filter((r) => !r.is_deleted), [records]);

  const recentActivity = useMemo(() => {
    return activeRecords
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 6);
  }, [activeRecords]);

  const recordsThisMonth = useMemo(() => {
    const now = new Date();
    const thisMonth = now.getFullYear() * 12 + now.getMonth();
    return activeRecords.filter((r) => {
      const m = new Date(r.created_at).getFullYear() * 12 + new Date(r.created_at).getMonth();
      return m === thisMonth;
    }).length;
  }, [activeRecords]);

  // Record type distribution
  const recordTypeDistribution = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of activeRecords) {
      const type = r.record_type || "unknown";
      counts[type] = (counts[type] || 0) + 1;
    }
    return Object.entries(counts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 6);
  }, [activeRecords]);

  // HbA1c data for chart
  const hba1cData = useMemo(() => {
    const entries: { date: string; value: number; memberName: string }[] = [];
    for (const r of activeRecords) {
      if (r.record_type !== "blood_glucose" && r.record_type !== "doctor_visit") continue;
      try {
        const parsed = JSON.parse(r.clinical_data);
        if (parsed.hba1c_value) {
          const v = parseFloat(parsed.hba1c_value);
          if (!isNaN(v))
            entries.push({
              date: r.record_date,
              value: v,
              memberName: memberNames[r.family_member_id] || "Unknown",
            });
          continue;
        }
        for (const key of ["lab_results", "tests"]) {
          const labs = parsed[key];
          if (!Array.isArray(labs)) continue;
          for (const test of labs) {
            const name = (test.test_name || "").toLowerCase();
            if (name.includes("hba1c") || name.includes("a1c") || name.includes("glycated")) {
              const match = (test.result || "").match(/(\d+\.?\d*)/);
              if (match) {
                entries.push({
                  date: r.record_date,
                  value: parseFloat(match[1]),
                  memberName: memberNames[r.family_member_id] || "Unknown",
                });
                break;
              }
            }
          }
        }
      } catch {
        /* skip */
      }
    }
    return entries.sort((a, b) => a.date.localeCompare(b.date));
  }, [activeRecords, memberNames]);

  const hba1cChartRows = useMemo(() => {
    const byDate: Record<string, { date: string; [k: string]: string | number }> = {};
    for (const e of hba1cData) {
      if (!byDate[e.date]) byDate[e.date] = { date: e.date };
      byDate[e.date][e.memberName] = e.value;
    }
    return Object.values(byDate).slice(-15);
  }, [hba1cData]);

  const hba1cMembers = useMemo(() => [...new Set(hba1cData.map((e) => e.memberName))], [hba1cData]);

  const memberRecordCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of activeRecords)
      counts[r.family_member_id] = (counts[r.family_member_id] || 0) + 1;
    return counts;
  }, [activeRecords]);

  // Family summary stats
  const familyStats = useMemo(() => {
    const scoreValues = Object.values(memberScores);
    const avgScore = scoreValues.length
      ? Math.round(scoreValues.reduce((s, d) => s + d.score, 0) / scoreValues.length)
      : 0;
    const totalConditions = scoreValues.reduce((s, d) => s + d.conditions, 0);
    const totalMedications = scoreValues.reduce((s, d) => s + d.medications, 0);
    return { avgScore, totalConditions, totalMedications };
  }, [memberScores]);

  // Alerts state
  const [alerts, setAlerts] = useState<DashboardAlert[]>([]);

  useEffect(() => {
    if (summary?.alerts) {
      setAlerts(summary.alerts);
    }
  }, [summary]);

  async function handleDismissAlert(alertId: string) {
    try {
      await dismissHealthAlert(alertId);
      setAlerts((prev) => prev.filter((a) => a.id !== alertId));
      toast.success("Alert dismissed");
      mutateSummary();
    } catch {
      toast.error("Failed to dismiss alert");
    }
  }

  // Record type color map
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

  return (
    <div className="space-y-5 max-w-[1600px] mx-auto">
      {/* ═══ HERO SECTION ═══ */}
      <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-card via-card to-muted/30 shadow-sm">
        <div className="absolute inset-0 bg-[linear-gradient(135deg,transparent_40%,hsl(var(--primary)/0.03)_100%)]" />
        <div className="relative px-6 py-5">
          <div className="flex items-start justify-between flex-wrap gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">{householdName}</h1>
              <p className="text-sm text-muted-foreground mt-1">Family health at a glance</p>
            </div>
            <div className="flex items-center gap-2">
              {stats.unreadNotifications > 0 && (
                <Link
                  to="/notifications"
                  className="inline-flex items-center gap-1.5 rounded-xl border px-3 h-9 text-sm font-medium hover:bg-muted/50 transition-colors"
                >
                  <Bell className="h-4 w-4" />
                  <span>{stats.unreadNotifications}</span>
                </Link>
              )}
              <Link
                to="/members/new"
                className="inline-flex items-center gap-1.5 rounded-xl bg-primary text-primary-foreground px-4 h-9 text-sm font-semibold hover:bg-primary/90 transition-colors shadow-sm"
              >
                <Plus className="h-4 w-4" />
                Add Member
              </Link>
            </div>
          </div>

          {/* Stat pills */}
          <div className="flex items-center gap-3 mt-4 flex-wrap">
            <div className="flex items-center gap-2 rounded-xl bg-background/80 border px-3.5 py-2 shadow-sm">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10">
                <Users className="h-4 w-4 text-blue-600" />
              </div>
              <div>
                <p className="text-lg font-bold leading-none">{activeCount}</p>
                <p className="text-[11px] text-muted-foreground">Members</p>
              </div>
            </div>
            <div className="flex items-center gap-2 rounded-xl bg-background/80 border px-3.5 py-2 shadow-sm">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10">
                <FileText className="h-4 w-4 text-emerald-600" />
              </div>
              <div>
                <p className="text-lg font-bold leading-none">{activeRecords.length}</p>
                <p className="text-[11px] text-muted-foreground">Records</p>
              </div>
            </div>
            <div className="flex items-center gap-2 rounded-xl bg-background/80 border px-3.5 py-2 shadow-sm">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/10">
                <Stethoscope className="h-4 w-4 text-violet-600" />
              </div>
              <div>
                <p className="text-lg font-bold leading-none">{stats.providersCount}</p>
                <p className="text-[11px] text-muted-foreground">Providers</p>
              </div>
            </div>
            {recordsThisMonth > 0 && (
              <div className="flex items-center gap-2 rounded-xl bg-background/80 border px-3.5 py-2 shadow-sm">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500/10">
                  <TrendingUp className="h-4 w-4 text-teal-600" />
                </div>
                <div>
                  <p className="text-lg font-bold leading-none">{recordsThisMonth}</p>
                  <p className="text-[11px] text-muted-foreground">This month</p>
                </div>
              </div>
            )}
            {!scoresLoading && familyStats.avgScore > 0 && (
              <div className="flex items-center gap-2 rounded-xl bg-background/80 border px-3.5 py-2 shadow-sm">
                <div
                  className="flex h-8 w-8 items-center justify-center rounded-lg"
                  style={{ backgroundColor: `${scoreColor(familyStats.avgScore)}15` }}
                >
                  <Activity
                    className="h-4 w-4"
                    style={{ color: scoreColor(familyStats.avgScore) }}
                  />
                </div>
                <div>
                  <p className="text-lg font-bold leading-none">{familyStats.avgScore}</p>
                  <p className="text-[11px] text-muted-foreground">Avg Score</p>
                </div>
              </div>
            )}
            {summary?.risk_summary &&
              (summary.risk_summary.high_risk_members > 0 ||
                summary.risk_summary.moderate_risk_members > 0) && (
                <div className="flex items-center gap-2 rounded-xl bg-red-500/10 border border-red-200 px-3.5 py-2">
                  <AlertTriangle className="h-4 w-4 text-red-600" />
                  <div>
                    <p className="text-sm font-bold text-red-700 leading-none">
                      {summary.risk_summary.high_risk_members > 0 &&
                        `${summary.risk_summary.high_risk_members} High`}
                      {summary.risk_summary.high_risk_members > 0 &&
                        summary.risk_summary.moderate_risk_members > 0 &&
                        " · "}
                      {summary.risk_summary.moderate_risk_members > 0 &&
                        `${summary.risk_summary.moderate_risk_members} Mod`}
                    </p>
                    <p className="text-[11px] text-red-600/70">Risk alerts</p>
                  </div>
                </div>
              )}
          </div>
        </div>
      </div>

      {/* Welcome card for new users */}
      <WelcomeCard
        hasMembers={activeMembers.length > 0}
        hasProviders={stats.providersCount > 0}
        hasRecords={activeRecords.length > 0}
        hasConversations={stats.conversationsCount > 0}
      />

      {/* Quick Log */}
      {activeMembers.length > 0 && (
        <div className="rounded-xl border bg-card px-4 py-3 shadow-sm">
          {quickLogMemberId ? (
            <div className="flex items-center gap-3">
              <button
                onClick={() => setQuickLogMemberId(null)}
                className="text-sm font-medium text-foreground hover:text-primary shrink-0 underline underline-offset-2"
              >
                Change
              </button>
              <QuickLogInput
                memberId={quickLogMemberId}
                memberName={memberNames[quickLogMemberId]}
                onLogged={() =>
                  setLastUsedMember(quickLogMemberId, memberNames[quickLogMemberId] || "")
                }
              />
            </div>
          ) : (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm text-muted-foreground font-medium">Quick log for:</span>
              {activeMembers.slice(0, 5).map((m) => (
                <button
                  key={m.id}
                  onClick={() => setQuickLogMemberId(m.id)}
                  className="inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-1.5 text-sm font-semibold hover:bg-primary hover:text-primary-foreground transition-colors focus:ring-2 focus:ring-primary focus:ring-offset-1"
                >
                  {m.first_name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ═══ ALERTS FEED ═══ */}
      {alerts.length > 0 && <AlertsFeed alerts={alerts} onDismiss={handleDismissAlert} />}

      {/* ═══ FAMILY HEALTH RINGS ═══ */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold">Family Health</h2>
          {!scoresLoading && familyStats.avgScore > 0 && (
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <span>
                Avg <strong className="text-foreground">{familyStats.avgScore}</strong>/100
              </span>
              <span className="text-border">|</span>
              <span>{familyStats.totalMedications} medications</span>
              <span className="text-border">|</span>
              <span>{familyStats.totalConditions} conditions</span>
            </div>
          )}
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
          {activeMembers.map((member) => {
            const scoreData = memberScores[member.id];
            const fullName = `${member.first_name} ${member.last_name}`;
            const recCount = memberRecordCounts[member.id] || 0;
            const initials = fullName
              .split(" ")
              .map((n) => n[0])
              .join("")
              .slice(0, 2)
              .toUpperCase();

            return (
              <Link
                key={member.id}
                to={`/members/${member.id}`}
                className="group rounded-xl border bg-card p-4 hover:shadow-lg hover:-translate-y-0.5 transition-all shadow-sm"
              >
                <div className="flex items-start gap-3">
                  {scoresLoading ? (
                    <Skeleton className="h-[64px] w-[64px] rounded-full shrink-0" />
                  ) : scoreData ? (
                    <HealthScoreRing
                      score={scoreData.score}
                      size={64}
                      riskLevel={scoreData.riskLevel}
                    />
                  ) : (
                    <div className="flex h-[64px] w-[64px] items-center justify-center rounded-full bg-muted/50 shrink-0">
                      <span className="text-base font-bold text-muted-foreground">--</span>
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold truncate">{fullName}</p>
                    <Badge variant="outline" className="text-[11px] mt-0.5 px-1.5 py-0">
                      {RELATIONSHIP_LABELS[member.relationship]}
                    </Badge>
                  </div>
                </div>

                {/* Details row */}
                <div className="flex items-center gap-2 mt-3 text-xs text-muted-foreground">
                  {member.bmi && (
                    <span className="inline-flex items-center gap-1 rounded-md bg-muted/60 px-1.5 py-0.5 font-medium">
                      BMI {member.bmi.toFixed(1)}
                    </span>
                  )}
                  {recCount > 0 && (
                    <span className="inline-flex items-center gap-1 rounded-md bg-muted/60 px-1.5 py-0.5 font-medium">
                      {recCount} records
                    </span>
                  )}
                  {scoreData && scoreData.medications > 0 && (
                    <span className="inline-flex items-center gap-1 rounded-md bg-violet-500/10 px-1.5 py-0.5 font-medium text-violet-600">
                      {scoreData.medications} meds
                    </span>
                  )}
                  {member.blood_group && (
                    <span className="inline-flex items-center rounded-md bg-red-500/10 px-1.5 py-0.5 font-medium text-red-600">
                      {member.blood_group}
                    </span>
                  )}
                </div>

                {/* Score breakdown (compact) */}
                {scoreData?.breakdown && Object.keys(scoreData.breakdown).length > 0 && (
                  <div className="mt-2.5">
                    <ScoreBreakdown
                      breakdown={scoreData.breakdown}
                      total={scoreData.score}
                      compact
                    />
                  </div>
                )}

                {/* Risk badge */}
                {scoreData?.riskLevel && scoreData.riskLevel !== "low" && (
                  <div className="mt-2">
                    <span
                      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-bold ${riskBg(scoreData.riskLevel)} ${riskColor(scoreData.riskLevel)}`}
                    >
                      {scoreData.riskLevel === "high" ? "HIGH RISK" : "MODERATE RISK"}
                    </span>
                  </div>
                )}
              </Link>
            );
          })}
          {/* Add Member card */}
          <Link
            to="/members/new"
            className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border/60 bg-card/30 p-4 hover:shadow-md hover:border-primary/30 transition-all group min-h-[180px]"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted/50 group-hover:bg-primary/10 transition-colors">
              <Plus className="h-6 w-6 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
            <p className="text-sm font-medium text-muted-foreground group-hover:text-foreground transition-colors">
              Add Family Member
            </p>
          </Link>
        </div>
      </div>

      {/* ═══ MAIN CONTENT: Charts + Sidebar ═══ */}
      <div className="grid gap-5 lg:grid-cols-3">
        {/* Left: Charts */}
        <div className="lg:col-span-2 space-y-5">
          {/* Charts row */}
          <div className="grid gap-5 md:grid-cols-2">
            {(numericRecords.length > 0 || activeRecords.length > 0) && (
              <Suspense
                fallback={
                  <>
                    <Card>
                      <CardContent className="py-8">
                        <Skeleton className="h-48 w-full" />
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="py-8">
                        <Skeleton className="h-48 w-full" />
                      </CardContent>
                    </Card>
                  </>
                }
              >
                <>
                  {numericRecords.length > 0 && (
                    <HealthTrendsChart records={numericRecords} memberNames={memberNames} />
                  )}
                  {activeRecords.length > 0 && <RecordTypeChart records={activeRecords} />}
                </>
              </Suspense>
            )}

            {/* Family Comparison Radar Chart */}
            {summary?.scores && summary.scores.length >= 2 && (
              <Suspense
                fallback={
                  <Card>
                    <CardContent className="py-8">
                      <Skeleton className="h-48 w-full" />
                    </CardContent>
                  </Card>
                }
              >
                <FamilyComparisonChart scores={summary.scores} />
              </Suspense>
            )}
          </div>

          {/* HbA1c Trend */}
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Heart className="h-4 w-4 text-red-500" />
                  HbA1c Trend
                </CardTitle>
                {hba1cData.length > 0 &&
                  (() => {
                    const latest = hba1cData[hba1cData.length - 1].value;
                    const cat = latest < 5.7 ? "Normal" : latest < 6.5 ? "Prediabetes" : "Diabetes";
                    return (
                      <Badge
                        variant="secondary"
                        className={`text-sm px-3 py-0.5 font-semibold ${HBA1C_CATEGORY_COLORS[cat] ?? ""}`}
                      >
                        {latest}% — {cat}
                      </Badge>
                    );
                  })()}
              </div>
            </CardHeader>
            <CardContent>
              {hba1cChartRows.length < 2 ? (
                <div className="flex items-center justify-center py-8 text-foreground/70">
                  <p className="text-sm">
                    {hba1cData.length === 0
                      ? "No HbA1c readings yet. Add one via Blood Glucose / HbA1c quick entry."
                      : "Add at least 2 HbA1c readings to see the trend."}
                  </p>
                </div>
              ) : (
                <Hba1cModernChart rows={hba1cChartRows} members={hba1cMembers} />
              )}
            </CardContent>
          </Card>

          {/* Record Activity & Type Distribution */}
          <div className="grid gap-5 md:grid-cols-2">
            {/* Record Type Distribution */}
            {recordTypeDistribution.length > 0 && (
              <Card className="shadow-sm">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <BarChart3 className="h-4 w-4 text-blue-500" />
                    Records by Type
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2.5">
                    {recordTypeDistribution.map(([type, count]) => {
                      const pct =
                        activeRecords.length > 0
                          ? Math.round((count / activeRecords.length) * 100)
                          : 0;
                      return (
                        <div key={type} className="space-y-1">
                          <div className="flex items-center justify-between text-sm">
                            <span className="font-medium">
                              {(RECORD_TYPE_LABELS as Record<string, string>)[type] || type}
                            </span>
                            <span className="text-muted-foreground">
                              {count} ({pct}%)
                            </span>
                          </div>
                          <div className="h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${TYPE_COLORS[type] || "bg-gray-400"}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Vaccination & Preventive Summary */}
            <Card className="shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-emerald-500" />
                  Preventive Health
                </CardTitle>
              </CardHeader>
              <CardContent>
                {summary?.preventive_care && summary.preventive_care.length > 0 ? (
                  <div className="space-y-2.5">
                    {summary.preventive_care.slice(0, 5).map((item, idx) => {
                      const statusColors: Record<string, string> = {
                        overdue: "text-red-600 bg-red-50 border-red-200",
                        due_soon: "text-amber-600 bg-amber-50 border-amber-200",
                        upcoming: "text-emerald-600 bg-emerald-50 border-emerald-200",
                      };
                      return (
                        <div
                          key={`${item.member_id}-${idx}`}
                          className="flex items-center justify-between rounded-lg border px-3 py-2"
                        >
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium truncate">{item.recommendation}</p>
                            <p className="text-xs text-muted-foreground">{item.member_name}</p>
                          </div>
                          <Badge
                            className={`text-[11px] font-semibold border ${statusColors[item.due_status] || ""}`}
                          >
                            {item.due_status === "overdue"
                              ? "Overdue"
                              : item.due_status === "due_soon"
                                ? "Due Soon"
                                : "Upcoming"}
                          </Badge>
                        </div>
                      );
                    })}
                    {summary.preventive_care.length > 5 && (
                      <p className="text-xs text-muted-foreground text-center pt-1">
                        +{summary.preventive_care.length - 5} more items
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2 py-6 text-foreground/70">
                    <ShieldCheck className="h-8 w-8 text-emerald-400" />
                    <p className="text-sm font-medium">Preventive care up to date</p>
                    <p className="text-xs text-muted-foreground">
                      Recommendations will appear as they become due
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        {/* ═══ RIGHT SIDEBAR ═══ */}
        <div className="space-y-5">
          {/* Quick Actions */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                Quick Actions
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-0.5">
              <Link
                to="/members/new"
                className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors group"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10">
                  <UserPlus className="h-4 w-4 text-blue-600" />
                </div>
                <span className="text-sm font-medium flex-1">Add Member</span>
                <ChevronRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-foreground transition-colors" />
              </Link>
              <Link
                to="/providers/new"
                className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors group"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10">
                  <Stethoscope className="h-4 w-4 text-emerald-600" />
                </div>
                <span className="text-sm font-medium flex-1">Add Provider</span>
                <ChevronRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-foreground transition-colors" />
              </Link>
              <Link
                to="/reminders/new"
                className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors group"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/10">
                  <CalendarClock className="h-4 w-4 text-amber-600" />
                </div>
                <span className="text-sm font-medium flex-1">New Reminder</span>
                <ChevronRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-foreground transition-colors" />
              </Link>
              <button
                onClick={() => setQuickAddOpen(true)}
                className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors group w-full text-left"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500/10">
                  <Plus className="h-4 w-4 text-teal-600" />
                </div>
                <span className="text-sm font-medium flex-1">Add Record</span>
                <ChevronRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-foreground transition-colors" />
              </button>
              <div className="px-3 py-2">
                <ReportGenerator variant="ghost" />
              </div>
            </CardContent>
          </Card>

          {/* Medication Summary */}
          {summary?.medication_summary &&
            summary.medication_summary.total_active_medications > 0 && (
              <MedicationSummaryWidget
                summary={summary.medication_summary}
                memberNames={memberNames}
              />
            )}

          {/* Upcoming Reminders */}
          <Card className="shadow-sm">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Clock className="h-4 w-4 text-amber-500" />
                Reminders
                {stats.upcomingReminders.length > 0 && (
                  <Badge className="text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300 px-1.5 py-0">
                    {stats.upcomingReminders.length}
                  </Badge>
                )}
              </CardTitle>
              <Link
                to="/reminders"
                className="text-sm font-medium text-primary hover:underline underline-offset-2"
              >
                View all
              </Link>
            </CardHeader>
            <CardContent>
              {stats.upcomingReminders.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-6 text-foreground/70">
                  <CalendarClock className="h-8 w-8 text-foreground/20" />
                  <p className="text-sm font-medium">No upcoming reminders</p>
                  <Link to="/reminders/new" className="text-xs text-primary hover:underline">
                    Create one
                  </Link>
                </div>
              ) : (
                <div className="space-y-2">
                  {stats.upcomingReminders.slice(0, 5).map((reminder) => {
                    const isOverdue = new Date(reminder.start_datetime) < new Date();
                    const memberName = reminder.family_member_id
                      ? memberNames[reminder.family_member_id]
                      : null;
                    return (
                      <Link
                        key={reminder.id}
                        to="/reminders"
                        className={`flex items-center justify-between rounded-xl px-3 py-2.5 transition-colors border ${isOverdue ? "bg-red-50 border-red-200 dark:bg-red-950/20" : "bg-muted/30 border-transparent hover:bg-muted/50"}`}
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-semibold truncate">{reminder.title}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {formatRelativeTime(reminder.start_datetime)}
                            {memberName && <span className="ml-1 font-medium">— {memberName}</span>}
                          </p>
                        </div>
                        {isOverdue && (
                          <span className="text-[11px] font-bold text-red-800 bg-red-200 px-2 py-0.5 rounded-md border border-red-300 shrink-0">
                            OVERDUE
                          </span>
                        )}
                      </Link>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Recent Activity */}
          {recentActivity.length > 0 && (
            <Card className="shadow-sm">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Zap className="h-4 w-4 text-blue-500" />
                  Recent Activity
                </CardTitle>
                <Link
                  to="/records"
                  className="text-sm font-medium text-primary hover:underline underline-offset-2"
                >
                  View all
                </Link>
              </CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {recentActivity.map((record) => {
                    const preview = extractPreview(record.clinical_data, record.diagnosis);
                    return (
                      <button
                        key={record.id}
                        onClick={() => openQuickView(record.id, record.family_member_id)}
                        className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-muted/50 transition-colors w-full text-left focus:ring-2 focus:ring-primary focus:ring-offset-1"
                      >
                        <div className="flex items-center gap-2.5 min-w-0 flex-1">
                          <Badge
                            variant="outline"
                            className="text-[11px] shrink-0 px-1.5 py-0 font-semibold"
                          >
                            {RECORD_TYPE_LABELS[record.record_type] || record.record_type}
                          </Badge>
                          <div className="min-w-0">
                            <p className="text-sm font-medium truncate">
                              {memberNames[record.family_member_id] || "Unknown"}
                            </p>
                            {preview && (
                              <p className="text-xs text-muted-foreground truncate">{preview}</p>
                            )}
                          </div>
                        </div>
                        <span className="text-xs text-muted-foreground shrink-0 ml-2">
                          {formatDate(record.record_date)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* ═══ FAMILY MEMBERS TABLE ═══ */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold">Family Members</h2>
          <Link
            to="/members/new"
            className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline underline-offset-2"
          >
            <Plus className="h-3.5 w-3.5" />
            Add
          </Link>
        </div>
        <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
          <div className="hidden sm:grid grid-cols-[auto_1fr_auto_auto_auto] gap-4 px-5 py-3 bg-muted/30 border-b text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            <span>Member</span>
            <span>Details</span>
            <span className="text-center">Score</span>
            <span className="text-center">Risk</span>
            <span>Actions</span>
          </div>
          <div className="divide-y">
            {activeMembers.map((member) => {
              const fullName = `${member.first_name} ${member.last_name}`;
              const initials = fullName
                .split(" ")
                .map((n) => n[0])
                .join("")
                .slice(0, 2)
                .toUpperCase();
              const recCount = memberRecordCounts[member.id] || 0;
              const scoreData = memberScores[member.id];
              const allergyCount = member.allergies?.length || 0;
              const hasSevere = member.allergies?.some((a) => a.severity === "severe");

              return (
                <div
                  key={member.id}
                  className="group grid sm:grid-cols-[auto_1fr_auto_auto_auto] gap-4 items-center px-5 py-3.5 hover:bg-muted/20 transition-colors"
                >
                  {/* Avatar + Name */}
                  <Link
                    to={`/members/${member.id}`}
                    className="flex items-center gap-3 hover:opacity-80 transition-opacity"
                  >
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/10 to-primary/5 text-sm font-bold text-foreground">
                      {initials}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold truncate">{fullName}</p>
                      <p className="text-xs text-muted-foreground">
                        {RELATIONSHIP_LABELS[member.relationship]}
                      </p>
                    </div>
                  </Link>

                  {/* Details */}
                  <div className="flex items-center gap-2 flex-wrap">
                    {member.blood_group && (
                      <span className="text-xs font-semibold text-red-600 bg-red-50 px-2 py-0.5 rounded-md border border-red-200">
                        {member.blood_group}
                      </span>
                    )}
                    {member.bmi && (
                      <span className="text-xs font-medium bg-muted/60 px-2 py-0.5 rounded-md">
                        BMI {member.bmi.toFixed(1)}
                      </span>
                    )}
                    {recCount > 0 && (
                      <span className="text-xs font-medium bg-muted/60 px-2 py-0.5 rounded-md">
                        {recCount} records
                      </span>
                    )}
                    {scoreData && scoreData.medications > 0 && (
                      <span className="text-xs font-medium bg-violet-50 text-violet-600 px-2 py-0.5 rounded-md border border-violet-200">
                        {scoreData.medications} meds
                      </span>
                    )}
                    {allergyCount > 0 && (
                      <span
                        className={`text-xs font-semibold px-2 py-0.5 rounded-md border ${hasSevere ? "bg-red-50 text-red-600 border-red-200" : "bg-amber-50 text-amber-600 border-amber-200"}`}
                      >
                        {allergyCount} allerg{allergyCount !== 1 ? "ies" : "y"}
                      </span>
                    )}
                  </div>

                  {/* Score */}
                  <div className="text-center">
                    {scoreData ? (
                      <span
                        className={`text-base font-bold ${scoreData.score >= 75 ? "text-green-600" : scoreData.score >= 50 ? "text-amber-600" : "text-red-600"}`}
                      >
                        {scoreData.score}
                      </span>
                    ) : (
                      <span className="text-sm text-muted-foreground">--</span>
                    )}
                  </div>

                  {/* Risk */}
                  <div className="text-center">
                    {scoreData?.riskLevel ? (
                      <span
                        className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-bold ${riskBg(scoreData.riskLevel)} ${riskColor(scoreData.riskLevel)}`}
                      >
                        {scoreData.riskLevel === "low"
                          ? "Low"
                          : scoreData.riskLevel === "moderate"
                            ? "Moderate"
                            : "High"}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">--</span>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    <Link
                      to={`/members/${member.id}/records/new`}
                      className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800 transition-colors"
                    >
                      <Plus className="h-3 w-3" />
                      Record
                    </Link>
                    <Link
                      to={`/members/${member.id}/ai`}
                      className="inline-flex items-center gap-1 text-xs font-medium text-violet-600 hover:text-violet-800 transition-colors"
                    >
                      <Sparkles className="h-3 w-3" />
                      AI
                    </Link>
                    <Link
                      to={`/members/${member.id}`}
                      className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <ArrowRight className="h-3 w-3" />
                      View
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <QuickAddRecordDialog open={quickAddOpen} onOpenChange={setQuickAddOpen} members={members} />
    </div>
  );
}

/* ── Skeleton ── */

export function DashboardSkeleton() {
  return (
    <div className="space-y-5 max-w-[1600px] mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <Skeleton className="h-7 w-48 mb-2" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-9 w-32 rounded-xl" />
      </div>
      <Skeleton className="h-10 w-full rounded-xl" />
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-44 rounded-xl" />
        ))}
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-5">
          <div className="grid gap-5 md:grid-cols-2">
            {[1, 2].map((i) => (
              <Card key={i}>
                <CardContent className="py-8">
                  <Skeleton className="h-48 w-full" />
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardContent className="py-8">
              <Skeleton className="h-40 w-full" />
            </CardContent>
          </Card>
        </div>
        <div className="space-y-5">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-5 w-32" />
              </CardHeader>
              <CardContent className="space-y-2">
                {[1, 2, 3].map((j) => (
                  <Skeleton key={j} className="h-12 w-full rounded-lg" />
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
