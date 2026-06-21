import { apiRequest } from "../api-client";

export function dismissHealthAlert(alertId: string) {
  return apiRequest<{ dismissed: boolean; id: string }>(`/health-alerts/${alertId}/dismiss`, {
    method: "PUT",
  });
}
