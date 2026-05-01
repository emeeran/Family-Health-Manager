import useSWR from "swr";
import { listNotifications } from "@/lib/api/notifications";

async function fetchUnreadCount(): Promise<number> {
  const notifications = await listNotifications().catch(() => []);
  return notifications.filter((n) => !n.is_read).length;
}

export function useNotificationCount() {
  const { data: count = 0 } = useSWR("notification-count", fetchUnreadCount, {
    refreshInterval: 30_000,
    revalidateOnFocus: true,
    dedupingInterval: 10_000,
  });
  return count;
}
