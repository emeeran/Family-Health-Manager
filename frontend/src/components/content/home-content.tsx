import React, { memo, useState, useMemo, useCallback, useEffect, Suspense } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { SmartEntryBar } from "@/components/records/smart-entry";
import { AlertStrip } from "@/components/home/alert-strip";
import { ActivityFeed } from "@/components/home/activity-feed";
import { FamilyStrip } from "@/components/home/family-strip";
import { useDashboardSummary } from "@/hooks/use-dashboard";
import { dismissHealthAlert } from "@/lib/api/health-alerts";
import { toast } from "sonner";
import type { DashboardAlert } from "@/lib/types/dashboard";
import type { FamilyMemberResponse } from "@/lib/types/member";
import type { HealthRecordResponse } from "@/lib/types/health-record";

interface DashboardReminder {
  id: string;
  title: string;
  start_datetime: string | null;
  reminder_type: string;
  family_member_id: string | null;
}

interface DashboardStats {
  providersCount: number;
  conversationsCount: number;
  unreadNotifications: number;
  upcomingReminders: DashboardReminder[];
}

interface HomeContentProps {
  members: FamilyMemberResponse[];
  householdName: string;
  stats: DashboardStats;
  records: HealthRecordResponse[];
}

export const HomeContent = memo(function HomeContent({
  members,
  householdName,
  stats,
  records,
}: HomeContentProps) {
  const { summary, isLoading: summaryLoading, mutate: mutateSummary } = useDashboardSummary();
  const activeMembers = useMemo(() => members.filter((m) => m.is_active), [members]);

  const [alerts, setAlerts] = useState<DashboardAlert[]>([]);
  useEffect(() => {
    if (summary?.alerts) setAlerts(summary.alerts);
  }, [summary]);

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

  const activeRecords = useMemo(() => records.filter((r) => !r.is_deleted), [records]);

  return (
    <div className="space-y-4 max-w-3xl mx-auto">
      {/* Greeting */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">{householdName}</h1>
          <p className="text-sm text-muted-foreground">
            {activeMembers.length} member{activeMembers.length !== 1 ? "s" : ""} &middot;{" "}
            {activeRecords.length} record{activeRecords.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link
          to="/people/new"
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary text-primary-foreground px-3.5 h-8 text-sm font-semibold hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          Add Member
        </Link>
      </div>

      {/* Smart Entry Bar */}
      <SmartEntryBar members={members} />

      {/* Alert Strip */}
      {alerts.length > 0 && <AlertStrip alerts={alerts} onDismiss={handleDismissAlert} />}

      {/* Family Strip */}
      {activeMembers.length > 0 && <FamilyStrip members={activeMembers} />}

      {/* Activity Feed */}
      <ActivityFeed
        records={activeRecords.slice(0, 10)}
        memberNames={memberNames}
        upcomingReminders={stats.upcomingReminders}
      />

      {/* Contextual Section */}
      {summary && (
        <ContextualSection
          summary={summary}
          memberNames={memberNames}
          activeRecords={activeRecords}
        />
      )}
    </div>
  );
});

/* ── Contextual Section: picks most relevant 2 cards ── */
function ContextualSection({
  summary,
  memberNames,
  activeRecords,
}: {
  summary: NonNullable<ReturnType<typeof useDashboardSummary>["summary"]>;
  memberNames: Record<string, string>;
  activeRecords: HealthRecordResponse[];
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
    <div className="space-y-4 max-w-3xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <Skeleton className="h-5 w-36 mb-2" />
          <Skeleton className="h-4 w-52" />
        </div>
        <Skeleton className="h-8 w-28 rounded-lg" />
      </div>
      <Skeleton className="h-12 w-full rounded-lg" />
      <Skeleton className="h-40 w-full rounded-lg" />
      <Skeleton className="h-32 w-full rounded-lg" />
    </div>
  );
}
