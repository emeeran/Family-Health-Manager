export interface NotificationResponse {
  id: string;
  reminder_id: string;
  household_id: string;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
}
