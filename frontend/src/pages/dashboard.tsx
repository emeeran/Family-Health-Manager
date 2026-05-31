import useSWR from "swr";
import { useNavigate } from "react-router-dom";
import { getDashboardSummary } from "@/lib/api/dashboard";
import { DashboardContent, DashboardSkeleton } from "@/components/content/dashboard-content";
import { UniversalQuickEntry } from "@/components/records/universal-quick-entry";
import { useEffect, useMemo } from "react";
import type { FamilyMemberResponse } from "@/lib/types/member";
import type { HealthRecordResponse } from "@/lib/types/health-record";

export default function DashboardPage() {
  const navigate = useNavigate();
  const { data: summary, error } = useSWR("dashboard", () => getDashboardSummary(), {
    revalidateOnFocus: false,
    dedupingInterval: 30_000,
  });

  useEffect(() => {
    if (
      error?.message === "Not authenticated" ||
      (error && "status" in error && (error as { status: number }).status === 401)
    ) {
      navigate("/login");
    }
  }, [error, navigate]);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <p className="text-lg font-semibold text-destructive mb-2">Failed to load dashboard</p>
        <p className="text-sm text-muted-foreground mb-4">{error.message}</p>
        <button
          onClick={() => navigate("/login")}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Log in again
        </button>
      </div>
    );
  }

  if (!summary) return <DashboardSkeleton />;

  // Redirect to onboarding if no members
  if (!summary.members || summary.members.length === 0) {
    navigate("/onboarding");
    return null;
  }

  // Derive stats from summary — single API call replaces 7 separate calls
  const members = summary.members as unknown as FamilyMemberResponse[];
  const records = (summary.recent_records || []) as unknown as HealthRecordResponse[];

  return (
    <>
      <DashboardContent
        members={members}
        householdName={summary.household_name || "My Family"}
        stats={{
          providersCount: summary.providers_count || 0,
          conversationsCount: summary.conversations_count || 0,
          unreadNotifications: summary.unread_notifications || 0,
          upcomingReminders: summary.upcoming_reminders || [],
        }}
        records={records}
      />
      <UniversalQuickEntry members={members} />
    </>
  );
}
