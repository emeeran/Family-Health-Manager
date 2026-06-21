import { apiRequest } from "../api-client";
import type { NotificationResponse } from "../types/notification";

export function listNotifications(params?: { is_read?: string }) {
  return apiRequest<NotificationResponse[]>("/notifications", { params });
}
