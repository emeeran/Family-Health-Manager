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
  X,
  ChevronRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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
import { listHealthAlerts, dismissHealthAlert } from "@/lib/api/health-alerts";
import { toast } from "sonner";

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
import type { HealthAlertResponse } from "@/lib/types/health-alert";

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

/* ── Health Score Ring ── */

function HealthScoreRing({
  score,
  size = 72,
  strokeWidth = 5,
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
        <span className="font-bold leading-none" style={{ color, fontSize: size * 0.26 }}>
          {score}
        </span>
        <span className="text-[9px] text-muted-foreground">/100</span>
      </div>
    </div>
  );
}

/* ── Alert Strip ── */

function AlertStrip({
  alerts,
  memberNames,
  onDismiss,
}: {
  alerts: HealthAlertResponse[];
  memberNames: Record<string, string>;
  onDismiss: (id: string) => void;
}) {
  if (alerts.length === 0) return null;

  const shown = alerts
    .filter((a) => a.severity === "critical" || a.severity === "warning")
    .slice(0, 3);
  if (shown.length === 0) return null;

  return (
    <div className="flex gap-3 overflow-x-auto pb-1">
      {shown.map((alert) => {
        const isCritical = alert.severity === "critical";
        const borderColor = isCritical ? "border-l-red-500" : "border-l-amber-500";
        const bgColor = isCritical
          ? "bg-red-50 dark:bg-red-950/20"
          : "bg-amber-50 dark:bg-amber-950/20";
        const memberName = memberNames[alert.family_member_id] || "Unknown";
        return (
          <div
            key={alert.id}
            className={`flex items-start gap-3 rounded-xl border-l-4 ${borderColor} ${bgColor} px-4 py-3 min-w-[280px] max-w-[380px] shrink-0`}
          >
            <AlertTriangle
              className={`h-4 w-4 mt-0.5 shrink-0 ${isCritical ? "text-red-500" : "text-amber-500"}`}
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold truncate">{alert.title}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {memberName}
                {alert.test_name && (
                  <span>
                    {" "}
                    · {alert.test_name}: {alert.value} (ref: {alert.reference})
                  </span>
                )}
              </p>
            </div>
            <button
              onClick={() => onDismiss(alert.id)}
              className="shrink-0 text-muted-foreground/50 hover:text-foreground transition-colors"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
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

/* ── Score data type ── */
interface ScoreData {
  score: number;
  medications: number;
  conditions: number;
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

  const [memberScores, setMemberScores] = useState<Record<string, ScoreData>>({});
  const [scoresLoading, setScoresLoading] = useState(true);
  const [healthAlerts, setHealthAlerts] = useState<HealthAlertResponse[]>([]);

  // Fetch health scores + alerts
  useEffect(() => {
    if (!activeMembers.length) {
      setScoresLoading(false);
      return;
    }
    if (!activeMembers.length) {
      setScoresLoading(false);
      return;
    }
    setScoresLoading(true);
    Promise.all([
      Promise.all(
        activeMembers.map((m) =>
          getMemberDashboard(m.id)
            .then((d) => ({
              id: m.id,
              data: {
                score: d.health_score,
                medications: d.active_medications_count,
                conditions: d.active_conditions_count,
              } as ScoreData,
            }))
            .catch(() => ({
              id: m.id,
              data: { score: 0, medications: 0, conditions: 0 } as ScoreData,
            }))
        )
      ),
      listHealthAlerts({ dismissed: false }).catch(() => []),
    ]).then(([scoreResults, alerts]) => {
      const map: Record<string, ScoreData> = {};
      for (const r of scoreResults) map[r.id] = r.data;
      setMemberScores(map);
      setHealthAlerts(alerts);
      setScoresLoading(false);
    });
  }, [activeMembers]);

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
      .slice(0, 5);
  }, [activeRecords]);

  const recordsThisMonth = useMemo(() => {
    const now = new Date();
    const thisMonth = now.getFullYear() * 12 + now.getMonth();
    return activeRecords.filter((r) => {
      const m = new Date(r.created_at).getFullYear() * 12 + new Date(r.created_at).getMonth();
      return m === thisMonth;
    }).length;
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

  async function handleDismissAlert(alertId: string) {
    try {
      await dismissHealthAlert(alertId);
      setHealthAlerts((prev) => prev.filter((a) => a.id !== alertId));
      toast.success("Alert dismissed");
    } catch {
      toast.error("Failed to dismiss alert");
    }
  }

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      {/* SECTION 1: Hero Bar */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{householdName}</h1>
          <div className="flex items-center gap-3 text-base text-foreground mt-1">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 font-medium">
              <Users className="h-4 w-4 text-muted-foreground" />
              {activeCount} member{activeCount !== 1 ? "s" : ""}
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 font-medium">
              <Stethoscope className="h-4 w-4 text-muted-foreground" />
              {stats.providersCount} provider{stats.providersCount !== 1 ? "s" : ""}
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 font-medium">
              <FileText className="h-4 w-4 text-muted-foreground" />
              {activeRecords.length} record{activeRecords.length !== 1 ? "s" : ""}
            </span>
            {recordsThisMonth > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 text-emerald-800 px-3 py-1 font-semibold">
                {recordsThisMonth} this month
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {healthAlerts.filter((a) => a.severity === "critical").length > 0 && (
            <Link
              to="/health-alerts"
              className="inline-flex items-center gap-2 rounded-lg border-2 border-red-300 bg-red-50 px-3 h-10 text-sm font-semibold text-red-700 hover:bg-red-100 transition-colors"
            >
              <AlertTriangle className="h-4 w-4" />
              {healthAlerts.filter((a) => a.severity === "critical").length} alert
              {healthAlerts.filter((a) => a.severity === "critical").length !== 1 ? "s" : ""}
            </Link>
          )}
          {stats.unreadNotifications > 0 && (
            <Link
              to="/notifications"
              className="inline-flex items-center gap-2 rounded-lg border-2 border-primary/30 px-3 h-10 text-base font-medium hover:bg-muted/50 transition-colors"
            >
              <Bell className="h-5 w-5" />
              <span>{stats.unreadNotifications} new</span>
            </Link>
          )}
          <Link
            to="/members/new"
            className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-(--brand-accent) to-(--brand-primary) px-4 h-10 text-base font-semibold text-white hover:opacity-90 transition-opacity shadow-md"
          >
            <Plus className="h-5 w-5" />
            Add Member
          </Link>
        </div>
      </div>

      {/* Quick Log */}
      {activeMembers.length > 0 && (
        <div className="rounded-xl border-2 px-4 py-3">
          {quickLogMemberId ? (
            <div className="flex items-center gap-3">
              <button
                onClick={() => setQuickLogMemberId(null)}
                className="text-sm font-medium text-foreground hover:text-primary shrink-0 underline underline-offset-2"
              >
                Change member
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
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm text-foreground font-semibold">Quick log for:</span>
              {activeMembers.slice(0, 5).map((m) => (
                <button
                  key={m.id}
                  onClick={() => setQuickLogMemberId(m.id)}
                  className="inline-flex items-center gap-1.5 rounded-full border-2 px-4 py-2 text-sm font-semibold hover:bg-primary hover:text-primary-foreground transition-colors focus:ring-2 focus:ring-primary focus:ring-offset-2"
                >
                  {m.first_name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* SECTION 2: Alert Strip */}
      <AlertStrip alerts={healthAlerts} memberNames={memberNames} onDismiss={handleDismissAlert} />

      {/* SECTION 3: Family Health Rings */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold">Family Health</h2>
          {!scoresLoading && familyStats.avgScore > 0 && (
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <span>
                Avg Score: <strong className="text-foreground">{familyStats.avgScore}</strong>
              </span>
              <span>·</span>
              <span>{familyStats.totalMedications} medications</span>
              <span>·</span>
              <span>{familyStats.totalConditions} conditions</span>
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {activeMembers.map((member) => {
            const scoreData = memberScores[member.id];
            const fullName = `${member.first_name} ${member.last_name}`;
            const recCount = memberRecordCounts[member.id] || 0;

            return (
              <Link
                key={member.id}
                to={`/members/${member.id}`}
                className="group flex flex-col items-center gap-2 rounded-xl border-2 bg-card p-5 hover:shadow-lg hover:-translate-y-0.5 transition-all"
              >
                {scoresLoading ? (
                  <Skeleton className="h-[72px] w-[72px] rounded-full" />
                ) : scoreData ? (
                  <HealthScoreRing score={scoreData.score} size={72} />
                ) : (
                  <div className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-muted/50">
                    <span className="text-lg font-bold text-muted-foreground">--</span>
                  </div>
                )}
                <div className="text-center">
                  <p className="text-sm font-bold truncate max-w-full">{fullName}</p>
                  <Badge variant="outline" className="text-xs mt-1 px-1.5 py-0.5 font-medium">
                    {RELATIONSHIP_LABELS[member.relationship]}
                  </Badge>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  {member.bmi && <span>BMI {member.bmi.toFixed(1)}</span>}
                  {member.bmi && recCount > 0 && <span>·</span>}
                  {recCount > 0 && (
                    <span>
                      {recCount} rec{recCount !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </Link>
            );
          })}
          {/* Add Member card */}
          <Link
            to="/members/new"
            className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border/60 bg-card/50 p-5 hover:shadow-md hover:border-primary/30 transition-all group"
          >
            <div className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-muted/50 group-hover:bg-primary/10 transition-colors">
              <Plus className="h-6 w-6 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
            <p className="text-sm font-semibold text-muted-foreground group-hover:text-foreground transition-colors">
              Add Member
            </p>
          </Link>
        </div>
      </div>

      {/* SECTION 4: Charts + Sidebar */}
      <div className="grid gap-5 lg:grid-cols-3">
        {/* Left: Charts */}
        <div className="lg:col-span-2 space-y-5">
          {(numericRecords.length > 0 || activeRecords.length > 0) && (
            <Suspense
              fallback={
                <div className="grid gap-5 md:grid-cols-2">
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
                </div>
              }
            >
              <div className="grid gap-5 md:grid-cols-2">
                {numericRecords.length > 0 && (
                  <HealthTrendsChart records={numericRecords} memberNames={memberNames} />
                )}
                {activeRecords.length > 0 && <RecordTypeChart records={activeRecords} />}
              </div>
            </Suspense>
          )}

          {/* HbA1c Trend */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Heart className="h-5 w-5 text-red-500" />
                  HbA1c Trend
                </CardTitle>
                {hba1cData.length > 0 &&
                  (() => {
                    const latest = hba1cData[hba1cData.length - 1].value;
                    const cat = latest < 5.7 ? "Normal" : latest < 6.5 ? "Prediabetes" : "Diabetes";
                    return (
                      <Badge
                        variant="secondary"
                        className={`text-sm px-2.5 py-0.5 font-semibold ${HBA1C_CATEGORY_COLORS[cat] ?? ""}`}
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
        </div>

        {/* Right sidebar */}
        <div className="space-y-4">
          {/* Quick Actions — compact vertical */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold">Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              <Link
                to="/members/new"
                className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors group"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-500/15 text-blue-600">
                  <UserPlus className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold">Add Member</p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground/50 group-hover:text-foreground transition-colors" />
              </Link>
              <Link
                to="/providers/new"
                className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors group"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-600">
                  <Stethoscope className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold">Add Provider</p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground/50 group-hover:text-foreground transition-colors" />
              </Link>
              <Link
                to="/reminders/new"
                className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors group"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-500/15 text-amber-600">
                  <CalendarClock className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold">New Reminder</p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground/50 group-hover:text-foreground transition-colors" />
              </Link>
              <button
                onClick={() => setQuickAddOpen(true)}
                className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors group w-full text-left"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-500/15 text-teal-600">
                  <Plus className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold">Add Record</p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground/50 group-hover:text-foreground transition-colors" />
              </button>
            </CardContent>
          </Card>

          {/* Upcoming Reminders */}
          <Card className="overflow-hidden border-2">
            <div className="h-2 bg-gradient-to-r from-amber-400 via-orange-500 to-red-400" />
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-lg font-bold flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/15">
                  <CalendarClock className="h-5 w-5 text-amber-600" />
                </div>
                Reminders
                {stats.upcomingReminders.length > 0 && (
                  <Badge className="text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300">
                    {stats.upcomingReminders.length}
                  </Badge>
                )}
              </CardTitle>
              <Link
                to="/reminders"
                className="text-sm font-semibold text-primary hover:underline underline-offset-2"
              >
                View all
              </Link>
            </CardHeader>
            <CardContent>
              {stats.upcomingReminders.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-6 text-foreground/70">
                  <CalendarClock className="h-8 w-8 text-foreground/30" />
                  <p className="text-base font-medium">No upcoming reminders</p>
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
                        className={`flex items-center justify-between rounded-xl px-4 py-3 transition-colors ${isOverdue ? "bg-red-50 border-2 border-red-300 dark:bg-red-950/30 dark:border-red-700" : "bg-muted/40 border-2 border-transparent hover:border-muted"}`}
                      >
                        <div className="min-w-0">
                          <p className="text-base font-semibold truncate">{reminder.title}</p>
                          <p className="text-sm text-foreground/70 mt-0.5">
                            {formatRelativeTime(reminder.start_datetime)}
                            {memberName && (
                              <span className="ml-1 font-semibold">— {memberName}</span>
                            )}
                          </p>
                        </div>
                        {isOverdue && (
                          <span className="text-sm font-bold text-red-800 bg-red-200 px-2.5 py-1 rounded-lg shrink-0 border border-red-300">
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
            <Card className="overflow-hidden border-2">
              <div className="h-2 bg-gradient-to-r from-blue-400 via-violet-500 to-purple-500" />
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-lg font-bold flex items-center gap-2.5">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/15">
                    <Activity className="h-5 w-5 text-blue-600" />
                  </div>
                  Recent Activity
                </CardTitle>
                <Link
                  to="/records"
                  className="text-sm font-semibold text-primary hover:underline underline-offset-2"
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
                        className="flex items-center justify-between rounded-xl px-3 py-3 hover:bg-muted/50 transition-colors w-full text-left focus:ring-2 focus:ring-primary focus:ring-offset-1"
                      >
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          <Badge
                            variant="outline"
                            className="text-xs shrink-0 px-2.5 py-0.5 font-bold border-2"
                          >
                            {RECORD_TYPE_LABELS[record.record_type] || record.record_type}
                          </Badge>
                          <div className="min-w-0">
                            <p className="text-base font-semibold truncate">
                              {memberNames[record.family_member_id] || "Unknown"}
                            </p>
                            {preview && (
                              <p className="text-sm text-foreground/60 truncate">{preview}</p>
                            )}
                          </div>
                        </div>
                        <span className="text-sm text-foreground/60 shrink-0 ml-3 font-medium">
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

      {/* SECTION 5: Family Members — enhanced cards */}
      <div>
        <h2 className="text-xl font-bold mb-4">Family Members</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
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
              <Card
                key={member.id}
                className="group hover:shadow-lg hover:-translate-y-0.5 transition-all text-left overflow-hidden"
              >
                <div className="h-1.5 bg-gradient-to-r from-violet-500 to-blue-500 opacity-50 group-hover:opacity-100 transition-opacity" />
                <CardContent className="pt-4 pb-3 px-4">
                  <div className="flex items-start gap-3">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-violet-500/20 to-blue-500/20 text-violet-700 dark:text-violet-300 text-base font-bold shrink-0">
                      {initials}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <Link
                          to={`/members/${member.id}`}
                          className="text-base font-bold hover:text-primary transition-colors truncate"
                        >
                          {fullName}
                        </Link>
                        {scoreData && (
                          <span
                            className={`text-xs font-bold shrink-0 ml-2 ${scoreData.score >= 75 ? "text-green-600" : scoreData.score >= 50 ? "text-amber-600" : "text-red-600"}`}
                          >
                            {scoreData.score}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant="outline" className="text-xs px-1.5 py-0.5 font-semibold">
                          {RELATIONSHIP_LABELS[member.relationship]}
                        </Badge>
                        {member.blood_group && (
                          <span className="text-xs text-foreground/70 font-semibold">
                            {member.blood_group}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Stats row */}
                  <div className="flex flex-wrap items-center gap-1.5 mt-3">
                    {member.bmi && (
                      <span
                        className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold ${member.bmi_category ? BMI_CATEGORY_COLORS[member.bmi_category] || "bg-muted text-muted-foreground" : "bg-muted text-muted-foreground"}`}
                      >
                        <Activity className="h-3 w-3" />
                        BMI {member.bmi.toFixed(1)}
                      </span>
                    )}
                    {recCount > 0 && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-blue-500/10 px-2 py-0.5 text-[11px] font-semibold text-blue-600">
                        <FileText className="h-3 w-3" />
                        {recCount} rec{recCount !== 1 ? "s" : ""}
                      </span>
                    )}
                    {scoreData && scoreData.medications > 0 && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-violet-500/10 px-2 py-0.5 text-[11px] font-semibold text-violet-600">
                        <Pill className="h-3 w-3" />
                        {scoreData.medications} med{scoreData.medications !== 1 ? "s" : ""}
                      </span>
                    )}
                    {allergyCount > 0 && (
                      <span
                        className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold ${hasSevere ? "bg-red-500/10 text-red-600" : "bg-amber-500/10 text-amber-600"}`}
                      >
                        <AlertTriangle className="h-3 w-3" />
                        {allergyCount} allerg{allergyCount === 1 ? "y" : "ies"}
                      </span>
                    )}
                  </div>

                  {/* Quick links */}
                  <div className="flex gap-1.5 mt-3">
                    <Link
                      to={`/members/${member.id}/records/new`}
                      className="rounded-md px-3 py-1.5 text-sm font-semibold text-blue-600 hover:bg-blue-50 transition-colors border border-blue-200"
                    >
                      + Record
                    </Link>
                    <Link
                      to={`/members/${member.id}/ai`}
                      className="rounded-md px-3 py-1.5 text-sm font-semibold text-violet-600 hover:bg-violet-50 transition-colors border border-violet-200"
                    >
                      Ask AI
                    </Link>
                    <Link
                      to={`/members/${member.id}/timeline`}
                      className="rounded-md px-3 py-1.5 text-sm font-semibold text-emerald-600 hover:bg-emerald-50 transition-colors border border-emerald-200"
                    >
                      Timeline
                    </Link>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      <QuickAddRecordDialog open={quickAddOpen} onOpenChange={setQuickAddOpen} members={members} />
    </div>
  );
}

/* ── Skeleton ── */

export function DashboardSkeleton() {
  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <Skeleton className="h-8 w-48 mb-1" />
          <Skeleton className="h-6 w-64" />
        </div>
        <Skeleton className="h-10 w-32 rounded-lg" />
      </div>
      <Skeleton className="h-12 w-full rounded-xl" />
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
                  <Skeleton key={j} className="h-14 w-full rounded-lg" />
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
