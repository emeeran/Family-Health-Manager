import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { listMembers } from "@/lib/api/members";
import { listReminders } from "@/lib/api/reminders";
import { ErrorState } from "@/components/shared/error-state";
import { PageLoader } from "@/components/shared/page-loader";
import { MembersContent } from "@/components/content/members-content";
import { RemindersContent } from "@/components/content/reminders-content";
import { cn } from "@/lib/utils";
import { Users, CalendarClock } from "lucide-react";

const TABS = [
  { key: "family", label: "Family", icon: Users },
  { key: "reminders", label: "Reminders", icon: CalendarClock },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function PeoplePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab") as TabKey | null;
  const [activeTab, setActiveTab] = useState<TabKey>(
    TABS.some((t) => t.key === tabParam) ? tabParam! : "family"
  );

  const {
    data: membersData,
    error: membersError,
    mutate: mutateMembers,
  } = useSWR("members", () => listMembers());

  const {
    data: remindersData,
    error: remindersError,
    mutate: mutateReminders,
  } = useSWR("reminders-page", async () => {
    const reminders = await listReminders();
    return reminders;
  });

  function handleTabChange(key: TabKey) {
    setActiveTab(key);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("tab", key);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      {/* Tab pills */}
      <div className="flex items-center gap-1 rounded-lg bg-muted/50 p-1">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              onClick={() => handleTabChange(tab.key)}
              className={cn(
                "relative flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-all",
                activeTab === tab.key
                  ? "bg-card text-foreground shadow-sm ring-1 ring-[var(--brand-accent)]/20"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon
                className={cn(
                  "h-3.5 w-3.5",
                  activeTab === tab.key ? "text-[var(--brand-accent)]" : ""
                )}
              />
              {tab.label}
              {activeTab === tab.key && (
                <div className="absolute bottom-0 left-1/4 right-1/4 h-[2px] rounded-full bg-[var(--brand-accent)]" />
              )}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      {activeTab === "family" && (
        <>
          {membersError ? (
            <ErrorState onRetry={() => mutateMembers()} />
          ) : !membersData ? (
            <PageLoader title="Family Members" />
          ) : (
            <MembersContent members={membersData} />
          )}
        </>
      )}

      {activeTab === "reminders" && (
        <>
          {remindersError ? (
            <ErrorState onRetry={() => mutateReminders()} />
          ) : !remindersData || !membersData ? (
            <PageLoader title="Reminders" />
          ) : (
            <RemindersContent reminders={remindersData} members={membersData} />
          )}
        </>
      )}
    </div>
  );
}
