import useSWR from "swr";
import { listNotifications } from "@/lib/api/notifications";
import { NotificationsContent } from "@/app/(app)/notifications/notifications-content";
import { ErrorState } from "@/components/shared/error-state";

export default function NotificationsPage() {
  const {
    data: notifications,
    error,
    mutate,
  } = useSWR("notifications", async () => {
    return listNotifications();
  });
  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!notifications)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  return <NotificationsContent notifications={notifications} />;
}
