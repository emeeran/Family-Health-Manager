import type { Gender, Relationship } from "./enums";
import type { ProviderAssignmentResponse } from "./provider-assignment";
import type { InsightSection } from "../parse-sections";
import type { SmartReportData } from "./smart-report";

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
  patient_id?: string | null;
  phone?: string | null;
  address?: string | null;
  medical_history?: MedicalHistoryQuestionnaire | null;
  notes?: string | null;
  cloud_ai_consent?: boolean | null;
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
  patient_id?: string | null;
  phone?: string | null;
  address?: string | null;
  notes?: string | null;
  is_active?: boolean | null;
  cloud_ai_consent?: boolean | null;
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
  patient_id?: string | null;
  phone?: string | null;
  address?: string | null;
  family_history: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  allergies: AllergyEntry[] | null;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
  notes: string | null;
  bmi: number | null;
  bmi_category: string | null;
  is_active: boolean;
  cloud_ai_consent: boolean;
  created_at: string;
  has_photo: boolean;
  photo_updated_at: string | null;
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
  /** Who flagged the interaction: "drugbank" (authoritative) or "ai" (AI estimate). */
  source?: "drugbank" | "ai";
  /** DrugBank evidence_level (level_1/level_2) when source is drugbank. */
  evidence_level?: string;
}

export interface DrugInteractionResponse {
  interactions: DrugInteraction[];
  medications_checked: number;
  cached_at: string | null;
}

/** FDA recall (enforcement) report matching one of the member's active meds. */
export interface DrugRecall {
  generic_name: string;
  product_description: string;
  reason_for_recall: string;
  classification: string;
  status: string;
  recalling_firm: string;
  recall_initiation_date: string;
  code_info: string;
  matched_medications?: string[];
}

export interface DrugRecallsResponse {
  recalls: DrugRecall[];
  medications_checked: number;
  checked_at: string;
}

/** FDA prescribing-label section (text-only). Only non-empty sections are sent. */
export interface DrugLabelSummary {
  generic_name: string;
  brand_name: string | null;
  manufacturer: string | null;
  drug_class: string | null;
  effective_date: string | null;
  sections: Record<string, string>;
}

/** A frequently-reported adverse reaction (FAERS) with its report count. */
export interface AdverseEventReaction {
  term: string;
  count: number;
}

/** An alternate/substitute brand (ABDM Drug Registry, India). */
export interface SubstituteDrug {
  id: string;
  name: string;
}

/** Indian-context indication/contraindication for a medication (ABDM). */
export interface DrugIndication {
  indication: string;
  contraindication: string;
  dose_form: string;
  routes: string[];
  source: string;
}

/** A MedlinePlus patient-education health-topic link (MedlinePlus Connect). */
export interface MedlinePlusTopic {
  title: string;
  url: string;
  summary?: string;
}

/** A DailyMed Structured Product Label (full package-insert) link. */
export interface DailyMedLabel {
  title: string;
  setid: string;
  url: string;
}

/** A normalized condition lookup result (clinicaltables → MedlinePlus Connect). */
export interface ConditionLookup {
  query: string;
  name: string | null;
  icd10_code: string | null;
  synonyms: string[];
  topics: MedlinePlusTopic[];
}

/** Response for the member's distinct condition/diagnosis strings. */
export interface MemberConditionsResponse {
  conditions: string[];
}

/** A clinical trial from ClinicalTrials.gov v2. */
export interface ClinicalTrial {
  nct_id: string;
  title: string;
  status: string;
  phase: string;
  conditions: string[];
  url: string;
}

/** A Health Canada DPD product resolved from an 8-digit DIN. */
export interface CanadianDrugProduct {
  din: string;
  brand_name: string;
  descriptor: string;
  company_name: string;
  class_name: string;
  drug_code: number | null;
  ai_group_no: string;
  last_update_date: string;
}

/** An MHRA drug-safety entry (UK) from the GOV.UK search API. */
export interface UkAlert {
  title: string;
  url: string;
  description: string;
  date: string;
  format: string;
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

export interface MemberDetailResponse {
  member: FamilyMemberResponse;
  health_score: number;
  score_breakdown: Record<string, { score: number; max: number; label: string }> | null;
  brief_medical_history: string | null;
  active_medications: ActiveMedication[];
  active_medications_count: number;
  active_conditions_count: number;
  age: number;
  provider_assignments: ProviderAssignmentResponse[];
  risk_assessment: { level: string; score: number } | null;
  hba1c_history: Hba1cHistoryEntry[];
  drug_interactions: DrugInteraction[];
  latest_insight: {
    id: string;
    response: string;
    provider_used: string;
    generated_at: string;
    verification: {
      status: string;
      claims_checked?: number | null;
      verifier_provider?: string | null;
      summary?: string | null;
      warnings?: string[] | null;
      verified_at?: string | null;
    } | null;
    sections?: InsightSection[] | null;
  } | null;
  latest_preconsult_note: {
    id: string;
    response: string;
    provider_used: string;
    generated_at: string;
    verification: {
      status: string;
      claims_checked?: number | null;
      verifier_provider?: string | null;
      summary?: string | null;
      warnings?: string[] | null;
      verified_at?: string | null;
    } | null;
    sections?: InsightSection[] | null;
  } | null;
  latest_smart_report: {
    id: string;
    response: string;
    provider_used: string;
    generated_at: string;
    verification: {
      status: string;
      claims_checked?: number | null;
      verifier_provider?: string | null;
      summary?: string | null;
      warnings?: string[] | null;
      verified_at?: string | null;
    } | null;
    report?: SmartReportData | null;
    raw_response?: string;
    sources?:
      | { id: string; type?: string | null; date?: string | null; summary?: string | null }[]
      | null;
    freshness_as_of?: string | null;
    range_start?: string | null;
  } | null;
  recent_records: {
    id: string;
    record_type: string;
    record_date: string | null;
    diagnosis: string | null;
    provider_name: string | null;
    summary: string | null;
  }[];
  upcoming_reminders: {
    id: string;
    title: string;
    description: string | null;
    start_datetime: string | null;
    reminder_type: string;
  }[];
  vaccinations: {
    id: string;
    name: string;
    date_administered: string | null;
    booster_due_date: string | null;
    notes: string | null;
  }[];
  preventive_recommendations: PreventiveRecommendation[];
}

/** One potential same-class duplicate-therapy flag (clinician review). */
export interface DuplicateTherapyFinding {
  therapeutic_class: string;
  medications: string[];
}

export interface DuplicateTherapyResponse {
  findings: DuplicateTherapyFinding[];
  medications_checked: number;
}
