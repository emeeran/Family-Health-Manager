import { apiRequest } from "../api-client";
import type { DashboardSummary } from "../types/dashboard";

export function getDashboardSummary() {
  return apiRequest<DashboardSummary>("/dashboard/summary");
}
