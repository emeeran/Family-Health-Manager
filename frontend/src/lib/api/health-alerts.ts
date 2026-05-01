import { apiRequest } from "../api-client";
import type { HealthAlertResponse, AlertSeverity } from "../types/health-alert";

export function listHealthAlerts(params?: {
  member_id?: string;
  severity?: AlertSeverity;
  dismissed?: boolean;
}) {
  return apiRequest<HealthAlertResponse[]>("/health-alerts", {
    params: params as Record<string, string | undefined>,
  });
}

export function dismissHealthAlert(alertId: string) {
  return apiRequest<{ dismissed: boolean; id: string }>(`/health-alerts/${alertId}/dismiss`, {
    method: "PUT",
  });
}
