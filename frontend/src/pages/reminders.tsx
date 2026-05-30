import useSWR from "swr";
import { listReminders } from "@/lib/api/reminders";
import { listMembers } from "@/lib/api/members";
import { RemindersContent } from "@/components/content/reminders-content";
import { ErrorState } from "@/components/shared/error-state";

export default function RemindersPage() {
  const { data, error, mutate } = useSWR("reminders-page", async () => {
    const [reminders, members] = await Promise.all([listReminders(), listMembers()]);
    return { reminders, members };
  });
  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!data)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  return <RemindersContent reminders={data.reminders} members={data.members} />;
}
