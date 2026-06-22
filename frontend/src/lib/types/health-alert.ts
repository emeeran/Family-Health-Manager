export type AlertType =
  | "lab_critical"
  | "lab_warning"
  | "trend_declining"
  | "trend_improving"
  | "preventive_due";
export type AlertSeverity = "critical" | "warning" | "info";

export interface HealthAlertResponse {
  id: string;
  household_id: string;
  family_member_id: string;
  record_id: string | null;
  alert_type: AlertType;
  severity: AlertSeverity;
  title: string;
  message: string;
  test_name: string | null;
  value: string | null;
  reference: string | null;
  is_dismissed: boolean;
  created_at: string | null;
}
