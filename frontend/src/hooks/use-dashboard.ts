import useSWR from "swr";
import { getDashboardSummary } from "@/lib/api/dashboard";
import type { DashboardSummary } from "@/lib/types/dashboard";

/**
 * Hook for auto-refreshing dashboard summary data.
 * Polls every 5 minutes so the dashboard widgets stay current.
 * Uses a shared SWR key so the dashboard page and content component
 * deduplicate requests automatically.
 */
export function useDashboardSummary() {
  const { data, error, mutate, isLoading } = useSWR<DashboardSummary>(
    "dashboard",
    () => getDashboardSummary(),
    {
      refreshInterval: 300_000,
      revalidateOnFocus: true,
      dedupingInterval: 30_000,
    }
  );

  return {
    summary: data,
    isLoading,
    error,
    mutate,
  };
}
