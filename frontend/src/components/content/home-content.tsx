import React, { memo, useState, useMemo, useCallback, useEffect, Suspense } from "react";
import { Link } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";
import { SmartEntryBar } from "@/components/records/smart-entry";
import { AlertStrip } from "@/components/home/alert-strip";
import { ActivityFeed } from "@/components/home/activity-feed";
import { FamilyStrip } from "@/components/home/family-strip";
import { QuickActionsGrid } from "@/components/home/quick-actions-grid";
import { HealthOverviewCard } from "@/components/home/health-overview-card";
import { useDashboardSummary } from "@/hooks/use-dashboard";
import { dismissHealthAlert } from "@/lib/api/health-alerts";
import { toast } from "sonner";
import type { DashboardAlert, DashboardSummary } from "@/lib/types/dashboard";
import type { FamilyMemberResponse } from "@/lib/types/member";
import type { HealthRecordResponse } from "@/lib/types/health-record";

interface HomeContentProps {
  summary: DashboardSummary;
}

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function getCurrentDate() {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

export const HomeContent = memo(function HomeContent({ summary }: HomeContentProps) {
  const { summary: liveSummary, mutate: mutateSummary } = useDashboardSummary();
  const activeSummary = liveSummary || summary;

  // Derive members from summary (match FamilyMemberResponse shape)
  const members = useMemo<FamilyMemberResponse[]>(
    () =>
      activeSummary.members.map((m) => ({
        id: m.id,
        household_id: "",
        first_name: m.first_name,
        last_name: m.last_name,
        date_of_birth: m.date_of_birth,
        gender: m.gender as FamilyMemberResponse["gender"],
        relationship: m.relationship as FamilyMemberResponse["relationship"],
        medical_history_summary: null,
        blood_group: m.blood_group,
        family_history: null,
        height_cm: null,
        weight_kg: null,
        allergies: m.allergies ?? null,
        emergency_contact_name: null,
        emergency_contact_phone: null,
        notes: null,
        bmi: m.bmi,
        bmi_category: null,
        is_active: m.is_active,
        created_at: "",
      })),
    [activeSummary.members]
  );

  const activeMembers = useMemo(() => members.filter((m) => m.is_active), [members]);
  const householdName = activeSummary.household_name || "My Family";

  const records = useMemo<HealthRecordResponse[]>(
    () => (activeSummary.recent_records || []) as unknown as HealthRecordResponse[],
    [activeSummary.recent_records]
  );
  const activeRecords = useMemo(() => records.filter((r) => !r.is_deleted), [records]);

  const [alerts, setAlerts] = useState<DashboardAlert[]>([]);
  useEffect(() => {
    if (activeSummary?.alerts) setAlerts(activeSummary.alerts);
  }, [activeSummary]);

  const handleDismissAlert = useCallback(
    async (alertId: string) => {
      try {
        await dismissHealthAlert(alertId);
        setAlerts((prev) => prev.filter((a) => a.id !== alertId));
        toast.success("Alert dismissed");
        mutateSummary();
      } catch {
        toast.error("Failed to dismiss alert");
      }
    },
    [mutateSummary]
  );

  const memberNames = useMemo(() => {
    const names: Record<string, string> = {};
    for (const m of members) names[m.id] = `${m.first_name} ${m.last_name}`;
    return names;
  }, [members]);

  const upcomingReminders = useMemo(() => activeSummary.upcoming_reminders || [], [activeSummary]);

  return (
    <div className="space-y-4">
      {/* Zone A — Centered header + quick actions */}
      <div className="max-w-5xl mx-auto space-y-4">
        <div className="space-y-1">
          <h1 className="text-lg font-semibold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
            {getGreeting()}, {householdName}
          </h1>
          <p className="text-xs text-muted-foreground">
            {getCurrentDate()} &middot; {activeMembers.length} member
            {activeMembers.length !== 1 ? "s" : ""} &middot; {activeRecords.length} record
            {activeRecords.length !== 1 ? "s" : ""}
          </p>
        </div>

        <QuickActionsGrid members={activeMembers} />
      </div>

      {/* Smart entry — full width to match AI Tools chat input */}
      <SmartEntryBar members={members} />

      {/* Zone B — Two-column layout, centered */}
      <div className="max-w-5xl mx-auto grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* Left column — Primary content */}
        <div className="space-y-4 min-w-0">
          {alerts.length > 0 && <AlertStrip alerts={alerts} onDismiss={handleDismissAlert} />}
          <ActivityFeed
            records={activeRecords.slice(0, 10)}
            memberNames={memberNames}
            upcomingReminders={upcomingReminders}
          />
          {activeSummary && <ContextualSection summary={activeSummary} />}
        </div>

        {/* Right column — Insights sidebar */}
        <div className="space-y-4">
          {activeMembers.length > 0 && (
            <FamilyStrip members={activeMembers} scores={activeSummary.scores} />
          )}
          <HealthOverviewCard summary={activeSummary} />
        </div>
      </div>
    </div>
  );
});

/* ── Contextual Section: picks most relevant 2 cards ── */
function ContextualSection({
  summary,
}: {
  summary: NonNullable<ReturnType<typeof useDashboardSummary>["summary"]>;
}) {
  // Lazy-loaded chart components
  const FamilyComparisonChart = React.lazy(() =>
    import("@/components/dashboard/family-comparison-chart").then((mod) => ({
      default: mod.FamilyComparisonChart,
    }))
  );

  const cards: React.ReactNode[] = [];

  // Overdue reminders card
  if (summary.preventive_care && summary.preventive_care.length > 0) {
    const overdue = summary.preventive_care.filter((item) => item.due_status === "overdue");
    if (overdue.length > 0) {
      cards.push(
        <div key="preventive" className="rounded-lg border p-4 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">Preventive Care Overdue</p>
            <span className="text-[10px] font-bold text-red-700 bg-red-100 px-1.5 py-0.5 rounded border border-red-200">
              {overdue.length}
            </span>
          </div>
          <div className="space-y-1">
            {overdue.slice(0, 3).map((item, idx) => (
              <div key={idx} className="flex items-center justify-between text-xs">
                <span className="truncate">{item.recommendation}</span>
                <span className="text-muted-foreground shrink-0 ml-2">{item.member_name}</span>
              </div>
            ))}
          </div>
          <Link to="/people?tab=reminders" className="text-xs text-primary hover:underline">
            View all
          </Link>
        </div>
      );
    }
  }

  // Family comparison chart
  if (summary.scores && summary.scores.length >= 2) {
    cards.push(
      <Suspense key="comparison" fallback={<Skeleton className="h-48 rounded-lg" />}>
        <FamilyComparisonChart scores={summary.scores} />
      </Suspense>
    );
  }

  if (cards.length === 0) return null;

  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        Insights
      </p>
      <div className="grid gap-3 md:grid-cols-2">{cards.slice(0, 2)}</div>
    </div>
  );
}

/* ── Skeleton ── */

export function HomeSkeleton() {
  return (
    <div className="space-y-4 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <Skeleton className="h-5 w-36 mb-2" />
          <Skeleton className="h-4 w-52" />
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-12 w-full rounded-lg" />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <Skeleton className="h-48 w-full rounded-lg" />
        </div>
        <div className="space-y-4">
          <Skeleton className="h-24 w-full rounded-lg" />
          <Skeleton className="h-36 w-full rounded-lg" />
        </div>
      </div>
    </div>
  );
}
