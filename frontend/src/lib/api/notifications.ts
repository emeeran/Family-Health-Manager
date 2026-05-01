import { apiRequest } from "../api-client";
import type { NotificationResponse } from "../types/notification";

export function listNotifications(params?: { is_read?: string }) {
  return apiRequest<NotificationResponse[]>("/notifications", { params });
}

export function markAsRead(notificationId: string) {
  return apiRequest<NotificationResponse>(`/notifications/${notificationId}/read`, {
    method: "PUT",
  });
}

export function deleteNotification(notificationId: string) {
  return apiRequest<void>(`/notifications/${notificationId}`, { method: "DELETE" });
}

export function markAllAsRead() {
  return apiRequest<{ marked: number }>("/notifications/read-all", { method: "PUT" });
}
