import useSWR from "swr";
import { listNotifications } from "@/lib/api/notifications";
import type { NotificationResponse } from "@/lib/types/notification";

/**
 * Hook for auto-refreshing notification state.
 * Polls every 30 seconds to detect new notifications.
 * Used in the header badge and notifications page.
 */
export function useNotifications() {
  const { data, error, mutate, isLoading } = useSWR<NotificationResponse[]>(
    "notifications",
    () => listNotifications(),
    {
      refreshInterval: 30_000,
      revalidateOnFocus: true,
      dedupingInterval: 10_000,
    }
  );

  const unreadCount = data?.filter((n) => !n.is_read).length ?? 0;
  const unreadNotifications = data?.filter((n) => !n.is_read) ?? [];

  return {
    notifications: data ?? [],
    unreadCount,
    unreadNotifications,
    isLoading,
    error,
    mutate,
  };
}
