import type { Gender, Relationship } from "./enums";
import type { ProviderAssignmentResponse } from "./provider-assignment";

export interface AllergyEntry {
  name: string;
  severity: "mild" | "moderate" | "severe";
}

export interface MedicalHistoryQuestionnaire {
  conditions?: string | null;
  allergies?: string | null;
  current_medications?: string | null;
  past_surgeries?: string | null;
  blood_group?: string | null;
  family_history?: string | null;
}

export interface FamilyMemberCreate {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  gender: Gender;
  relationship: Relationship;
  height_cm?: number | null;
  weight_kg?: number | null;
  allergies?: AllergyEntry[] | null;
  emergency_contact_name?: string | null;
  emergency_contact_phone?: string | null;
  medical_history?: MedicalHistoryQuestionnaire | null;
}

export interface FamilyMemberUpdate {
  first_name?: string | null;
  last_name?: string | null;
  date_of_birth?: string | null;
  gender?: Gender | null;
  relationship?: Relationship | null;
  medical_history_summary?: string | null;
  blood_group?: string | null;
  family_history?: string | null;
  height_cm?: number | null;
  weight_kg?: number | null;
  allergies?: AllergyEntry[] | null;
  emergency_contact_name?: string | null;
  emergency_contact_phone?: string | null;
  is_active?: boolean | null;
}

export interface FamilyMemberResponse {
  id: string;
  household_id: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  gender: Gender;
  relationship: Relationship;
  medical_history_summary: string | null;
  blood_group: string | null;
  family_history: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  allergies: AllergyEntry[] | null;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
  bmi: number | null;
  bmi_category: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ActiveMedication {
  medicine: string;
  type: string;
  dosage: string;
  duration: string;
  timing: string;
  note: string;
  start_date: string | null;
  end_date: string | null;
  status: "active" | "completed";
  prescribed_date?: string | null;
  provider_name?: string | null;
  record_id: string;
  prescription_index: number;
}

export interface DrugInteraction {
  drugs: string[];
  severity: "high" | "moderate" | "low";
  description: string;
  recommendation: string;
}

export interface DrugInteractionResponse {
  interactions: DrugInteraction[];
  medications_checked: number;
}

export interface BmiHistoryEntry {
  date: string;
  bmi: number;
  height_cm?: number | null;
  weight_kg?: number | null;
}

export interface Hba1cHistoryEntry {
  date: string;
  hba1c_value: number;
}

export interface MemberDashboardResponse {
  member: FamilyMemberResponse;
  brief_medical_history: string | null;
  active_medications: ActiveMedication[];
  active_conditions_count: number;
  active_medications_count: number;
  age: number;
  health_score: number;
  score_breakdown?: Record<string, { score: number; max: number; label: string }> | null;
  provider_assignments: ProviderAssignmentResponse[];
}

export interface PreventiveRecommendation {
  title: string;
  description: string;
  priority: "high" | "medium" | "low";
  category: string;
  due_interval_months: number;
  source: string;
}

export interface PreventiveRecommendationsResponse {
  recommendations: PreventiveRecommendation[];
}

export interface BatchMemberScore {
  member_id: string;
  total_records: number;
  latest_record_date: string;
  active_medications_count: number;
}

export interface BatchScoresResponse {
  members: BatchMemberScore[];
}
