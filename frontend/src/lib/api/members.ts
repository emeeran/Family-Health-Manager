import { apiRequest } from "../api-client";
import type {
  FamilyMemberCreate,
  FamilyMemberUpdate,
  FamilyMemberResponse,
  MemberDashboardResponse,
  MemberDetailResponse,
  DrugInteractionResponse,
  DrugRecallsResponse,
  DrugLabelSummary,
  AdverseEventReaction,
  MedlinePlusTopic,
  DailyMedLabel,
  ClinicalTrial,
  CanadianDrugProduct,
  UkAlert,
  ActiveMedication,
  Hba1cHistoryEntry,
  PreventiveRecommendation,
  BatchScoresResponse,
} from "../types/member";
import type { MedicationDiffResponse } from "../types/health-record";
import type { VerificationResult } from "../types/message";
import type { InsightSection } from "../parse-sections";
import type { SmartReportData } from "../types/smart-report";

export function listMembers(params?: { is_active?: string }) {
  return apiRequest<FamilyMemberResponse[]>("/members", { params });
}

export function createMember(data: FamilyMemberCreate) {
  return apiRequest<FamilyMemberResponse>("/members", { method: "POST", body: data });
}

export function getMember(memberId: string) {
  return apiRequest<FamilyMemberResponse>(`/members/${memberId}`);
}

export function updateMember(memberId: string, data: FamilyMemberUpdate) {
  return apiRequest<FamilyMemberResponse>(`/members/${memberId}`, {
    method: "PUT",
    body: data,
  });
}

export function deleteMember(memberId: string) {
  return apiRequest<void>(`/members/${memberId}`, { method: "DELETE" });
}

/** Upload (or replace) a member's profile photo. The photo is served back as a
 *  300px WebP thumbnail via GET /members/{id}/photo (cookie-auth <img>), so the
 *  response's photo_updated_at drives the client cache-bust query param. */
export function uploadMemberPhoto(memberId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<FamilyMemberResponse>(`/members/${memberId}/photo`, {
    method: "POST",
    body: formData,
    isFormData: true,
  });
}

export function deleteMemberPhoto(memberId: string) {
  return apiRequest<FamilyMemberResponse>(`/members/${memberId}/photo`, {
    method: "DELETE",
  });
}

export function getMemberDashboard(memberId: string) {
  return apiRequest<MemberDashboardResponse>(`/members/${memberId}/dashboard`);
}

export function getMemberDetail(memberId: string) {
  return apiRequest<MemberDetailResponse>(`/members/${memberId}/detail`);
}

export function getDrugInteractions(memberId: string) {
  return apiRequest<DrugInteractionResponse>(`/members/${memberId}/drug-interactions`, {
    timeout: 120_000,
  });
}

export function getLatestInsight(memberId: string) {
  return apiRequest<GeneratedInsight>(`/members/${memberId}/latest-insight`);
}

export function getLatestDrugInteractions(memberId: string) {
  return apiRequest<DrugInteractionResponse>(`/members/${memberId}/latest-drug-interactions`, {
    timeout: 120_000,
  });
}

/** FDA recall reports matching any of the member's active medications (free, no key). */
export function getDrugRecalls(memberId: string) {
  return apiRequest<DrugRecallsResponse>(`/members/${memberId}/drug-recalls`, {
    timeout: 30_000,
  });
}

/** FDA prescribing label (key sections) for a single medication. */
export function getDrugLabel(memberId: string, medicine: string) {
  return apiRequest<{ label: DrugLabelSummary | null }>(`/members/${memberId}/drug-label`, {
    params: { medicine },
    timeout: 30_000,
  });
}

/** Top reported adverse reactions (FAERS) for a single medication. */
export function getDrugAdverseEvents(memberId: string, medicine: string) {
  return apiRequest<{ events: AdverseEventReaction[] }>(
    `/members/${memberId}/drug-adverse-events`,
    { params: { medicine }, timeout: 30_000 }
  );
}

/** Patient-education links (MedlinePlus) + full-label links (DailyMed) for a med. */
export function getDrugEducation(memberId: string, medicine: string) {
  return apiRequest<{ medlineplus: MedlinePlusTopic[]; dailymed: DailyMedLabel[] }>(
    `/members/${memberId}/drug-education`,
    { params: { medicine }, timeout: 30_000 }
  );
}

/** Clinical trials (ClinicalTrials.gov v2) matching a condition. */
export function getClinicalTrials(memberId: string, condition: string, limit = 8) {
  return apiRequest<{ trials: ClinicalTrial[]; condition: string }>(
    `/members/${memberId}/clinical-trials`,
    { params: { condition, limit: String(limit) }, timeout: 30_000 }
  );
}

/** MedlinePlus patient-education for an ICD-10/SNOMED/LOINC code. */
export function getConditionInfo(memberId: string, codeSystem: string, code: string) {
  return apiRequest<{ results: MedlinePlusTopic[] }>(`/members/${memberId}/condition-info`, {
    params: { code_system: codeSystem, code },
    timeout: 30_000,
  });
}

/** Health Canada DPD product for an 8-digit DIN (no name search available). */
export function getCanadianProduct(memberId: string, din: string) {
  return apiRequest<{ product: CanadianDrugProduct | null }>(
    `/members/${memberId}/canadian-product`,
    { params: { din }, timeout: 30_000 }
  );
}

/** MHRA drug-safety alerts/news (GOV.UK) for a drug or term — UK recall source. */
export function getUkAlerts(memberId: string, term: string, limit = 5) {
  return apiRequest<{ alerts: UkAlert[]; term: string }>(`/members/${memberId}/uk-alerts`, {
    params: { term, limit: String(limit) },
    timeout: 30_000,
  });
}

export function addMedication(
  memberId: string,
  data: Omit<
    ActiveMedication,
    | "start_date"
    | "end_date"
    | "status"
    | "prescribed_date"
    | "provider_name"
    | "record_id"
    | "prescription_index"
  >
) {
  return apiRequest<{
    id: string;
    prescription: ActiveMedication;
    record_id: string;
    prescription_index: number;
  }>(`/members/${memberId}/medications`, { method: "POST", body: data });
}

export function updateMedication(
  memberId: string,
  recordId: string,
  prescriptionIndex: number,
  data: Omit<
    ActiveMedication,
    | "start_date"
    | "end_date"
    | "status"
    | "prescribed_date"
    | "provider_name"
    | "record_id"
    | "prescription_index"
  >
) {
  return apiRequest<{ updated: boolean }>(`/members/${memberId}/medications`, {
    method: "PUT",
    body: { record_id: recordId, prescription_index: prescriptionIndex, data },
  });
}

export function deleteMedication(memberId: string, recordId: string, prescriptionIndex: number) {
  return apiRequest<{ deleted: boolean }>(`/members/${memberId}/medications`, {
    method: "DELETE",
    body: { record_id: recordId, prescription_index: prescriptionIndex },
  });
}

export interface GeneratedInsight {
  id: string;
  response: string;
  provider_used: string;
  generated_at: string;
  verification: VerificationResult | null;
  /** Smart Report only — structured object parsed server-side. */
  report?: SmartReportData | null;
  /** Smart Report only — the raw JSON string (fallback for prose render). */
  raw_response?: string;
  /** Insights only — server-parsed markdown sections with stable keys. */
  sections?: InsightSection[] | null;
}

export type InsightMode = "comprehensive" | "brief";

export function getHba1cHistory(memberId: string) {
  return apiRequest<Hba1cHistoryEntry[]>(`/members/${memberId}/hba1c-history`);
}

export function createPreventiveReminder(
  memberId: string,
  recommendation: PreventiveRecommendation
) {
  return apiRequest<{ id: string; title: string; due_date: string }>(
    `/members/${memberId}/preventive-reminders`,
    {
      method: "POST",
      body: {
        title: recommendation.title,
        description: recommendation.description,
        due_interval_months: recommendation.due_interval_months,
      },
    }
  );
}

export function getBatchScores() {
  return apiRequest<BatchScoresResponse>("/members/batch-scores");
}

export function bulkDeleteMedications(
  memberId: string,
  items: Array<{ record_id: string; prescription_index: number }>
) {
  return apiRequest<{ deleted: number }>(`/members/${memberId}/medications/bulk-delete`, {
    method: "POST",
    body: { items },
  });
}

export function computeMedicationDiff(
  memberId: string,
  prescriptions: Record<string, string>[],
  recordId?: string
) {
  return apiRequest<MedicationDiffResponse>(`/members/${memberId}/medications/diff`, {
    method: "POST",
    body: { prescriptions, record_id: recordId },
  });
}

export function applyMedicationSync(
  memberId: string,
  applyAdded: string[],
  applyUpdated: string[],
  applyRemoved: string[]
) {
  return apiRequest<{ applied: number }>(`/members/${memberId}/medications/apply-sync`, {
    method: "POST",
    body: {
      apply_added: applyAdded,
      apply_updated: applyUpdated,
      apply_removed: applyRemoved,
    },
  });
}

export function getLatestPreConsultationNote(memberId: string) {
  return apiRequest<{ note: GeneratedInsight | null }>(
    `/members/${memberId}/pre-consultation-note/latest`
  );
}
