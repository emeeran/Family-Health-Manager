import React, { useState, useMemo, useEffect, Suspense } from "react";
import { Link } from "react-router-dom";
import {
  Users,
  Stethoscope,
  CalendarClock,
  Plus,
  UserPlus,
  Activity,
  FileText,
  Bell,
  AlertTriangle,
  ChevronRight,
  ShieldCheck,
  TrendingUp,
  Clock,
  Sparkles,
  Syringe,
  ArrowRight,
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
import { ReportGenerator } from "@/components/shared/report-generator";
import { AlertsFeed } from "@/components/dashboard/alerts-feed";
import { MedicationSummaryWidget } from "@/components/dashboard/medication-summary";
import { FamilyComparisonChart } from "@/components/dashboard/family-comparison-chart";
import { useDashboardSummary } from "@/hooks/use-dashboard";
import { dismissHealthAlert } from "@/lib/api/health-alerts";
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

function memberAge(dob: string | null | undefined): string | null {
  if (!dob) return null;
  const d = new Date(dob);
  const now = new Date();
  let age = now.getFullYear() - d.getFullYear();
  const m = now.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) age--;
  return age >= 0 ? `${age}y` : null;
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
        <span className="text-[8px] text-muted-foreground">/100</span>
      </div>
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

  const { summary, isLoading: summaryLoading, mutate: mutateSummary } = useDashboardSummary();

  const [memberScores, setMemberScores] = useState<
    Record<string, { score: number; medications: number; conditions: number; riskLevel: string }>
  >({});
  const [scoresLoading, setScoresLoading] = useState(true);

  useEffect(() => {
    if (summary?.scores?.length) {
      const map: Record<
        string,
        { score: number; medications: number; conditions: number; riskLevel: string }
      > = {};
      for (const s of summary.scores) {
        map[s.member_id] = {
          score: s.health_score,
          medications: s.active_medications_count || 0,
          conditions: 0,
          riskLevel: s.risk_level || "low",
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
              },
            }))
            .catch(() => ({
              id: m.id,
              data: { score: 0, medications: 0, conditions: 0, riskLevel: "low" },
            }))
        )
      ).then((results) => {
        const map: Record<
          string,
          { score: number; medications: number; conditions: number; riskLevel: string }
        > = {};
        for (const r of results) map[r.id] = r.data;
        setMemberScores(map);
        setScoresLoading(false);
      });
    } else if (!summaryLoading) {
      setScoresLoading(false);
    }
  }, [summary, summaryLoading, activeMembers]);

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

  const recentActivity = useMemo(
    () =>
      activeRecords
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
        .slice(0, 5),
    [activeRecords]
  );

  const memberRecordCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of activeRecords)
      counts[r.family_member_id] = (counts[r.family_member_id] || 0) + 1;
    return counts;
  }, [activeRecords]);

  const familyStats = useMemo(() => {
    const vals = Object.values(memberScores);
    const avgScore = vals.length
      ? Math.round(vals.reduce((s, d) => s + d.score, 0) / vals.length)
      : 0;
    const totalMeds = vals.reduce((s, d) => s + d.medications, 0);
    return { avgScore, totalMeds };
  }, [memberScores]);

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

  const [alerts, setAlerts] = useState<DashboardAlert[]>([]);
  useEffect(() => {
    if (summary?.alerts) setAlerts(summary.alerts);
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

  const vacStatus = summary?.vaccination_status;

  return (
    <div className="space-y-4 max-w-[1400px] mx-auto">
      {/* ═══ HEADER ═══ */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">{householdName}</h1>
          <p className="text-sm text-muted-foreground">Family health overview</p>
        </div>
        <div className="flex items-center gap-2">
          {stats.unreadNotifications > 0 && (
            <Link
              to="/notifications"
              className="inline-flex items-center gap-1.5 rounded-lg border px-3 h-8 text-sm hover:bg-muted/50 transition-colors"
            >
              <Bell className="h-3.5 w-3.5" />
              <span>{stats.unreadNotifications}</span>
            </Link>
          )}
          <Link
            to="/members/new"
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary text-primary-foreground px-3.5 h-8 text-sm font-semibold hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Member
          </Link>
        </div>
      </div>

      {/* ═══ STAT CARDS ROW ═══ */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
        <Card className="shadow-none">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground font-medium">Members</p>
              <Users className="h-4 w-4 text-muted-foreground/40" />
            </div>
            <p className="text-2xl font-bold mt-1">{activeCount}</p>
          </CardContent>
        </Card>
        <Card className="shadow-none">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground font-medium">Records</p>
              <FileText className="h-4 w-4 text-muted-foreground/40" />
            </div>
            <p className="text-2xl font-bold mt-1">{activeRecords.length}</p>
          </CardContent>
        </Card>
        <Card className="shadow-none">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground font-medium">Providers</p>
              <Stethoscope className="h-4 w-4 text-muted-foreground/40" />
            </div>
            <p className="text-2xl font-bold mt-1">{stats.providersCount}</p>
          </CardContent>
        </Card>
        <Card className="shadow-none">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground font-medium">Avg Score</p>
              <Activity className="h-4 w-4 text-muted-foreground/40" />
            </div>
            <p
              className="text-2xl font-bold mt-1"
              style={{ color: scoreColor(familyStats.avgScore) }}
            >
              {!scoresLoading && familyStats.avgScore > 0 ? familyStats.avgScore : "--"}
            </p>
          </CardContent>
        </Card>
        {vacStatus && vacStatus.total_vaccinations > 0 && (
          <Card className="shadow-none">
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground font-medium">Vaccines</p>
                <Syringe className="h-4 w-4 text-muted-foreground/40" />
              </div>
              <p className="text-2xl font-bold mt-1">{vacStatus.total_vaccinations}</p>
              {vacStatus.overdue_count > 0 && (
                <p className="text-[10px] text-amber-600 font-medium">
                  {vacStatus.overdue_count} overdue
                </p>
              )}
            </CardContent>
          </Card>
        )}
        {summary?.risk_summary &&
          (summary.risk_summary.high_risk_members > 0 ||
            summary.risk_summary.moderate_risk_members > 0) && (
            <Card className="shadow-none border-red-200 bg-red-50/50">
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs text-red-600 font-medium">Risk Alerts</p>
                  <AlertTriangle className="h-4 w-4 text-red-400" />
                </div>
                <p className="text-2xl font-bold mt-1 text-red-700">
                  {summary.risk_summary.high_risk_members +
                    summary.risk_summary.moderate_risk_members}
                </p>
              </CardContent>
            </Card>
          )}
      </div>

      {/* ═══ QUICK LOG ═══ */}
      {activeMembers.length > 0 && (
        <Card className="shadow-none">
          <CardContent className="py-2.5 px-4">
            {quickLogMemberId ? (
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setQuickLogMemberId(null)}
                  className="text-xs font-medium text-muted-foreground hover:text-foreground shrink-0 underline underline-offset-2"
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
                <span className="text-xs text-muted-foreground font-medium">Quick log:</span>
                {activeMembers.slice(0, 5).map((m) => (
                  <button
                    key={m.id}
                    onClick={() => setQuickLogMemberId(m.id)}
                    className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-semibold hover:bg-primary hover:text-primary-foreground transition-colors"
                  >
                    {m.first_name}
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ═══ ALERTS ═══ */}
      {alerts.length > 0 && <AlertsFeed alerts={alerts} onDismiss={handleDismissAlert} />}

      {/* ═══ MAIN GRID: Content + Sidebar ═══ */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Left: Family + Charts */}
        <div className="lg:col-span-2 space-y-4">
          {/* Family Health Cards */}
          <div>
            <h2 className="text-sm font-semibold mb-3">Family Health</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {activeMembers.map((member) => {
                const scoreData = memberScores[member.id];
                const fullName = `${member.first_name} ${member.last_name}`;
                const recCount = memberRecordCounts[member.id] || 0;
                const age = memberAge(member.date_of_birth);
                const riskLevel = scoreData?.riskLevel;
                const isHighRisk = riskLevel === "high" || riskLevel === "moderate";

                return (
                  <Link
                    key={member.id}
                    to={`/members/${member.id}`}
                    className="group rounded-lg border bg-card p-3.5 hover:shadow-md transition-all"
                  >
                    <div className="flex items-center gap-3">
                      {scoresLoading ? (
                        <Skeleton className="h-[56px] w-[56px] rounded-full shrink-0" />
                      ) : scoreData ? (
                        <HealthScoreRing
                          score={scoreData.score}
                          size={56}
                          riskLevel={scoreData.riskLevel}
                        />
                      ) : (
                        <div className="flex h-[56px] w-[56px] items-center justify-center rounded-full bg-muted/50 shrink-0">
                          <span className="text-sm font-bold text-muted-foreground">--</span>
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <p className="text-sm font-semibold truncate">{fullName}</p>
                          {isHighRisk && (
                            <span
                              className={`inline-block h-1.5 w-1.5 rounded-full ${riskLevel === "high" ? "bg-red-500" : "bg-amber-500"}`}
                            />
                          )}
                        </div>
                        <div className="flex items-center gap-1.5 mt-0.5 text-[11px] text-muted-foreground">
                          <span>{RELATIONSHIP_LABELS[member.relationship]}</span>
                          {age && (
                            <>
                              <span className="opacity-30">·</span>
                              <span>{age}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                    {/* Detail chips */}
                    <div className="flex items-center gap-1.5 mt-2.5 flex-wrap">
                      {member.blood_group && (
                        <span className="text-[10px] font-semibold text-red-600 bg-red-50 px-1.5 py-0.5 rounded">
                          {member.blood_group}
                        </span>
                      )}
                      {member.bmi && (
                        <span className="text-[10px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
                          BMI {member.bmi.toFixed(1)}
                        </span>
                      )}
                      {recCount > 0 && (
                        <span className="text-[10px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
                          {recCount} recs
                        </span>
                      )}
                      {scoreData && scoreData.medications > 0 && (
                        <span className="text-[10px] text-violet-600 bg-violet-50 px-1.5 py-0.5 rounded">
                          {scoreData.medications} meds
                        </span>
                      )}
                      {member.allergies && member.allergies.length > 0 && (
                        <span className="text-[10px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                          {member.allergies.length} allerg
                          {member.allergies.length !== 1 ? "ies" : "y"}
                        </span>
                      )}
                    </div>
                  </Link>
                );
              })}
              {/* Add member */}
              <Link
                to="/members/new"
                className="flex items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border/50 py-8 hover:border-primary/30 transition-colors group"
              >
                <Plus className="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
                <span className="text-sm font-medium text-muted-foreground group-hover:text-foreground transition-colors">
                  Add Member
                </span>
              </Link>
            </div>
          </div>

          {/* Charts Row */}
          <div className="grid gap-4 md:grid-cols-2">
            {(numericRecords.length > 0 || activeRecords.length > 0) && (
              <Suspense
                fallback={
                  <Card className="shadow-none">
                    <CardContent className="py-8">
                      <Skeleton className="h-48 w-full" />
                    </CardContent>
                  </Card>
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
            {summary?.scores && summary.scores.length >= 2 && (
              <FamilyComparisonChart scores={summary.scores} />
            )}
          </div>

          {/* HbA1c Trend */}
          {hba1cChartRows.length >= 2 && (
            <Card className="shadow-none">
              <CardHeader className="pb-2 pt-4 px-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold">HbA1c Trend</CardTitle>
                  {hba1cData.length > 0 &&
                    (() => {
                      const latest = hba1cData[hba1cData.length - 1].value;
                      const cat =
                        latest < 5.7 ? "Normal" : latest < 6.5 ? "Prediabetes" : "Diabetes";
                      return (
                        <Badge
                          variant="secondary"
                          className={`text-xs px-2 py-0.5 font-semibold ${HBA1C_CATEGORY_COLORS[cat] ?? ""}`}
                        >
                          {latest}% — {cat}
                        </Badge>
                      );
                    })()}
                </div>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                <Hba1cModernChart rows={hba1cChartRows} members={hba1cMembers} />
              </CardContent>
            </Card>
          )}

          {/* Preventive Care */}
          {summary?.preventive_care && summary.preventive_care.length > 0 && (
            <Card className="shadow-none">
              <CardHeader className="pb-2 pt-4 px-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-emerald-500" />
                    Preventive Care
                  </CardTitle>
                  <Badge className="text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 px-1.5">
                    {summary.preventive_care.length}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                <div className="space-y-1.5">
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
                          <p className="text-xs font-medium truncate">{item.recommendation}</p>
                          <p className="text-[10px] text-muted-foreground">{item.member_name}</p>
                        </div>
                        <Badge
                          className={`text-[10px] font-semibold border ${statusColors[item.due_status] || ""}`}
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
                    <p className="text-[10px] text-muted-foreground text-center pt-1">
                      +{summary.preventive_care.length - 5} more
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* ═══ RIGHT SIDEBAR ═══ */}
        <div className="space-y-4">
          {/* Quick Actions */}
          <Card className="shadow-none">
            <CardContent className="pt-4 pb-3 space-y-0.5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                Quick Actions
              </p>
              <Link
                to="/members/new"
                className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-muted/50 transition-colors group"
              >
                <UserPlus className="h-4 w-4 text-blue-500" />
                <span className="text-sm font-medium flex-1">Add Member</span>
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/30 group-hover:text-foreground transition-colors" />
              </Link>
              <Link
                to="/providers/new"
                className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-muted/50 transition-colors group"
              >
                <Stethoscope className="h-4 w-4 text-emerald-500" />
                <span className="text-sm font-medium flex-1">Add Provider</span>
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/30 group-hover:text-foreground transition-colors" />
              </Link>
              <Link
                to="/reminders/new"
                className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-muted/50 transition-colors group"
              >
                <CalendarClock className="h-4 w-4 text-amber-500" />
                <span className="text-sm font-medium flex-1">New Reminder</span>
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/30 group-hover:text-foreground transition-colors" />
              </Link>
              <button
                onClick={() => setQuickAddOpen(true)}
                className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-muted/50 transition-colors group w-full text-left"
              >
                <Plus className="h-4 w-4 text-teal-500" />
                <span className="text-sm font-medium flex-1">Add Record</span>
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/30 group-hover:text-foreground transition-colors" />
              </button>
              <div className="px-2 py-1.5">
                <ReportGenerator variant="ghost" />
              </div>
            </CardContent>
          </Card>

          {/* Medications */}
          {summary?.medication_summary &&
            summary.medication_summary.total_active_medications > 0 && (
              <MedicationSummaryWidget
                summary={summary.medication_summary}
                memberNames={memberNames}
              />
            )}

          {/* Reminders */}
          <Card className="shadow-none">
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-semibold flex items-center gap-2">
                  <Clock className="h-4 w-4 text-amber-500" />
                  Reminders
                </p>
                <Link
                  to="/reminders"
                  className="text-xs font-medium text-primary hover:underline underline-offset-2"
                >
                  View all
                </Link>
              </div>
              {stats.upcomingReminders.length === 0 ? (
                <div className="flex items-center gap-2 py-4 text-muted-foreground">
                  <CalendarClock className="h-5 w-5 text-muted-foreground/20" />
                  <p className="text-xs">No upcoming reminders</p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  {stats.upcomingReminders.slice(0, 4).map((reminder) => {
                    const isOverdue = new Date(reminder.start_datetime) < new Date();
                    const memberName = reminder.family_member_id
                      ? memberNames[reminder.family_member_id]
                      : null;
                    return (
                      <Link
                        key={reminder.id}
                        to="/reminders"
                        className={`flex items-center justify-between rounded-lg px-2.5 py-2 transition-colors border ${isOverdue ? "bg-red-50/50 border-red-200" : "border-transparent hover:bg-muted/50"}`}
                      >
                        <div className="min-w-0">
                          <p className="text-xs font-semibold truncate">{reminder.title}</p>
                          <p className="text-[10px] text-muted-foreground mt-0.5">
                            {formatRelativeTime(reminder.start_datetime)}
                            {memberName && <span className="ml-1">— {memberName}</span>}
                          </p>
                        </div>
                        {isOverdue && (
                          <span className="text-[10px] font-bold text-red-700 bg-red-100 px-1.5 py-0.5 rounded border border-red-200 shrink-0">
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
            <Card className="shadow-none">
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm font-semibold">Recent</p>
                  <Link
                    to="/records"
                    className="text-xs font-medium text-primary hover:underline underline-offset-2"
                  >
                    View all
                  </Link>
                </div>
                <div className="space-y-0.5">
                  {recentActivity.map((record) => {
                    const preview = extractPreview(record.clinical_data, record.diagnosis);
                    return (
                      <button
                        key={record.id}
                        onClick={() => openQuickView(record.id, record.family_member_id)}
                        className="flex items-center justify-between rounded-lg px-2.5 py-2 hover:bg-muted/50 transition-colors w-full text-left"
                      >
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          <Badge
                            variant="outline"
                            className="text-[10px] shrink-0 px-1.5 py-0 font-semibold"
                          >
                            {(RECORD_TYPE_LABELS as Record<string, string>)[record.record_type] ||
                              record.record_type}
                          </Badge>
                          <div className="min-w-0">
                            <p className="text-xs font-medium truncate">
                              {memberNames[record.family_member_id] || "Unknown"}
                            </p>
                            {preview && (
                              <p className="text-[10px] text-muted-foreground truncate">
                                {preview}
                              </p>
                            )}
                          </div>
                        </div>
                        <span className="text-[10px] text-muted-foreground shrink-0 ml-2">
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

      <QuickAddRecordDialog open={quickAddOpen} onOpenChange={setQuickAddOpen} members={members} />
    </div>
  );
}

/* ── Skeleton ── */

export function DashboardSkeleton() {
  return (
    <div className="space-y-4 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <Skeleton className="h-6 w-48 mb-2" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-8 w-32 rounded-lg" />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} className="shadow-none">
            <CardContent className="py-4">
              <Skeleton className="h-10 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-36 rounded-lg" />
            ))}
          </div>
        </div>
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="shadow-none">
              <CardContent className="py-4">
                <Skeleton className="h-32 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
