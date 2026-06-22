import type { ReminderType, ScheduleType } from "./enums";

export interface ReminderCreate {
  family_member_id?: string | null;
  reminder_type: ReminderType;
  title: string;
  description?: string | null;
  schedule_type: ScheduleType;
  schedule_interval?: number | null;
  start_datetime: string;
  end_datetime?: string | null;
}

export interface ReminderUpdate {
  title?: string | null;
  description?: string | null;
  schedule_type?: ScheduleType | null;
  schedule_interval?: number | null;
  start_datetime?: string | null;
  end_datetime?: string | null;
  is_active?: boolean | null;
}

export interface ReminderResponse {
  id: string;
  household_id: string;
  family_member_id: string | null;
  reminder_type: ReminderType;
  title: string;
  description: string | null;
  schedule_type: ScheduleType;
  schedule_interval: number | null;
  start_datetime: string;
  end_datetime: string | null;
  is_active: boolean;
  created_at: string;
}
