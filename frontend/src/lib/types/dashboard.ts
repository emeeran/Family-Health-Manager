export interface DashboardAlert {
  id: string;
  alert_type: string;
  severity: "critical" | "warning" | "info";
  title: string;
  message: string;
  member_name: string;
  family_member_id: string;
  created_at: string;
}

export interface PreventiveItem {
  member_id: string;
  member_name: string;
  recommendation: string;
  priority: "high" | "medium" | "low";
  category: string;
  due_status: "overdue" | "due_soon" | "upcoming";
}

export interface MedicationSummary {
  total_active_medications: number;
  members_with_medications: number;
  refill_reminders: {
    medicine: string;
    member_name: string;
    days_until_empty: number;
  }[];
}

export interface MemberScore {
  member_id: string;
  first_name: string;
  last_name: string;
  health_score: number;
  score_breakdown: Record<string, { score: number; max: number; label: string }>;
  total_records: number;
  active_medications_count: number;
  risk_level?: "low" | "moderate" | "high";
}

export interface RecordActivity {
  total_last_30_days: number;
  by_type: Record<string, number>;
}

export interface VaccinationStatus {
  total_vaccinations: number;
  overdue_count: number;
}

export interface RiskSummary {
  high_risk_members: number;
  moderate_risk_members: number;
  low_risk_members: number;
}

export interface DashboardSummary {
  alerts: DashboardAlert[];
  preventive_care: PreventiveItem[];
  medication_summary: MedicationSummary;
  scores: MemberScore[];
  record_activity: RecordActivity;
  vaccination_status: VaccinationStatus;
  risk_summary: RiskSummary;
  // Extended fields (single-call dashboard)
  members: {
    id: string;
    first_name: string;
    last_name: string;
    date_of_birth: string;
    gender: string;
    relationship: string;
    blood_group: string | null;
    bmi: number | null;
    is_active: boolean;
    allergies_json: string | null;
  }[];
  household_name: string;
  providers_count: number;
  unread_notifications: number;
  upcoming_reminders: {
    id: string;
    title: string;
    start_datetime: string | null;
    reminder_type: string;
    family_member_id: string | null;
  }[];
  recent_records: {
    id: string;
    family_member_id: string;
    record_type: string;
    record_date: string | null;
    diagnosis: string | null;
    clinical_data: string | null;
    is_deleted: boolean;
    created_at: string | null;
  }[];
  conversations_count: number;
}

export interface RiskFactor {
  factor: string;
  severity: "high" | "moderate" | "low";
  description: string;
}

export interface RiskAssessment {
  risk_level: "low" | "moderate" | "high";
  factors: RiskFactor[];
}
