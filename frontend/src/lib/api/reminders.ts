import { apiRequest } from "../api-client";
import type { ReminderCreate, ReminderUpdate, ReminderResponse } from "../types/reminder";
import type { ReminderType } from "../types/enums";

export function listReminders(params?: {
  reminder_type?: ReminderType;
  is_active?: string;
  family_member_id?: string;
}) {
  return apiRequest<ReminderResponse[]>("/reminders", {
    params: params as Record<string, string | undefined>,
  });
}

export function createReminder(data: ReminderCreate) {
  return apiRequest<ReminderResponse>("/reminders", { method: "POST", body: data });
}

export function getReminder(reminderId: string) {
  return apiRequest<ReminderResponse>(`/reminders/${reminderId}`);
}

export function updateReminder(reminderId: string, data: ReminderUpdate) {
  return apiRequest<ReminderResponse>(`/reminders/${reminderId}`, {
    method: "PUT",
    body: data,
  });
}

export function deleteReminder(reminderId: string) {
  return apiRequest<void>(`/reminders/${reminderId}`, { method: "DELETE" });
}
