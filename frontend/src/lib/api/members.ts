import { apiRequest } from "../api-client";
import type {
  FamilyMemberCreate,
  FamilyMemberUpdate,
  FamilyMemberResponse,
  MemberDashboardResponse,
  DrugInteractionResponse,
  ActiveMedication,
  BmiHistoryEntry,
  Hba1cHistoryEntry,
  PreventiveRecommendation,
  PreventiveRecommendationsResponse,
  BatchScoresResponse,
} from "../types/member";
import type { MedicationDiffResponse } from "../types/health-record";
import type { VerificationResult } from "../types/message";

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

export function getMemberDashboard(memberId: string) {
  return apiRequest<MemberDashboardResponse>(`/members/${memberId}/dashboard`);
}

export function getDrugInteractions(memberId: string) {
  return apiRequest<DrugInteractionResponse>(`/members/${memberId}/drug-interactions`);
}

export function getLatestInsight(memberId: string) {
  return apiRequest<GeneratedInsight>(`/members/${memberId}/latest-insight`);
}

export function getLatestDrugInteractions(memberId: string) {
  return apiRequest<DrugInteractionResponse>(`/members/${memberId}/latest-drug-interactions`);
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
}

export function generateMemberInsights(memberId: string) {
  return apiRequest<GeneratedInsight>(`/members/${memberId}/generate-insights`, {
    method: "POST",
  });
}

export function getBmiHistory(memberId: string) {
  return apiRequest<BmiHistoryEntry[]>(`/members/${memberId}/bmi-history`);
}

export function getHba1cHistory(memberId: string) {
  return apiRequest<Hba1cHistoryEntry[]>(`/members/${memberId}/hba1c-history`);
}

export function getPreventiveRecommendations(memberId: string) {
  return apiRequest<PreventiveRecommendationsResponse>(
    `/members/${memberId}/preventive-recommendations`
  );
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

export function generatePreConsultationNote(memberId: string) {
  return apiRequest<GeneratedInsight>(`/members/${memberId}/pre-consultation-note`, {
    method: "POST",
  });
}

export function getLatestPreConsultationNote(memberId: string) {
  return apiRequest<{ note: GeneratedInsight | null }>(
    `/members/${memberId}/pre-consultation-note/latest`
  );
}
