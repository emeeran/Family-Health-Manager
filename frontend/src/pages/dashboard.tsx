import useSWR from "swr";
import { useNavigate } from "react-router-dom";
import { listMembers } from "@/lib/api/members";
import { getHousehold, listHouseholdRecords } from "@/lib/api/household";
import { listProviders } from "@/lib/api/providers";
import { listReminders } from "@/lib/api/reminders";
import { listNotifications } from "@/lib/api/notifications";
import { listConversations } from "@/lib/api/conversations";
import { DashboardContent, DashboardSkeleton } from "@/components/content/dashboard-content";
import { UniversalQuickEntry } from "@/components/records/universal-quick-entry";
import { useEffect } from "react";

async function fetchDashboardData() {
  const [members, household, providers, reminders, notifications, records, conversations] =
    await Promise.all([
      listMembers(),
      getHousehold(),
      listProviders().catch(() => []),
      listReminders().catch(() => []),
      listNotifications().catch(() => []),
      listHouseholdRecords(30).catch(() => []),
      listConversations().catch(() => []),
    ]);
  return { members, household, providers, reminders, notifications, records, conversations };
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const { data, error } = useSWR("dashboard", fetchDashboardData, {
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

  if (!data) return <DashboardSkeleton />;

  // Redirect to onboarding if no members
  if (data.members.length === 0) {
    navigate("/onboarding");
    return null;
  }

  const unreadNotifications = data.notifications.filter((n) => !n.is_read).length;
  const seen = new Set<string>();
  const upcomingReminders = data.reminders
    .filter((r) => r.is_active && new Date(r.start_datetime) > new Date())
    .filter((r) => {
      const key = `${r.title}|${r.start_datetime}|${r.reminder_type}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => new Date(a.start_datetime).getTime() - new Date(b.start_datetime).getTime())
    .slice(0, 5);

  return (
    <>
      <DashboardContent
        members={data.members}
        householdName={data.household.name}
        stats={{
          providersCount: data.providers.length,
          conversationsCount: data.conversations.length,
          unreadNotifications,
          upcomingReminders,
        }}
        records={data.records}
      />
      <UniversalQuickEntry members={data.members} />
    </>
  );
}
