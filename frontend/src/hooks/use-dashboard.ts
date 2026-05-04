import useSWR from "swr";
import { getDashboardSummary } from "@/lib/api/dashboard";
import type { DashboardSummary } from "@/lib/types/dashboard";

/**
 * Hook for auto-refreshing dashboard summary data.
 * Polls every 60 seconds so the dashboard widgets stay current.
 */
export function useDashboardSummary() {
  const { data, error, mutate, isLoading } = useSWR<DashboardSummary>(
    "dashboard-summary",
    () => getDashboardSummary(),
    {
      refreshInterval: 60_000,
      revalidateOnFocus: true,
      dedupingInterval: 15_000,
    }
  );

  return {
    summary: data,
    isLoading,
    error,
    mutate,
  };
}
